#!/usr/bin/env python3
"""
Olive Tree Investments — Master Deal Index

Rebuilds a master spreadsheet with one row per deal property, linking
to every key document in that deal's Drive folder: OM, T-12, Rent Roll,
Deal Analyzer, Analysis Summary, LOI, and Pitch Deck.

Reads every subfolder under "Olive Tree Investments - Deals", classifies
files by name keywords, and writes one row per address to the master sheet.
Re-run is safe — it overwrites all rows each time (always current, no dedup).
Skips folders whose name contains "TEST".

Stdlib-only (urllib) — cloud-ready with no extra packages.
Auth: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN
(read from env or ../.env; falls back to `gws auth export` locally)

Usage:
  python3 scripts/deal_index.py          # rebuild master index
  python3 scripts/deal_index.py --dry-run  # print classification, no sheet write

Config (env-overridable):
  DEAL_INDEX_SHEET_ID    Master index spreadsheet
  DEAL_INDEX_SHEET_TAB   Tab name (default: Deal Index)
"""

import argparse
import json
import os
import urllib.parse
from datetime import datetime
from pathlib import Path

import loom_sync as G
from loom_sync import _http, _auth, _load_dotenv, get_token

DEALS_FOLDER_ID = "1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p"

SHEET_TAB = os.environ.get("DEAL_INDEX_SHEET_TAB", "Deal Index")
SHEET_ID  = os.environ.get("DEAL_INDEX_SHEET_ID",
                            "1mvqgkSw8kMWhWHEVZ4a2Q8IiRihusCwL1zxNwXgj3ao").strip()

SHEET_HEADER = [
    "Address / Property", "Deal Folder",
    "OM", "T-12", "Rent Roll", "Deal Analyzer",
    "Analysis Summary", "LOI", "Pitch Deck", "Last Updated",
]

# Classification rules: (column_key, [keywords to match — any match wins])
# Keyword match is case-insensitive against the file name.
FILE_CLASSES = [
    ("OM",               ["offering memorandum", " om ", "(om)", "-om-", "_om_"]),
    ("T-12",             ["t-12", "t12", "trailing"]),
    ("Rent Roll",        ["rent roll"]),
    ("Deal Analyzer",    ["deal analyzer", "proforma", "pro forma"]),
    ("Analysis Summary", ["analysis summary"]),
    ("LOI",              ["loi", "letter of intent"]),
    ("Pitch Deck",       ["pitch deck"]),
]

# Folder names / substrings that are infrastructure — skip them.
SKIP_NAMES = {"TEST", "Land Wholesale", "Olive Tree Investments - LOI",
              "Olive Tree Investments - Deal Index"}


# ─────────────────────────────────────────────
# Drive helpers
# ─────────────────────────────────────────────

def list_subfolders(token, parent_id):
    """Return list of (id, name, webViewLink) for direct child folders."""
    q = (f"'{parent_id}' in parents "
         "and mimeType='application/vnd.google-apps.folder' "
         "and trashed=false")
    params = urllib.parse.urlencode({
        "q": q, "fields": "files(id,name,webViewLink)", "pageSize": "200",
    })
    data = _http("GET", f"{G.DRIVE_BASE}/files?{params}",
                 headers=_auth(token), timeout=30)
    return data.get("files", [])


def list_files_in_folder(token, folder_id):
    """Return list of file metadata dicts for direct children (non-folders)."""
    q = (f"'{folder_id}' in parents "
         "and mimeType!='application/vnd.google-apps.folder' "
         "and trashed=false")
    params = urllib.parse.urlencode({
        "q": q,
        "fields": "files(id,name,webViewLink,mimeType)",
        "pageSize": "200",
    })
    data = _http("GET", f"{G.DRIVE_BASE}/files?{params}",
                 headers=_auth(token), timeout=30)
    return data.get("files", [])


# ─────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────

def classify_file(name):
    """Return the column key for a file name, or None if no match."""
    lower = name.lower()
    for col_key, keywords in FILE_CLASSES:
        for kw in keywords:
            if kw in lower:
                return col_key
    return None


def classify_folder(token, folder):
    """Return a dict of {column_key: webViewLink} for files in a deal folder."""
    found = {}
    try:
        files = list_files_in_folder(token, folder["id"])
    except RuntimeError as e:
        print(f"      WARN: could not list files: {e}")
        return found
    for f in files:
        col = classify_file(f["name"])
        if col and col not in found:
            found[col] = f.get("webViewLink", "")
    return found


# ─────────────────────────────────────────────
# Sheets
# ─────────────────────────────────────────────

def clear_and_write(token, rows):
    """Overwrite the entire sheet with header + data rows."""
    # Clear the sheet first
    rng_enc = urllib.parse.quote(f"{SHEET_TAB}!A1:Z")
    _http("POST",
          f"{G.SHEETS_BASE}/{SHEET_ID}/values/{rng_enc}:clear",
          headers={**_auth(token), "Content-Type": "application/json"},
          data=b"{}",
          timeout=30)
    if not rows:
        return
    rng_enc = urllib.parse.quote(f"{SHEET_TAB}!A1")
    _http("PUT",
          f"{G.SHEETS_BASE}/{SHEET_ID}/values/{rng_enc}"
          "?valueInputOption=USER_ENTERED",
          headers={**_auth(token), "Content-Type": "application/json"},
          data=json.dumps({"values": rows, "majorDimension": "ROWS"}).encode(),
          timeout=30)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Olive Tree — Deal Index")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    global SHEET_ID, SHEET_TAB
    SHEET_ID  = os.environ.get("DEAL_INDEX_SHEET_ID", SHEET_ID).strip()
    SHEET_TAB = os.environ.get("DEAL_INDEX_SHEET_TAB", SHEET_TAB)

    token = get_token()

    print("Listing deal folders...")
    folders = list_subfolders(token, DEALS_FOLDER_ID)
    # Skip infra folders and TEST folders
    deal_folders = [
        f for f in folders
        if not any(skip in f["name"] for skip in SKIP_NAMES)
    ]
    print(f"  Found {len(deal_folders)} deal folder(s) "
          f"({len(folders) - len(deal_folders)} skipped)")

    now_str = datetime.now().strftime("%m/%d/%Y %H:%M")
    rows = [SHEET_HEADER]
    for folder in sorted(deal_folders, key=lambda f: f["name"]):
        name   = folder["name"]
        flink  = folder.get("webViewLink", "")
        print(f"  • {name}")

        classified = classify_folder(token, folder)
        if args.dry_run:
            for col, link in classified.items():
                print(f"      {col}: {link[:60] if link else '—'}")

        # Build row in SHEET_HEADER column order
        row = [
            name, flink,
            classified.get("OM", ""),
            classified.get("T-12", ""),
            classified.get("Rent Roll", ""),
            classified.get("Deal Analyzer", ""),
            classified.get("Analysis Summary", ""),
            classified.get("LOI", ""),
            classified.get("Pitch Deck", ""),
            now_str,
        ]
        rows.append(row)

    if args.dry_run:
        print(f"\nDry-run: {len(rows)-1} row(s) would be written (not sent to sheet).")
        return

    print(f"\nWriting {len(rows)-1} row(s) to master index...")
    clear_and_write(token, rows)
    print(f"Done.")
    print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
