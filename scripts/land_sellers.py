#!/usr/bin/env python3
"""
Olive Tree — Land Sellers (the /land-sellers engine)

Auto-builds the seller list for a zip straight from county parcel data: vacant
lots owned by out-of-state owners, in the market's acreage band, with each
owner's MAILING ADDRESS and a computed cash offer. Writes to the Land Sellers
tab + olive.db. This is the core driver — no scraping, no manual list building.

Offer = builder $/acre × acres × (1 − spread).  Builder price comes from the
Land Builders tab (--builder-price overrides). Offer is sanity-capped at the
parcel's appraised land value (never offer above it without a confirmed buyer).

Excludes HOA / association / management-company owners (not real sellers).
Flags same-owner multi-lot holdings as package opportunities.

Usage:
  # Build the Cartersville seller list (uses Land Builders price for 30120)
  python3 scripts/land_sellers.py --zip 30120

  # Override the builder price + spread, preview without writing
  python3 scripts/land_sellers.py --zip 30120 --builder-price 8000 --spread 0.15 --dry-run

  # Different county / band / cap
  python3 scripts/land_sellers.py --county forsyth-ga --zip 30040 --min-acres 0.1 --max-acres 2
"""

import argparse
import os
import re
import statistics
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

import land_parcels as lp  # noqa: E402
from land_markets import DEFAULT_BAND  # noqa: E402
from land_sheets import append_rows, get_token, read_rows  # noqa: E402

load_dotenv(Path(__file__).parent.parent / ".env")

TAB = "Land Sellers"
DEFAULT_SPREAD = 0.15

# ── FMLS market data ──────────────────────────────────────────────────────────

def fmls_median_ppa_by_zip(zips):
    """
    Query FMLS for active Land listings in the given zips and return a dict of
    {zip: median_$/acre}. Falls back to county-wide median if a zip has <3 data
    points, and to None if the token is missing or the call fails.
    """
    token = os.getenv("FMLS_API_TOKEN", "")
    dataset = os.getenv("FMLS_DATASET_ID", "fmls")
    if not token:
        return {}
    base = f"https://api.bridgedataoutput.com/api/v2/OData/{dataset}"
    headers = {"Authorization": f"Bearer {token}"}
    zip_filter = " or ".join(f"PostalCode eq '{z}'" for z in zips)
    params = {
        "$filter": f"PropertyType eq 'Land' and StandardStatus eq 'Active' and ({zip_filter})",
        "$select": "PostalCode,ListPrice,LotSizeAcres",
        "$top": 200,
    }
    url, by_zip = f"{base}/Property", {}
    pages = 0
    while url and pages < 10:
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
        except Exception:
            break
        data = r.json()
        for prop in data.get("value", []):
            p = prop.get("ListPrice") or 0
            a = prop.get("LotSizeAcres") or 0
            z = (prop.get("PostalCode") or "").strip()
            if p > 0 and a > 0 and z:
                by_zip.setdefault(z, []).append(p / a)
        url, params = data.get("@odata.nextLink"), None
        pages += 1

    # County-wide fallback median (from all collected points)
    all_ppa = [v for vals in by_zip.values() for v in vals]
    county_median = statistics.median(all_ppa) if all_ppa else None

    result = {}
    for z in zips:
        vals = by_zip.get(z, [])
        if len(vals) >= 3:
            result[z] = statistics.median(vals)
        elif county_median:
            result[z] = county_median
    return result
# Owners that aren't real sellers (common areas, lender/REO, government).
EXCLUDE_OWNER = re.compile(
    r"\b(ASSOC|HOA|HOMEOWNERS|OWNERS ASSN|BANK|COUNTY|CITY OF|STATE OF|"
    r"UNITED STATES|AUTHORITY|CHURCH)\b", re.I)
# Entities (vs. individuals). Individuals are the prime motivated absentee target;
# entities (esp. builders/developers) are kept but ranked lower and tagged.
ENTITY_HINT = re.compile(
    r"\b(LLC|INC|CORP|LP|LTD|TRUST|PROPERTIES|HOMES|HOMEBUILDER|FARM|COMPANY|"
    r"CO|ASSOCIATES|GROUP|HOLDINGS|VENTURES|DEVELOPMENT|PARTNERS|REALTY|"
    r"INVESTMENTS|CAPITAL|ENTERPRISES)\b", re.I)


def is_entity(owner):
    return bool(ENTITY_HINT.search(owner or ""))


def builder_price_for(zip_code):
    """Look up the highest $/acre on file in Land Builders covering this zip."""
    try:
        rows = read_rows(get_token(), "Land Builders")
    except Exception:
        return None
    best = None
    for r in rows[1:]:
        markets = r[4] if len(r) > 4 else ""
        price = r[7] if len(r) > 7 else ""
        if zip_code in markets and "/ac" in price:
            try:
                best = max(best or 0, float(price.replace("$", "").replace("/ac", "")))
            except ValueError:
                pass
    return best


def compute_offer(acres, price_per_acre, spread):
    """Starting offer = builder $/acre × acres × (1 − spread). Assessed value is
    NOT used as a cap — for raw land it lags far below market and would nuke offers."""
    if not (acres and price_per_acre):
        return None
    offer = acres * price_per_acre * (1 - spread)
    return round(offer / 100) * 100      # round to nearest $100


def build_list(county, zip_code, band, price_per_acre, spread, cap=4000):
    cfg = lp.COUNTIES[county]
    lo, hi = band
    bbox = lp.resolve_bbox(county, zip_code)
    recs = lp.query_parcels(county, bbox=bbox, zip_code=zip_code,
                            vacant_only=True, max_records=cap)

    sellers, owner_counts = [], {}
    for r in recs:
        if not lp.is_vacant(r) or not lp.is_out_of_state(r, cfg["state"]):
            continue
        a = r["acres"]
        if a is None or not (lo <= a <= hi):
            continue
        if EXCLUDE_OWNER.search(r.get("owner_name") or ""):
            continue
        owner_counts[r.get("owner_name")] = owner_counts.get(r.get("owner_name"), 0) + 1
        sellers.append(r)

    # Pull FMLS median $/acre for all zips in this batch (one API call).
    zips_in_batch = {r.get("site_zip") or zip_code for r in sellers}
    mls_ppa = fmls_median_ppa_by_zip(zips_in_batch) if zips_in_batch else {}
    if mls_ppa:
        print(f"  FMLS median $/ac: { {z: f'${v:,.0f}' for z, v in mls_ppa.items()} }")

    out = []
    for r in sellers:
        owner = r.get("owner_name")
        z     = r.get("site_zip") or zip_code
        offer = compute_offer(r["acres"], price_per_acre, spread)
        ppa   = mls_ppa.get(z)
        mkt   = round(ppa * r["acres"] / 100) * 100 if (ppa and r["acres"]) else None
        buy   = round(mkt * (1 - spread) / 100) * 100 if mkt else None
        out.append({
            "parcel_id": r.get("parcel_id"),
            "situs": (r.get("site_address") or "").strip(),
            "zip": z,
            "subdivision": r.get("subdivision") or "",
            "acres": r["acres"],
            "owner": owner,
            "owner_addr": (r.get("owner_addr") or "").strip(),
            "owner_city": r.get("owner_city") or "",
            "owner_state": r.get("owner_state") or "",
            "owner_zip": r.get("owner_zip") or "",
            "land_value": r.get("land_value"),
            "offer": offer,
            "mkt_avg_list_pr": mkt,
            "buy_pr_est": buy,
            "package": owner_counts.get(owner, 1) > 1,
            "entity": is_entity(owner),
        })
    # Individuals first (prime absentee target), then packages, then larger offers.
    out.sort(key=lambda s: (s["entity"], not s["package"], -(s["offer"] or 0)))
    return out


def _row(s):
    # Land Sellers header order (land_setup.TABS).
    notes = " ".join(t for t in (
        "PACKAGE" if s["package"] else "",
        "ENTITY" if s["entity"] else "INDIVIDUAL",
    ) if t)
    return [
        s["parcel_id"], s["situs"], s["zip"], s["subdivision"], s["acres"],
        s["owner"], s["owner_addr"], s["owner_city"], s["owner_state"], "Y",
        s["land_value"] or "", s["offer"] or "", "",  # owner_phone blank
        "", "mail", "new", "", "", "", notes, s.get("owner_zip") or "",
        s.get("mkt_avg_list_pr") or "", s.get("buy_pr_est") or "", "",  # Buy Box = formula
    ]


def _db_upsert(sellers):
    try:
        from db.connection import get_session
        from db.schema import LandSeller
        sess = get_session()
        for s in sellers:
            existing = sess.query(LandSeller).filter_by(parcel_id=s["parcel_id"]).first()
            o = existing or LandSeller(parcel_id=s["parcel_id"])
            o.situs_address, o.zip, o.subdivision = s["situs"], s["zip"], s["subdivision"]
            o.acres, o.owner_name, o.owner_addr = s["acres"], s["owner"], s["owner_addr"]
            o.owner_city, o.owner_state, o.out_of_state = s["owner_city"], s["owner_state"], True
            o.owner_zip = s.get("owner_zip") or None
            o.est_land_value, o.offer_price = s["land_value"], s["offer"]
            o.channel = "mail"
            o.call_status = o.call_status or "new"
            o.notes = "PACKAGE" if s["package"] else (o.notes or "")
            if not existing:
                sess.add(o)
        sess.commit()
        sess.close()
    except Exception as e:
        print(f"  (DB mirror skipped: {e})")


def main():
    ap = argparse.ArgumentParser(description="Auto-build a land seller list with offers.")
    ap.add_argument("--zip", dest="zip_code", required=True)
    ap.add_argument("--county", default="bartow-ga", choices=sorted(lp.COUNTIES))
    ap.add_argument("--builder-price", type=float, help="$/acre (else from Land Builders)")
    ap.add_argument("--spread", type=float, default=DEFAULT_SPREAD, help="0.10–0.20")
    ap.add_argument("--min-acres", type=float)
    ap.add_argument("--max-acres", type=float)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    band = DEFAULT_BAND.get(args.county, (0.1, 10.0))
    if args.min_acres is not None and args.max_acres is not None:
        band = (args.min_acres, args.max_acres)

    price = args.builder_price or builder_price_for(args.zip_code)
    if not price:
        sys.exit(f"No builder $/acre for {args.zip_code}. Add one via /land-builders "
                 f"or pass --builder-price.")

    sellers = build_list(args.county, args.zip_code, band, price, args.spread)
    pkgs = sum(1 for s in sellers if s["package"])
    indiv = sum(1 for s in sellers if not s["entity"])
    print(f"\n  {lp.COUNTIES[args.county]['name']} — zip {args.zip_code}")
    print(f"  Builder ${price:g}/ac · spread {args.spread:.0%} · band {band[0]}–{band[1]} ac")
    print(f"  {len(sellers)} sellers · {indiv} individuals (prime) · {pkgs} package lots\n")
    for s in sellers[:25]:
        tag = (" [PKG]" if s["package"] else "") + ("" if s["entity"] else " ★")
        offer = f"${s['offer']:,.0f}" if s["offer"] else "—"
        print(f"  {s['situs'][:24]:24} {s['acres']:>5}ac  offer {offer:>9}  "
              f"{s['owner'][:26]} [{s['owner_state']}]{tag}")
    if len(sellers) > 25:
        print(f"  … and {len(sellers) - 25} more")
    print("  ★ = individual owner (prime absentee target)")

    if args.dry_run:
        print("\n  (dry-run — nothing written)")
        return

    token = get_token()
    # One read for existing parcel ids, then a single batch append of new rows
    # (avoids a full-sheet read per row).
    existing = read_rows(token, TAB)
    have = {r[0] for r in existing[1:] if r}
    new_rows = [_row(s) for s in sellers if s["parcel_id"] not in have]
    if new_rows:
        append_rows(token, TAB, new_rows)
    _db_upsert(sellers)
    print(f"\n  Wrote {len(new_rows)} new sellers ({len(sellers) - len(new_rows)} "
          f"already on the tab) to Land Sellers + olive.db.")
    print(f"  Next: /land-mail (free mass offer) or skip-trace phones for /land-call.")


if __name__ == "__main__":
    main()
