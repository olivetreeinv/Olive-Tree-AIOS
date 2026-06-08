#!/usr/bin/env python3
"""
Rentometer market rent lookup — Olive Tree Investments

Usage (standalone):
  python3 scripts/rentometer.py --address "123 Main St, Nashville TN 37207" \
      --beds 2 --om-rent 1200

  python3 scripts/rentometer.py --address "..." --beds 1 --baths 1 --om-rent 950
  python3 scripts/rentometer.py --address "..." --beds 3 --baths "1.5+" --om-rent 1600

Usage (as module):
  import sys; sys.path.insert(0, "scripts")
  import rentometer
  result = rentometer.lookup(address="123 Main St...", beds=2, om_rent=1200)
  # result["median"], result["mean"], result["percentile_75"], etc.

Requirements:
  pip3 install requests python-dotenv
  RENTOMETER_API_KEY set in .env

To get your API key:
  1. Log in at rentometer.com
  2. Tools → API Settings → accept Terms of Use
  3. Copy key → add to .env as RENTOMETER_API_KEY=your_key
  (Included free with Pro Standard — no extra charge)
"""

import argparse
import json
import os
import sys

import requests

try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    load_dotenv(_env)
except ImportError:
    pass

RENTOMETER_BASE = "https://www.rentometer.com/api/v1"


def _api_key():
    key = os.getenv("RENTOMETER_API_KEY", "").strip()
    if not key:
        print("ERROR: RENTOMETER_API_KEY not set in .env")
        print("  1. Log in at rentometer.com")
        print("  2. Tools → API Settings → accept Terms of Use")
        print("  3. Copy key → paste into .env: RENTOMETER_API_KEY=your_key_here")
        sys.exit(1)
    return key


def check_auth():
    """Verify API key and return account info. Free — costs 0 credits."""
    r = requests.get(f"{RENTOMETER_BASE}/auth",
                     params={"api_key": _api_key()}, timeout=10)
    if r.status_code == 401:
        print("ERROR: Invalid Rentometer API key. Check RENTOMETER_API_KEY in .env")
        sys.exit(1)
    r.raise_for_status()
    return r.json()


def lookup(address, beds, baths=None, building_type=None, om_rent=None):
    """
    Query Rentometer /summary for one address + bedroom type. Costs 1 QuickView credit.

    Returns dict with: mean, median, min, max, percentile_25, percentile_75,
    std_dev, sample_size, radius_miles, normalized_address, quickview_url,
    credits_remaining, bedrooms, baths.

    If om_rent provided, also includes: om_rent, vs_median, vs_median_pct,
    vs_mean, vs_mean_pct, om_assessment.

    Returns None if no data found for that address/bedroom combo.
    """
    api_key = _api_key()
    params = {"api_key": api_key, "address": address, "bedrooms": beds}
    if baths:
        params["baths"] = baths
    if building_type:
        params["building_type"] = building_type

    r = requests.get(f"{RENTOMETER_BASE}/summary", params=params, timeout=15)

    if r.status_code == 401:
        print("ERROR: Invalid Rentometer API key.")
        sys.exit(1)
    if r.status_code == 402:
        print("ERROR: No Rentometer credits remaining. Check your plan.")
        sys.exit(1)
    if r.status_code == 404:
        return None
    r.raise_for_status()

    data = r.json()
    result = {
        "mean":               data.get("mean"),
        "median":             data.get("median"),
        "min":                data.get("min"),
        "max":                data.get("max"),
        "percentile_25":      data.get("percentile_25"),
        "percentile_75":      data.get("percentile_75"),
        "std_dev":            data.get("std_dev"),
        "sample_size":        data.get("sample_size"),
        "radius_miles":       data.get("radius"),
        "normalized_address": data.get("normalized_address"),
        "quickview_url":      data.get("quickview_url"),
        "credits_remaining":  data.get("credits_remaining"),
        "bedrooms":           beds,
        "baths":              baths,
    }

    if om_rent and result["median"]:
        delta_med  = om_rent - result["median"]
        pct_med    = (om_rent / result["median"] - 1) * 100
        delta_mean = (om_rent - result["mean"]) if result["mean"] else None
        pct_mean   = ((om_rent / result["mean"] - 1) * 100) if result["mean"] else None

        p75 = result.get("percentile_75")
        if p75 is not None and om_rent > p75:
            assessment = "AGGRESSIVE — above 75th percentile"
        elif om_rent >= result["median"]:
            assessment = "REASONABLE — at or above median"
        else:
            assessment = "CONSERVATIVE — below median"

        result.update({
            "om_rent":       om_rent,
            "vs_median":     delta_med,
            "vs_median_pct": pct_med,
            "vs_mean":       delta_mean,
            "vs_mean_pct":   pct_mean,
            "om_assessment": assessment,
        })

    return result


def _money(v):
    """Format a nullable numeric as $X,XXX/mo — safe on partial API responses."""
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "N/A"


def print_report(result, beds, baths=None):
    """Print a formatted market rent report to stdout."""
    if not result:
        print("  No Rentometer data for this address/bedroom combo.")
        print("  Check that the address is fully formed (include zip code).")
        return

    bed_label  = f"{beds}BR"
    bath_label = f" / {baths} ba" if baths else ""

    print(f"\n{'─'*54}")
    print(f"  RENTOMETER MARKET RENTS — {bed_label}{bath_label}")
    print(f"{'─'*54}")
    if result.get("normalized_address"):
        print(f"  Address : {result['normalized_address']}")
    print(f"  Radius  : {result['radius_miles']} mi  |  Samples: {result['sample_size']}")
    print()
    print(f"  {'Metric':<24} {'Rent/mo':>10}")
    print(f"  {'─'*24} {'─'*10}")
    print(f"  {'Mean':<24} {_money(result.get('mean')):>10}")
    print(f"  {'Median':<24} {_money(result.get('median')):>10}")
    print(f"  {'25th Percentile':<24} {_money(result.get('percentile_25')):>10}")
    print(f"  {'75th Percentile':<24} {_money(result.get('percentile_75')):>10}")
    print(f"  {'Min':<24} {_money(result.get('min')):>10}")
    print(f"  {'Max':<24} {_money(result.get('max')):>10}")

    if result.get("om_rent"):
        sign_m = "+" if result["vs_median"] >= 0 else ""
        print()
        print(f"  {'─'*36}")
        print(f"  OM Asking Rent : ${result['om_rent']:,.0f}/mo")
        print(f"  vs. Median     : {sign_m}${result['vs_median']:,.0f}  ({sign_m}{result['vs_median_pct']:.1f}%)")
        if result.get("vs_mean") is not None:
            sign_a = "+" if result["vs_mean"] >= 0 else ""
            print(f"  vs. Mean       : {sign_a}${result['vs_mean']:,.0f}  ({sign_a}{result['vs_mean_pct']:.1f}%)")
        emoji = "⚠️ " if "AGGRESSIVE" in result.get("om_assessment", "") else "✅"
        print(f"  Assessment     : {emoji} {result['om_assessment']}")

    if result.get("quickview_url"):
        print(f"\n  Full report    : {result['quickview_url']}")
    if result.get("credits_remaining") is not None:
        print(f"  Credits left   : {result['credits_remaining']}")
    print(f"{'─'*54}\n")


def main():
    p = argparse.ArgumentParser(description="Rentometer market rent lookup")
    p.add_argument("--address",  required=True,
                   help="Full property address including zip code")
    p.add_argument("--beds",     required=True, type=int, choices=[1, 2, 3, 4],
                   help="Bedrooms (1–4)")
    p.add_argument("--baths",    type=str, choices=["1", "1.5+"],
                   help="Bath filter: '1' or '1.5+' (optional)")
    p.add_argument("--om-rent",  type=float,
                   help="OM asking rent per unit/mo — compares against market comps")
    p.add_argument("--type",     type=str, choices=["apartment", "house"],
                   help="Building type filter (optional)")
    p.add_argument("--json",     action="store_true", help="Output raw JSON")
    args = p.parse_args()

    result = lookup(
        address=args.address,
        beds=args.beds,
        baths=args.baths,
        building_type=args.type,
        om_rent=args.om_rent,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result, args.beds, args.baths)


if __name__ == "__main__":
    main()
