#!/usr/bin/env python3
"""
Olive Tree — Land Comps (the Avg $/Acre column engine)

Computes a median $/acre comp for a zip — the market number the offer prices
under — and (optionally) writes it into the Land Builders tab's "Avg $/Acre
(Comp)" column for every builder covering that zip.

Two sources, best-available:
  1. LISTINGS (retail)  — MLS active land listings via the FMLS/Bridge API
     (land_markets.fmls_median_ppa). The number builders actually pay. GA only
     today (FMLS dataset); returns None elsewhere.
  2. PARCEL ASSESSED (basis) — median(land_value / acres) over vacant parcels in
     the zip's buildable band, from the same county GIS / ReportAll pull the
     seller list uses. Works for every wired source; assessed lags market, so
     treat it as a floor, not retail.

Reported comp = listings when available, else assessed (flagged).

NOTE on Zillow: direct Zillow/portal scraping is blocked in this sandbox (403 —
the same wall that stops listing photos) and breaks Zillow's ToS, so it is NOT
used here. The two sources above are free and authoritative. A true multi-state
retail-listing feed is a paid API (Bridge per-MLS, or a RapidAPI Zillow endpoint
~$30-75/mo) — add only if assessed + FMLS prove insufficient per market.

Usage:
  python3 scripts/land_comps.py --zip 30120 --county bartow-ga
  python3 scripts/land_comps.py --zip 30120 --county bartow-ga --write
  python3 scripts/land_comps.py --zip 30120 --county bartow-ga --json
"""

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import land_parcels as lp                       # noqa: E402
from land_markets import fmls_median_ppa        # noqa: E402
from land_sheets import get_token, read_rows, upsert_row  # noqa: E402

BUILDERS_TAB = "Land Builders"
MARKETS_COL = 6   # Land Builders: Markets/Zips
AVG_ACRE_COL = 7  # Land Builders: Avg $/Acre (Comp)


def assessed_ppa(zip_code, county, min_acres=1.0, max_acres=10.0):
    """Median assessed $/acre over vacant, in-band parcels. (value, n)."""
    recs = lp.query_parcels(county, zip_code=zip_code, vacant_only=True)
    vals = []
    for r in recs:
        lv, ac = r.get("land_value"), r.get("acres")
        if not lv or not ac or ac <= 0:
            continue
        if ac < min_acres or ac > max_acres:
            continue
        if not lp.is_vacant(r):                  # Python-side safety net
            continue
        vals.append(lv / ac)
    if len(vals) < 3:                            # too thin to trust a median
        return None, len(vals)
    return round(statistics.median(vals)), len(vals)


def comp_for_zip(zip_code, county, min_acres=1.0, max_acres=10.0):
    """Comp signals + the best single number for the column.

    Preference: SOLD comps (what actually closed) > assessed basis. Asking-price
    listings are kept only as a secondary reference — they overstate (sellers ask
    high) and skew worse the thinner the market.
    """
    sold = fmls_median_ppa(zip_code, min_acres, max_acres,
                           status="Closed", price_field="ClosePrice")
    asking = fmls_median_ppa(zip_code, min_acres, max_acres)  # Active/ListPrice
    assessed, n = assessed_ppa(zip_code, county, min_acres, max_acres)
    best = sold if sold else assessed
    return {
        "zip": zip_code, "county": county,
        "sold_ppa": sold, "asking_ppa": asking,
        "assessed_ppa": assessed, "assessed_n": n,
        "comp": best,
        "comp_source": "sold" if sold else ("assessed" if assessed else None),
    }


def write_to_builders(token, zip_code, comp):
    """Set Avg $/Acre for every builder whose Markets contains the zip."""
    rows = read_rows(token, BUILDERS_TAB)
    if not rows:
        return 0
    header, written = rows[0], 0
    for r in rows[1:]:
        markets = r[MARKETS_COL] if len(r) > MARKETS_COL else ""
        if zip_code not in markets:
            continue
        r = r + [""] * (len(header) - len(r))    # pad to full width
        r[AVG_ACRE_COL] = str(comp)
        upsert_row(token, BUILDERS_TAB, 0, r[0], r)  # dedup on builder name
        written += 1
    return written


def main():
    ap = argparse.ArgumentParser(description="Median $/acre comp for a zip.")
    ap.add_argument("--zip", dest="zip_code", required=True)
    ap.add_argument("--county", default="bartow-ga", choices=sorted(lp.COUNTIES),
                    help="County GIS config for the assessed pull (default bartow-ga)")
    ap.add_argument("--min-acres", type=float, default=1.0)
    ap.add_argument("--max-acres", type=float, default=10.0)
    ap.add_argument("--write", action="store_true",
                    help="Write the comp into the Land Builders Avg $/Acre column")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    c = comp_for_zip(a.zip_code, a.county, a.min_acres, a.max_acres)

    if a.json:
        import json
        print(json.dumps(c))
    else:
        sold = f"${c['sold_ppa']:,}/ac" if c["sold_ppa"] else "—"
        ask = f"${c['asking_ppa']:,}/ac" if c["asking_ppa"] else "—"
        asd = f"${c['assessed_ppa']:,}/ac (n={c['assessed_n']})" if c["assessed_ppa"] \
            else f"— (n={c['assessed_n']}, need ≥3)"
        print(f"  Zip {a.zip_code} ({a.county})")
        print(f"  Sold comps:         {sold}   ← MLS closed, GA only (true comp)")
        print(f"  Asking (reference): {ask}   ← MLS active; overstates")
        print(f"  Assessed (basis):   {asd}")
        comp = f"${c['comp']:,}/ac" if c["comp"] else "no comp available"
        print(f"  → Comp: {comp}" + (f"  [{c['comp_source']}]" if c["comp"] else ""))

    if a.write:
        if not c["comp"]:
            print("  Nothing to write — no comp available.")
            return
        n = write_to_builders(get_token(), a.zip_code, c["comp"])
        print(f"  Wrote ${c['comp']:,}/ac to {n} builder row(s) covering {a.zip_code}.")


if __name__ == "__main__":
    main()
