#!/usr/bin/env python3
"""
Crexi live broker scan — no browser, no API key.

Hits api.crexi.com directly (works unauthenticated from a residential IP;
cloud/sandbox IPs get 403'd). State geography comes from a captured polygon
fixture in references/crexi-polygons/<STATE>.json — capture new states once
via the browser (see .claude/skills/broker-search/SKILL.md, Browser mode).

Usage:
    python3 scripts/crexi_live.py --state GA                # scan + append new 2+ brokers to sheet
    python3 scripts/crexi_live.py --state GA --dry-run      # print only, no sheet writes
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from deal_inbox import BUY_BOX  # zip → market map, synced with references/buy-box.md
from gws_auth import get_token
from broker_search import TODAY, append_rows, get_existing_brokers

API = "https://api.crexi.com"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Origin": "https://www.crexi.com",
    "Referer": "https://www.crexi.com/",
}
POLYGON_DIR = Path(__file__).parent.parent / "references" / "crexi-polygons"
PAGE_SIZE = 60
BROKER_CONCURRENCY = 5
MIN_LISTINGS = 2


def _norm(name):
    """Punctuation/credential-proof name key: 'Damien Lanclos, CCIM' == 'damien lanclos ccim'."""
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def load_payload(state):
    fixture = POLYGON_DIR / f"{state.upper()}.json"
    if not fixture.exists():
        captured = sorted(p.stem for p in POLYGON_DIR.glob("*.json"))
        sys.exit(
            f"No polygon fixture for {state.upper()} (have: {', '.join(captured) or 'none'}).\n"
            f"Capture it once via browser mode — see /broker-search SKILL.md."
        )
    return json.loads(fixture.read_text())


def _post_with_retry(url, body, attempts=3):
    for i in range(attempts):
        try:
            r = requests.post(url, headers=HEADERS, json=body, timeout=30)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))


def search_assets(payload, state):
    """Page through all listings for the state. Dedupes by asset id."""
    assets, seen, offset, total = [], set(), 0, None
    while total is None or offset < total:
        r = _post_with_retry(
            f"{API}/assets/search",
            {**payload, "count": PAGE_SIZE, "offset": offset},
        )
        data = r.json()
        total = data["totalCount"]
        page = data["data"]
        if not page:
            break
        for a in page:
            # server-side sort shuffles between pages — dedupe, keep state-only
            if a["id"] in seen:
                continue
            seen.add(a["id"])
            locs = a.get("locations") or []
            if any((l.get("state") or {}).get("code") == state.upper() for l in locs):
                assets.append(a)
        offset += PAGE_SIZE
        time.sleep(0.3)
    print(f"  {len(assets)} unique {state.upper()} listings (of {total} reported)")
    return assets


FETCH_FAILURES = []


def fetch_brokers(asset):
    time.sleep(0.2)  # ponytail: fixed pace ≈ manual-browsing request rate; token bucket if Crexi ever pushes back
    try:
        r = requests.get(f"{API}/assets/{asset['id']}/brokers", headers=HEADERS, timeout=30)
        if r.status_code != 200:
            FETCH_FAILURES.append(asset["id"])
            return []
        return [
            {
                "broker_id": b["id"],
                "name": f"{b.get('firstName', '')} {b.get('lastName', '')}".strip(),
                "brokerage": (b.get("brokerage") or {}).get("name", ""),
                "profile": b.get("publicProfileId", ""),
                "total_listings": b.get("numberOfAssets", 0),
                "asset_name": asset.get("name", ""),
                "zips": [l["zip"].split("-")[0] for l in (asset.get("locations") or []) if l.get("zip")],
            }
            for b in r.json()
            if f"{b.get('firstName', '')}{b.get('lastName', '')}".strip()
        ]
    except requests.RequestException:
        FETCH_FAILURES.append(asset["id"])
        return []


def aggregate(rows):
    by_broker = {}
    for r in rows:
        b = by_broker.setdefault(
            r["broker_id"],
            {**{k: r[k] for k in ("name", "brokerage", "profile", "total_listings")},
             "listings": [], "zips": set()},
        )
        b["listings"].append(r["asset_name"])
        b["zips"].update(r["zips"])
    return sorted(by_broker.values(), key=lambda b: -len(b["listings"]))


def build_row(b, state):
    count = len(b["listings"])
    return [
        b["brokerage"], b["name"],
        "", "",  # email/phone — Crexi never exposes; enrich via /broker-search agents
        ", ".join(sorted(b["zips"])), "Multifamily", "B", "No",
        str(count), TODAY, "",
        "New — Found via Platform Scan",
        f"Auto-added: crexi_live {state.upper()} scan {TODAY}; {count} listings"
        f" ({b['total_listings']} total on Crexi); crexi profile: {b['profile']};"
        f" needs contact enrichment",
    ]


def parse_units(asset):
    m = re.search(r"(\d+)\s*Units?", f"{asset.get('description','')} {asset.get('name','')}", re.I)
    return int(m.group(1)) if m else None


def screen_deals(assets):
    """Buy-box screen: zip + 15–50 units + $1M–$3M. Unknown unit/price = still shown."""
    matches, near = [], []
    for a in assets:
        locs = a.get("locations") or []
        zips = [(l.get("zip") or "")[:5] for l in locs]
        market = next((BUY_BOX[z] for z in zips if z in BUY_BOX), None)
        loc0 = locs[0] if locs else {}
        city_state = f"{loc0.get('city','')}, {(loc0.get('state') or {}).get('code','')}"
        units, price = parse_units(a), a.get("askingPrice")
        units_ok = units is None or 15 <= units <= 50
        price_ok = price is None or 1_000_000 <= price <= 3_000_000
        entry = {
            "name": a.get("name", ""), "market": market, "units": units, "price": price,
            "url": f"https://www.crexi.com/properties/{a['id']}/{a.get('urlSlug','')}",
            "zips": ", ".join(z for z in zips if z), "city_state": city_state,
        }
        if market and units_ok and price_ok:
            matches.append(entry)
        elif market:  # right zip, wrong size/price — worth a glance
            near.append(entry)
    return matches, near


def print_deals(matches, near):
    def line(e):
        u = f"{e['units']} units" if e["units"] else "units ?"
        p = f"${e['price']:,.0f}" if e["price"] else "unpriced"
        if e.get("analyzed") and e.get("analyzed_strength") == "address":
            flag = f"\n    ⏭️  ALREADY ANALYZED → {e['analyzed']}"
        elif e.get("analyzed"):
            flag = f"\n    ⚠️  same city as analyzed deal ({e['analyzed']}) — verify not a dup"
        else:
            flag = ""
        return f"  • {e['name']} — {e['market'] or e['zips']} | {u} | {p}\n    {e['url']}{flag}"
    print(f"\n🎯 BUY BOX MATCHES ({len(matches)}):")
    for e in matches:
        print(line(e))
    print(f"\n🔶 NEAR MISSES — buy-box zip, size/price out of band ({len(near)}):")
    for e in near:
        print(line(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="GA")
    ap.add_argument("--min-listings", type=int, default=MIN_LISTINGS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--deals", action="store_true",
                    help="screen listings against the buy box instead of scanning brokers")
    args = ap.parse_args()

    if args.deals:
        from analyzed_deals import load_analyzed, match_analyzed
        assets = search_assets(load_payload(args.state), args.state)
        matches, near = screen_deals(assets)
        analyzed = load_analyzed(get_token())
        for e in matches + near:
            hit, strength = match_analyzed(e["city_state"], e["name"], analyzed)
            e["analyzed"] = hit["folder"] if hit else ""
            e["analyzed_strength"] = strength or ""
        print_deals(matches, near)
        return

    print(f"Crexi live scan — {args.state.upper()} multifamily")
    assets = search_assets(load_payload(args.state), args.state)

    rows = []
    with ThreadPoolExecutor(max_workers=BROKER_CONCURRENCY) as pool:
        for result in pool.map(fetch_brokers, assets):
            rows.extend(result)
    brokers = aggregate(rows)
    qualifying = [b for b in brokers if len(b["listings"]) >= args.min_listings]
    print(f"  {len(brokers)} unique brokers, {len(qualifying)} with {args.min_listings}+ listings")
    if FETCH_FAILURES:
        print(f"  ⚠️  broker fetch failed for {len(FETCH_FAILURES)} listing(s) — counts may be low: {FETCH_FAILURES[:10]}")

    token = get_token()
    _, existing_names = get_existing_brokers(token)
    existing_norm = {_norm(n) for n in existing_names}
    new = [b for b in qualifying if _norm(b["name"]) not in existing_norm]
    print(f"  {len(new)} not yet in Brokers List\n")

    for b in new:
        print(f"  + {b['name']} — {b['brokerage'] or '(no brokerage)'} | "
              f"{len(b['listings'])} listings | {', '.join(sorted(b['zips'])) or 'no zips'}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return
    append_rows(token, [build_row(b, args.state) for b in new])
    print(f"\n✅ {len(new)} broker(s) appended to Brokers List (contact fields blank — "
          f"run enrichment via /broker-search).")


if __name__ == "__main__":
    main()
