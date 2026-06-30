#!/usr/bin/env python3
"""
Olive Tree — Land Markets (the /land-scout engine)

Screens a zip for land-wholesaling viability straight from county parcel data
and writes a Go/No-Go to the Land Markets tab. Replaces eyeballing Zillow with
the three data-driven tests from references/land-wholesale-buy-box.md:

  1. Building demand   — new construction present (builder signal; partly manual)
  2. Uniform inventory — cookie-cutter score (acreage CV → uniformity 0–1)
  3. Absentee pool     — count of vacant + out-of-state-owned lots (the seller)

Verdict is driven primarily by the absentee seller pool (what actually makes a
market wholesalable), with uniformity + lot economics as context.

Usage:
  python3 scripts/land_markets.py --zip 30120                 # screen + log
  python3 scripts/land_markets.py --zip 30120 --dry-run       # screen, no write
  python3 scripts/land_markets.py --zip 30120 --json          # machine output
  python3 scripts/land_markets.py --county forsyth-ga --zip 30040 --dry-run
"""

import argparse
import json
import os
import statistics
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

import land_parcels as lp

load_dotenv(Path(__file__).parent.parent / ".env")

def fmls_median_ppa(zip_code):
    """Return FMLS median active $/acre for a zip, or None if unavailable."""
    token = os.getenv("FMLS_API_TOKEN", "")
    dataset = os.getenv("FMLS_DATASET_ID", "fmls")
    if not token:
        return None
    base = f"https://api.bridgedataoutput.com/api/v2/OData/{dataset}"
    params = {
        "$filter": (
            f"PropertyType eq 'Land' and StandardStatus eq 'Active'"
            f" and PostalCode eq '{zip_code}'"
        ),
        "$select": "ListPrice,LotSizeAcres",
        "$top": 200,
    }
    url, ppa_vals = f"{base}/Property", []
    pages = 0
    while url and pages < 10:
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                             params=params, timeout=20)
            r.raise_for_status()
        except Exception:
            break
        data = r.json()
        for prop in data.get("value", []):
            p = prop.get("ListPrice") or 0
            a = prop.get("LotSizeAcres") or 0
            if p > 0 and a > 0:
                ppa_vals.append(p / a)
        url, params = data.get("@odata.nextLink"), None
        pages += 1
    return round(statistics.median(ppa_vals)) if len(ppa_vals) >= 3 else None


# Verdict thresholds on the vacant + out-of-state seller pool (per zip).
GO_MIN = 50      # >= this many absentee vacant lots -> GO
WATCH_MIN = 10   # WATCH band; below -> NO-GO

# Default seller acreage band per county (buy-box.md). Bartow = rural 1–10 ac.
DEFAULT_BAND = {"bartow-ga": (1.0, 10.0), "forsyth-ga": (0.1, 2.0)}


def screen_zip(county, zip_code, band=None, sample_cap=3000):
    """Exact server counts for the headline numbers; a sample for acreage stats."""
    cfg = lp.COUNTIES[county]
    lo, hi = band or DEFAULT_BAND.get(county, (0.1, 10.0))
    bbox = lp.resolve_bbox(county, zip_code)

    # Headline counts — exact, server-side.
    total = lp.count_parcels(county, bbox=bbox, zip_code=zip_code)
    vacant = lp.count_parcels(county, bbox=bbox, zip_code=zip_code, vacant_only=True)
    n = lp.count_parcels(county, bbox=bbox, zip_code=zip_code,
                         vacant_only=True, out_of_state=True)

    # Stats — from a representative sample of vacant out-of-state lots.
    sample = lp.query_parcels(county, bbox=bbox, zip_code=zip_code,
                              vacant_only=True, max_records=sample_cap)
    sample = [r for r in sample if lp.is_out_of_state(r, cfg["state"])]
    band_lots = [r for r in sample if r["acres"] is not None and lo <= r["acres"] <= hi]
    stats = lp.acre_stats(band_lots or sample)
    vals = [r["land_value"] for r in band_lots if r.get("land_value")]
    avg_val = round(sum(vals) / len(vals)) if vals else None

    verdict = "GO" if n >= GO_MIN else ("WATCH" if n >= WATCH_MIN else "NO-GO")
    # Score 0–100: absentee pool (capped at 100) is the spine; uniformity nudges.
    score = round(min(n, 100) * 0.8 + (stats.get("uniformity") or 0) * 20, 1)

    ppa = fmls_median_ppa(zip_code)

    return {
        "county": county,
        "zip": zip_code,
        "state": cfg["state"],
        "total_parcels": total,
        "vacant_lots": vacant,
        "vacant_oos": n,
        "band": f"{lo}-{hi} ac",
        "band_lots": len(band_lots),
        "uniformity": stats.get("uniformity"),
        "median_acres": stats.get("median"),
        "avg_land_value": avg_val,
        "go_nogo": verdict,
        "score": score,
        "fmls_median_ppa": ppa,
    }


def _row(m, city=""):
    """Land Markets tab row order (see land_setup.TABS)."""
    return [
        m["county"], m["zip"], city, m["state"], m["total_parcels"],
        m["vacant_lots"], m["vacant_oos"], m["uniformity"], m["median_acres"],
        m["avg_land_value"], "(call builders)", m["go_nogo"], m["score"],
        f"seller band {m['band']}: {m['band_lots']} lots", date.today().isoformat(),
        m.get("fmls_median_ppa") or "",
    ]


def main():
    ap = argparse.ArgumentParser(description="Screen a zip for land-wholesaling viability.")
    ap.add_argument("--zip", dest="zip_code", required=True)
    ap.add_argument("--county", default="bartow-ga", choices=sorted(lp.COUNTIES))
    ap.add_argument("--city", default="", help="City label for the log row")
    ap.add_argument("--min-acres", type=float, help="Override seller band low")
    ap.add_argument("--max-acres", type=float, help="Override seller band high")
    ap.add_argument("--dry-run", action="store_true", help="Screen without writing")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    args = ap.parse_args()

    band = None
    if args.min_acres is not None and args.max_acres is not None:
        band = (args.min_acres, args.max_acres)

    m = screen_zip(args.county, args.zip_code, band)

    if args.json:
        print(json.dumps(m, indent=2))
    else:
        print(f"\n  {lp.COUNTIES[args.county]['name']} — zip {m['zip']}")
        print(f"  {'─'*46}")
        print(f"  Total parcels        {m['total_parcels']:>8,}")
        print(f"  Vacant lots          {m['vacant_lots']:>8,}")
        print(f"  Vacant + out-of-state{m['vacant_oos']:>8,}   ← seller pool")
        print(f"  In band ({m['band']}) {m['band_lots']:>8,}")
        print(f"  Cookie-cutter unif.  {str(m['uniformity']):>8}")
        print(f"  Median acres         {str(m['median_acres']):>8}")
        av = f"${m['avg_land_value']:,}" if m['avg_land_value'] else "—"
        print(f"  Avg land value       {av:>8}")
        ppa = f"${m['fmls_median_ppa']:,}/ac" if m.get("fmls_median_ppa") else "—"
        print(f"  FMLS median $/acre   {ppa:>8}   ← MLS active listings")
        print(f"  {'─'*46}")
        print(f"  VERDICT: {m['go_nogo']}   (score {m['score']}/100)")
        print(f"  Next: call builders in {m['zip']} for a buy box, then /land-sellers\n")

    if args.dry_run:
        return

    # Write to sheet (upsert on county|zip) + mirror to DB.
    from land_sheets import get_token, upsert_row
    token = get_token()
    # composite key isn't a single column; dedup on zip within the tab is fine here
    upsert_row(token, "Land Markets", 1, m["zip"], _row(m, args.city))
    print(f"  Logged to Land Markets tab.")

    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from db.connection import get_session
        from db.schema import LandMarket
        s = get_session()
        existing = s.query(LandMarket).filter_by(county=m["county"], zip=m["zip"]).first()
        obj = existing or LandMarket(county=m["county"], zip=m["zip"])
        obj.city = args.city
        obj.state = m["state"]
        obj.total_parcels = m["total_parcels"]
        obj.vacant_lots = m["vacant_lots"]
        obj.vacant_oos = m["vacant_oos"]
        obj.uniformity = m["uniformity"]
        obj.median_acres = m["median_acres"]
        obj.avg_land_value = m["avg_land_value"]
        obj.go_nogo = m["go_nogo"]
        obj.score = m["score"]
        obj.date = date.today().isoformat()
        if not existing:
            s.add(obj)
        s.commit()
        s.close()
    except Exception as e:  # DB mirror is best-effort; sheet is source of truth
        print(f"  (DB mirror skipped: {e})")


if __name__ == "__main__":
    main()
