#!/usr/bin/env python3
"""
Olive Tree Investments — Broker Site Sweep

Off-market deals post on broker/brokerage sites BEFORE they hit Crexi/LoopNet.
This sweeps every broker in the Brokers List against their listings page so a
deal we haven't seen surfaces early.

Coverage is driven by the Brokers List sheet (not a hand-kept list), so every
broker we add is automatically in scope. Each broker's listings URL comes from,
in order:
  1. a manual/discovered override in references/broker-sites.json (keyed by name)
  2. a brokerage URL template (e.g. Marcus & Millichap advisor slug)
Brokers with neither are reported as "needs URL discovery" — hand those names to
the discovery agents (see /broker-search SKILL.md) which WebSearch each broker's
listings page and append it to broker-sites.json.

Fetch is deterministic Python (curl-style, local residential IP). EXTRACTION is
a Claude/agent step: read the saved .txt, pull listings, screen vs buy box, and
cross-check scripts/analyzed_deals.py so already-worked-up deals don't re-surface.
JS-app sites (M&M, Meybohm, GREA, MRG, Franklin St) don't server-render listings
— fetch saves their shell and marks them for the @browser DOM sweep instead.

Usage:
  python3 scripts/broker_sites.py --sync      # reconcile registry with the sheet, report gaps
  python3 scripts/broker_sites.py             # fetch all resolvable sites → output/broker-sites/<date>/
  python3 scripts/broker_sites.py --curl-only # skip known JS-app sites (they need @browser)
"""

import argparse
import html as html_mod
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from gws_auth import get_token
from deal_inbox import SHEETS_BASE, SPREADSHEET_ID, auth_headers

ROOT = Path(__file__).parent.parent
REGISTRY = ROOT / "references" / "broker-sites.json"
OUT_DIR = ROOT / "output" / "broker-sites" / date.today().isoformat()
HEADERS = {"User-Agent": (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")}

# Brokerages with a deterministic per-agent listings URL. Add patterns as we
# learn them; everything else falls through to per-broker discovery.
BROKERAGE_TEMPLATES = {
    "marcus & millichap": lambda first, last: (
        f"https://www.marcusmillichap.com/advisors/{first}-{last}", "js-app"),
}

# Brokerage-level listings pages: one page serves ALL that firm's agents, so any
# agent at the firm resolves to the same URL (deduped at fetch time). Regional
# Southeast firms whose whole inventory is in-market and worth sweeping.
# (substring match on brokerage name) -> (url, status)
BROKERAGE_SITES = {
    "grea": ("https://www.grea.com/properties", "js-app"),
    "charles hawkins": ("https://www.charleshawkinsco.com/", "active"),
    "fickling": ("https://commercial.fickling.com/", "active"),
    "meybohm": ("https://meybohmcre.com/property-search", "js-app"),
    "sherman": ("https://shermanandhemstreet.com/property-search/commercial-property-search/", "active"),
    "franklin street": ("https://franklinst.com/properties/for-sale/", "js-app"),
    "bull realty": ("https://www.bullrealty.com/properties", "active"),
    "edge realty": ("https://edge-re.com/properties/", "active"),
    "g2 commercial": ("https://g2cre.com/", "active"),
    "nai g2": ("https://g2cre.com/", "active"),
}
# Residential/franchise brands where individual agents rarely publish a listings
# page — resolve to "none" so they're recorded and not re-checked every sync.
RESIDENTIAL_BRANDS = (
    "keller williams", "kw ", "re/max", "century 21", "exp realty", "era ",
    "berkshire hathaway", "homesmart", "virtual properties", "pmi ",
    "fleur de lee", "first united", "skyline realty", "livian",
)
# Sites known to render listings client-side — fetch saves the shell; the real
# extraction is the @browser DOM sweep (see /deal-search SKILL.md).
JS_APP_HINTS = ("marcusmillichap.com", "meybohmcre.com", "grea.com",
                "mrgrealtypartners.com", "franklinst.com")


def to_text(raw):
    txt = re.sub(r"<(script|style|noscript).*?</\1>", " ", raw, flags=re.S | re.I)
    txt = html_mod.unescape(re.sub(r"<[^>]+>", "\n", txt))
    return "\n".join(l for l in (x.strip() for x in txt.splitlines()) if l)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_sheet_brokers(token):
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers%20List!A1:Z2000",
        headers=auth_headers(token), timeout=30)
    r.raise_for_status()
    rows = r.json().get("values", [])
    out = []
    for row in rows[1:]:
        brokerage = row[0].strip() if len(row) > 0 else ""
        name = row[1].strip() if len(row) > 1 else ""
        if name:
            out.append({"name": name, "brokerage": brokerage})
    return out


def template_url(broker):
    """Resolve a broker to a listings URL. Returns dict or None (needs discovery).
    A 'none' status means the firm has no per-agent page (residential) — resolved,
    just nothing to fetch."""
    b = broker["brokerage"].lower()
    # brokerage-level shared listings page (one URL for all the firm's agents)
    for key, (url, status) in BROKERAGE_SITES.items():
        if key in b:
            return {"url": url, "status": status, "source": "brokerage"}
    # residential brand with no per-agent page — record as resolved-none
    if any(k in b for k in RESIDENTIAL_BRANDS):
        return {"url": "", "status": "none", "source": "residential"}
    # per-agent URL template (M&M advisor slug)
    parts = broker["name"].split()
    if len(parts) >= 2:
        first, last = slug(parts[0]), slug(parts[-1])
        for key, fn in BROKERAGE_TEMPLATES.items():
            if key in b:
                url, status = fn(first, last)
                return {"url": url, "status": status, "source": "template"}
    return None


def build_registry(token):
    """Merge manual/discovered overrides (broker-sites.json) with sheet-derived
    template URLs. Returns (sites, unresolved) where unresolved = broker dicts
    with no URL from either source."""
    reg = json.loads(REGISTRY.read_text())
    by_name = {s["broker"].split(" / ")[0].strip().lower(): s for s in reg["sites"]}
    # also index team entries (broker field may list several names)
    for s in reg["sites"]:
        for nm in s["broker"].split(" / "):
            by_name.setdefault(nm.strip().lower(), s)

    sites, unresolved = list(reg["sites"]), []
    seen_urls = {s["url"] for s in reg["sites"] if s.get("url")}
    for broker in load_sheet_brokers(token):
        if broker["name"].lower() in by_name:
            continue  # already resolved (has an override/discovered entry)
        t = template_url(broker)
        if not t:
            unresolved.append(broker)
            continue
        if t["url"] and t["url"] in seen_urls:
            continue  # shared brokerage page already queued — don't fetch twice
        sites.append({"broker": broker["name"], "brokerage": broker["brokerage"],
                      "url": t["url"], "status": t["status"], "source": t["source"]})
        if t["url"]:
            seen_urls.add(t["url"])
    return sites, unresolved


def is_js_app(site):
    return site.get("status") == "js-app" or any(h in site["url"] for h in JS_APP_HINTS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true",
                    help="reconcile registry with the sheet, write template URLs, report gaps")
    ap.add_argument("--curl-only", action="store_true",
                    help="skip JS-app sites (they need the @browser DOM sweep)")
    args = ap.parse_args()

    token = get_token()
    sites, unresolved = build_registry(token)

    if args.sync:
        # persist all auto-resolved entries (brokerage/template/residential) so
        # they resolve instantly next time and don't re-appear as gaps
        reg = json.loads(REGISTRY.read_text())
        known = {(s["broker"].lower(), s["url"]) for s in reg["sites"]}
        added = [s for s in sites if s.get("source") in ("template", "brokerage", "residential")
                 and (s["broker"].lower(), s["url"]) not in known]
        reg["sites"].extend(added)
        REGISTRY.write_text(json.dumps(reg, indent=2))
        by_src = {}
        for s in added:
            by_src[s["source"]] = by_src.get(s["source"], 0) + 1
        print(f"registry synced: +{len(added)} auto-resolved "
              f"({', '.join(f'{v} {k}' for k, v in by_src.items()) or 'none'}), "
              f"{len(reg['sites'])} total entries")
        print(f"\n⚠️  {len(unresolved)} broker(s) need agent URL discovery "
              f"(CRE firm, no known brokerage page):")
        for b in unresolved:
            print(f"  • {b['name']} — {b['brokerage'] or '(no brokerage)'}")
        print("\nHand these to the discovery agents (/broker-search → broker-site coverage), "
              "then append name|url|type to references/broker-sites.json.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = bad = skipped = 0
    for site in sites:
        if not site.get("url") or site.get("status") in ("none", "404"):
            continue  # no page (residential agent) or known-dead — skip
        if args.curl_only and is_js_app(site):
            skipped += 1
            continue
        try:
            r = requests.get(site["url"], headers=HEADERS, timeout=25, allow_redirects=True)
            status = r.status_code
        except requests.RequestException as e:
            status = f"error: {e.__class__.__name__}"
        if status == 200:
            path = OUT_DIR / f"{slug(site['broker'])}.txt"
            tag = "  [JS-APP: shell only, use @browser]" if is_js_app(site) else ""
            path.write_text(f"SOURCE: {site['url']}\nBROKER: {site['broker']} "
                            f"({site['brokerage']}){tag}\n\n{to_text(r.text)}")
            ok += 1
        else:
            print(f"  ❌ {site['broker']} — {status} ({site['url']})")
            bad += 1
        time.sleep(1)

    print(f"\n{ok} fetched → {OUT_DIR}  |  {bad} failed  |  {skipped} JS-app skipped")
    js = [s["broker"] for s in sites if is_js_app(s)]
    if js and not args.curl_only:
        print(f"\n{len(js)} JS-app site(s) saved as shells — extract via @browser DOM sweep:")
        print("  " + ", ".join(js[:12]) + (" …" if len(js) > 12 else ""))
    if unresolved:
        print(f"\n⚠️  {len(unresolved)} broker(s) still need a listings URL — run --sync to list them.")
    print("\nNext: extract listings from the .txt files, screen vs buy box, "
          "cross-check analyzed_deals.py, flag pre-portal (not on crexi_live --deals).")


if __name__ == "__main__":
    main()
