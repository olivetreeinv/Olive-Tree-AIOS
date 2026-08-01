#!/usr/bin/env python3
"""
Olive Tree Investments — Land Wholesaling workbook bootstrap

Idempotent. Creates the dedicated "Olive Tree — Land Wholesaling" Google
Spreadsheet (separate from the multifamily deal workbook, GovCon-style),
adds the 4 Land tabs with header rows, and saves LAND_SHEET_ID to .env.

Re-runnable: if LAND_SHEET_ID is already set, it reuses that workbook and
just ensures the tabs + headers exist.

Usage:
  python3 scripts/land_setup.py            # create or repair the workbook
  python3 scripts/land_setup.py --dry-run  # show what it would do
"""

import argparse
import os
import re

import requests
from dotenv import load_dotenv
from gws_auth import get_token

load_dotenv()

SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
TITLE = "Olive Tree — Land Wholesaling"
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

# Tab name -> header row. Mirrors db/schema.py LandMarket/Builder/Seller/Deal.
TABS = {
    "Land Markets": [
        "County", "Zip", "City", "State", "Total Parcels", "Vacant Lots",
        "Vacant Out-of-State", "Cookie-Cutter Uniformity", "Median Acres",
        "Avg Land Value", "Builders Active", "Go/No-Go", "Score", "Notes", "Date",
        "FMLS Median $/Acre",
    ],
    "Land Builders": [
        "Name", "Company", "State", "City", "Phone", "Email", "Markets/Zips",
        "Avg $/Acre (Comp)", "Lot Size Min", "Lot Size Max", "Price Per Lot",
        "Volume/Mo", "Conditions", "Close Timeline", "Tier", "Deals Done",
        "Last Contact", "Notes", "Intake Portal",
    ],
    "Land Sellers": [
        "Parcel ID", "Situs Address", "Zip", "Subdivision", "Acres",
        "Owner Name", "Owner Mailing Address", "Owner City", "Owner State",
        "Out-of-State", "Est Land Value", "Offer Price", "Owner Phone",
        "Builder Target", "Channel", "Call Status", "Last Call",
        "Callback Date", "Outcome", "Notes", "Owner Zip",
        "Mkt Avg List Pr", "Buy Pr Est", "Buy Box",
    ],
    "Land Deals": [
        "Parcel ID", "Situs Address", "Seller", "Builder", "Contract Price",
        "Assignment Price", "Spread", "Status", "Feasibility Deadline",
        "Deal-Killer Check", "Title Company", "Close Date", "Profit",
        "Referral Sent", "Neighbors Called", "Notes",
    ],
}


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_spreadsheet(token):
    body = {
        "properties": {"title": TITLE},
        "sheets": [{"properties": {"title": t}} for t in TABS],
    }
    r = requests.post(SHEETS_BASE, headers=_headers(token), json=body, timeout=30)
    r.raise_for_status()
    return r.json()["spreadsheetId"]


def existing_tabs(token, sheet_id):
    r = requests.get(f"{SHEETS_BASE}/{sheet_id}",
                     headers=_headers(token),
                     params={"fields": "sheets.properties.title"}, timeout=30)
    r.raise_for_status()
    return {s["properties"]["title"] for s in r.json().get("sheets", [])}


def add_tab(token, sheet_id, title):
    body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
    r = requests.post(f"{SHEETS_BASE}/{sheet_id}:batchUpdate",
                      headers=_headers(token), json=body, timeout=30)
    r.raise_for_status()


def write_headers(token, sheet_id, title, header):
    rng = f"{title}!A1"
    r = requests.put(
        f"{SHEETS_BASE}/{sheet_id}/values/{requests.utils.quote(rng)}",
        headers=_headers(token),
        params={"valueInputOption": "RAW"},
        json={"values": [header]}, timeout=30)
    r.raise_for_status()


def save_env(sheet_id):
    """Add or update LAND_SHEET_ID in .env."""
    path = os.path.abspath(ENV_PATH)
    line = f"LAND_SHEET_ID={sheet_id}\n"
    if os.path.exists(path):
        with open(path) as f:
            content = f.read()
        if re.search(r"^LAND_SHEET_ID=", content, re.M):
            content = re.sub(r"^LAND_SHEET_ID=.*$", line.rstrip(), content, flags=re.M)
        else:
            content = content.rstrip("\n") + "\n" + line
    else:
        content = line
    with open(path, "w") as f:
        f.write(content)


def main():
    ap = argparse.ArgumentParser(description="Bootstrap the land wholesaling workbook.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = get_token()
    sheet_id = os.getenv("LAND_SHEET_ID")

    if args.dry_run:
        print(f"[dry-run] workbook: {sheet_id or '(none — would create ' + TITLE + ')'}")
        print(f"[dry-run] tabs: {', '.join(TABS)}")
        return

    if not sheet_id:
        sheet_id = create_spreadsheet(token)
        print(f"Created workbook '{TITLE}': {sheet_id}")
    else:
        print(f"Reusing workbook: {sheet_id}")

    have = existing_tabs(token, sheet_id)
    for title, header in TABS.items():
        if title not in have:
            add_tab(token, sheet_id, title)
            print(f"  + added tab: {title}")
        write_headers(token, sheet_id, title, header)
        print(f"  · headers set: {title}")

    save_env(sheet_id)
    print(f"\nLAND_SHEET_ID saved to .env")
    print(f"Open: https://docs.google.com/spreadsheets/d/{sheet_id}")


if __name__ == "__main__":
    main()
