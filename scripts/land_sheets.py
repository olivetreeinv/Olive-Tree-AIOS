#!/usr/bin/env python3
"""
Olive Tree — Land Wholesaling sheet I/O

Thin Google Sheets helpers scoped to the dedicated land workbook (LAND_SHEET_ID).
Shared by land_markets / land_builders / land_sellers / land_deals so none of
them repeat auth + range plumbing. Mirror of the patterns in sheets_update.py,
but pointed at the land workbook instead of the multifamily one.
"""

import os

import requests
from dotenv import load_dotenv
from gws_auth import get_token

load_dotenv()

SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def sheet_id():
    sid = os.getenv("LAND_SHEET_ID")
    if not sid:
        raise RuntimeError("LAND_SHEET_ID not set. Run: python3 scripts/land_setup.py")
    return sid


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def read_rows(token, tab):
    """Return all rows of a tab as a list of lists (row 0 = header)."""
    rng = requests.utils.quote(f"{tab}!A1:Z100000")
    r = requests.get(f"{SHEETS_BASE}/{sheet_id()}/values/{rng}",
                     headers=_headers(token), timeout=30)
    r.raise_for_status()
    return r.json().get("values", [])


def append_rows(token, tab, rows):
    """Append one or more rows to the bottom of a tab."""
    if not rows:
        return
    rng = requests.utils.quote(f"{tab}!A1")
    r = requests.post(
        f"{SHEETS_BASE}/{sheet_id()}/values/{rng}:append",
        headers=_headers(token),
        params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
        json={"values": rows, "majorDimension": "ROWS"}, timeout=30)
    r.raise_for_status()
    return r.json()


def upsert_row(token, tab, key_col_index, key_value, row):
    """
    Insert row, or overwrite the existing row whose key column matches key_value.
    Keeps the sheet deduped on a natural key (e.g. parcel id, zip).
    """
    existing = read_rows(token, tab)
    for i, r in enumerate(existing):
        if i == 0:
            continue  # header
        if len(r) > key_col_index and r[key_col_index] == str(key_value):
            rng = requests.utils.quote(f"{tab}!A{i + 1}")
            resp = requests.put(
                f"{SHEETS_BASE}/{sheet_id()}/values/{rng}",
                headers=_headers(token),
                params={"valueInputOption": "RAW"},
                json={"values": [row]}, timeout=30)
            resp.raise_for_status()
            return "updated"
    append_rows(token, tab, [row])
    return "appended"


__all__ = ["get_token", "sheet_id", "read_rows", "append_rows", "upsert_row"]
