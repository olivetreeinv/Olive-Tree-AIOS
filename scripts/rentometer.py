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

Auth modes (in priority order):
  1. API key  — set RENTOMETER_API_KEY in .env  (1 QuickView credit per call)
  2. Web login — set RENTOMETER_EMAIL + RENTOMETER_PASSWORD in .env (free, no credits)
                 Playwright navigates rentometer.com under Brian's account.

Requirements:
  pip3 install requests beautifulsoup4 python-dotenv playwright
  playwright install chromium  (first-time only)
"""

import argparse
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    load_dotenv(_env)
except ImportError:
    pass

RENTOMETER_BASE = "https://www.rentometer.com/api/v1"
RENTOMETER_WEB  = "https://www.rentometer.com"


# ---------------------------------------------------------------------------
# API path (unchanged — keeps downstream callers working when key is set)
# ---------------------------------------------------------------------------

def _api_key():
    return os.getenv("RENTOMETER_API_KEY", "").strip()


def _lookup_api(address, beds, baths=None, building_type=None):
    """Query Rentometer REST API — costs 1 QuickView credit."""
    key = _api_key()
    params = {"api_key": key, "address": address, "bedrooms": beds}
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
    d = r.json()
    return {
        "mean":               d.get("mean"),
        "median":             d.get("median"),
        "min":                d.get("min"),
        "max":                d.get("max"),
        "percentile_25":      d.get("percentile_25"),
        "percentile_75":      d.get("percentile_75"),
        "std_dev":            d.get("std_dev"),
        "sample_size":        d.get("sample_size"),
        "radius_miles":       d.get("radius"),
        "normalized_address": d.get("normalized_address"),
        "quickview_url":      d.get("quickview_url"),
        "credits_remaining":  d.get("credits_remaining"),
    }


# ---------------------------------------------------------------------------
# Web-login path — Playwright (no API key required)
# ---------------------------------------------------------------------------

def _web_credentials():
    email    = os.getenv("RENTOMETER_EMAIL", "").strip()
    password = os.getenv("RENTOMETER_PASSWORD", "").strip()
    if not email or not password:
        return None, None
    return email, password


def _parse_money(text):
    """Parse '$1,234' or '1234' (ignoring trailing text like '±5%') → float, or None."""
    if not text:
        return None
    m = re.search(r'\$([\d,]+(?:\.\d+)?)', text.strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_results_html(html, page_url=None):
    """
    Parse Rentometer's quickview analysis page → dict with mean/median/percentiles.

    Layout (confirmed 2026-06):
      - Stats in div.box-stats-row > div.box-stats > p.box-num
        Order: Average (mean), Median, 25th Percentile, 75th Percentile
      - Sample + radius in p.qv-ng-results-info:
          "Results based on 23 , 2-bedroom, rentals seen within 12 months in a 1.50 mile radius."
    """
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # --- Primary stats (box-stats layout) ---
    stat_boxes = soup.select("div.box-stats")
    key_order  = ["mean", "median", "percentile_25", "percentile_75"]
    for i, box in enumerate(stat_boxes[:4]):
        val_el = box.select_one("p.box-num")
        if val_el:
            val = _parse_money(val_el.get_text())
            if val and i < len(key_order):
                result[key_order[i]] = val

    # --- Sample size + radius from qv-ng-results-info ---
    info_el = soup.select_one("p.qv-ng-results-info")
    if info_el:
        info_text = info_el.get_text(" ", strip=True)
        m_sample  = re.search(r'based on\s+(\d+)', info_text)
        m_radius  = re.search(r'([\d.]+)\s+mile', info_text)
        if m_sample:
            result["sample_size"] = int(m_sample.group(1))
        if m_radius:
            result["radius_miles"] = float(m_radius.group(1))

    # --- QuickView URL ---
    if page_url:
        result["quickview_url"] = page_url
    else:
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            result["quickview_url"] = canonical["href"]

    if result.get("median") or result.get("mean"):
        result.setdefault("sample_size",        None)
        result.setdefault("radius_miles",       None)
        result.setdefault("normalized_address", None)
        result.setdefault("quickview_url",      None)
        result.setdefault("min",                None)
        result.setdefault("max",                None)
        result.setdefault("percentile_25",      None)
        result.setdefault("percentile_75",      None)
        result.setdefault("std_dev",            None)
        result.setdefault("credits_remaining",  None)
        return result

    return None


def _lookup_web_playwright(address, beds, baths=None):
    """
    Drive rentometer.com under Brian's stored credentials via Playwright.
    Fills the address search form, selects bedroom count, submits, and parses results.
    Returns raw dict (without om_rent fields) or None.
    """
    email, password = _web_credentials()
    if not email:
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [rentometer] playwright not installed. Run: pip3 install playwright && playwright install chromium")
        return None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page    = browser.new_page()

            # --- Login ---
            page.goto(f"{RENTOMETER_WEB}/accounts/sign_in")
            page.fill("input[name='user[email]']",    email)
            page.fill("input[name='user[password]']", password)
            page.click("input[type='submit']")
            page.wait_for_load_state("networkidle", timeout=15000)

            if page.url != f"{RENTOMETER_WEB}/" and "sign_in" in page.url:
                print("  [rentometer] Web login failed — check RENTOMETER_EMAIL/PASSWORD in .env")
                browser.close()
                return None

            # --- Homepage: fill address form ---
            page.goto(f"{RENTOMETER_WEB}/")
            page.wait_for_load_state("domcontentloaded", timeout=10000)

            addr_input = page.locator("input[name='unified_search[address]']").first
            addr_input.fill(address)
            page.wait_for_timeout(1500)

            # Accept first autocomplete suggestion (Google Places)
            suggestions = page.locator(".pac-item")
            if suggestions.count() > 0:
                suggestions.first.click()
                page.wait_for_timeout(500)

            # Set bedroom count (bed_style select)
            page.locator("select[name='unified_search[bed_style]']:visible").first.select_option(str(beds))
            page.wait_for_timeout(300)

            # Set baths if provided
            if baths:
                baths_val = "1" if baths == "1" else "1.5"
                page.locator("select[name='unified_search[baths]']:visible").first.select_option(baths_val)
                page.wait_for_timeout(200)

            # Submit
            page.locator("input[value='Check Rents']:visible").first.click()
            page.wait_for_load_state("networkidle", timeout=25000)

            final_url = page.url
            html      = page.content()
            browser.close()

        return _parse_results_html(html, page_url=final_url)

    except Exception as exc:
        print(f"  [rentometer] Playwright error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Public interface — unchanged contract for all downstream callers
# ---------------------------------------------------------------------------

def check_auth():
    """Verify API key and return account info. Free — costs 0 credits."""
    key = _api_key()
    if not key:
        print("ERROR: RENTOMETER_API_KEY not set; check_auth() requires API key.")
        sys.exit(1)
    r = requests.get(f"{RENTOMETER_BASE}/auth",
                     params={"api_key": key}, timeout=10)
    if r.status_code == 401:
        print("ERROR: Invalid Rentometer API key.")
        sys.exit(1)
    r.raise_for_status()
    return r.json()


def lookup(address, beds, baths=None, building_type=None, om_rent=None):
    """
    Query Rentometer for one address + bedroom type.

    Auth priority:
      1. RENTOMETER_API_KEY set in .env  → REST API (1 credit/call)
      2. RENTOMETER_EMAIL + PASSWORD     → Playwright web scrape (free, no credits)

    Returns dict with: mean, median, min, max, percentile_25, percentile_75,
    std_dev, sample_size, radius_miles, normalized_address, quickview_url,
    credits_remaining, bedrooms, baths.

    If om_rent provided, also includes: om_rent, vs_median, vs_median_pct,
    vs_mean, vs_mean_pct, om_assessment.

    Returns None if no data found for that address/bedroom combo.
    """
    if _api_key():
        raw = _lookup_api(address, beds, baths, building_type)
    else:
        raw = _lookup_web_playwright(address, beds, baths)

    if raw is None:
        return None

    result = dict(raw)
    result["bedrooms"] = beds
    result["baths"]    = baths

    if om_rent is not None and result.get("median"):
        delta_med  = om_rent - result["median"]
        pct_med    = (om_rent / result["median"] - 1) * 100
        delta_mean = (om_rent - result["mean"]) if result.get("mean") else None
        pct_mean   = ((om_rent / result["mean"] - 1) * 100) if result.get("mean") else None

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


# ---------------------------------------------------------------------------
# CLI output helpers (unchanged)
# ---------------------------------------------------------------------------

def _money(v):
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "N/A"


def print_report(result, beds, baths=None):
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
    radius  = result.get("radius_miles")
    samples = result.get("sample_size")
    print(f"  Radius  : {radius} mi  |  Samples: {samples}")
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
