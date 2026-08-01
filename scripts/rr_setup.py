#!/usr/bin/env python3
"""
Olive Tree — Rank & Rent workbook + Drive folder bootstrap

Idempotent. Creates the "Olive Tree Investments - Rank-Rent" Drive folder,
a tracking spreadsheet inside it with 3 tabs (Sites, Rent Call List, Leads),
saves RR_SHEET_ID + RR_FOLDER_ID to .env, and seeds the Rent Call List from
the rr_prospects table in olive.db.

Re-runnable: reuses RR_SHEET_ID/RR_FOLDER_ID if already set; only fills gaps.

Usage:
  python3 scripts/rr_setup.py            # create or repair
  python3 scripts/rr_setup.py --dry-run
  python3 scripts/rr_setup.py --no-seed  # skip pushing prospects into the sheet
  python3 scripts/rr_setup.py --sync     # sheet edits -> db, then db -> sheet

Sync rule: the sheet is the live editing surface (status/notes/last-call/
callback you type during calls flow back to olive.db); the db is the source
of membership (new --pull prospects flow out to the sheet). Matched on
(name, city).
"""

import argparse
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from gws_auth import get_token

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

load_dotenv()

SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_BASE = "https://www.googleapis.com/drive/v3/files"
FOLDER_NAME = "Olive Tree Investments - Rank-Rent"
TITLE = "Rank & Rent Tracker"
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

TABS = {
    "Sites": [
        "Slug", "Business Name", "Niche", "City", "State", "Domain",
        "Tracking Number", "Live URL", "Deploy Status", "SEO Status",
        "Renter", "Rent Terms", "Date Built", "Notes",
    ],
    "Rent Call List": [
        "Niche", "City", "Name", "Phone", "Website", "Rating", "Reviews",
        "Status", "Last Call", "Callback", "Notes",
    ],
    "Leads": [
        "Month", "Site", "Renter", "Total Calls", "Billable Calls",
        "Rate", "Amount Due", "Invoiced", "Paid", "Notes",
    ],
}


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_folder(token):
    r = requests.post(DRIVE_BASE, headers=_h(token), json={
        "name": FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }, params={"fields": "id"}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def create_spreadsheet(token, folder_id):
    body = {
        "properties": {"title": TITLE},
        "sheets": [{"properties": {"title": t}} for t in TABS],
    }
    r = requests.post(SHEETS_BASE, headers=_h(token), json=body, timeout=30)
    r.raise_for_status()
    sid = r.json()["spreadsheetId"]
    # Move the freshly-created sheet from My Drive root into the folder.
    mv = requests.patch(f"{DRIVE_BASE}/{sid}", headers=_h(token),
                        params={"addParents": folder_id,
                                "removeParents": "root",
                                "fields": "id, parents"}, timeout=30)
    mv.raise_for_status()
    return sid


def existing_tabs(token, sheet_id):
    r = requests.get(f"{SHEETS_BASE}/{sheet_id}", headers=_h(token),
                     params={"fields": "sheets.properties.title"}, timeout=30)
    r.raise_for_status()
    return {s["properties"]["title"] for s in r.json().get("sheets", [])}


def add_tab(token, sheet_id, title):
    requests.post(f"{SHEETS_BASE}/{sheet_id}:batchUpdate", headers=_h(token),
                  json={"requests": [{"addSheet": {"properties": {"title": title}}}]},
                  timeout=30).raise_for_status()


def write_rows(token, sheet_id, title, rows):
    rng = requests.utils.quote(f"{title}!A1")
    requests.put(f"{SHEETS_BASE}/{sheet_id}/values/{rng}", headers=_h(token),
                 params={"valueInputOption": "RAW"},
                 json={"values": rows}, timeout=30).raise_for_status()


def _prospects_ready():
    """rr_prospects exists and has the two sheet-only columns."""
    with engine.begin() as conn:
        exists = conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rr_prospects'"
        )).first()
        if not exists:
            return False
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(rr_prospects)"))}
        for col in ("last_call", "callback"):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE rr_prospects ADD COLUMN {col} TEXT"))
    return True


def prospect_rows():
    """Rent Call List rows from rr_prospects (header + best-first data)."""
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT niche, city, name, phone, website, rating, review_count,
                   status, last_call, callback, notes
            FROM rr_prospects
            ORDER BY (phone IS NOT NULL) DESC,
                     CASE WHEN rating BETWEEN 3.5 AND 4.7 AND review_count < 150
                          THEN 0 ELSE 1 END,
                     review_count ASC
        """)).all()
    header = TABS["Rent Call List"]
    data = [[r.niche, r.city, r.name, r.phone or "", r.website or "",
             r.rating or "", r.review_count or "", r.status or "new",
             r.last_call or "", r.callback or "", r.notes or ""] for r in rows]
    return [header] + data, len(data)


def read_tab(token, sheet_id, title):
    rng = requests.utils.quote(f"{title}!A1:Z100000")
    r = requests.get(f"{SHEETS_BASE}/{sheet_id}/values/{rng}",
                     headers=_h(token), timeout=30)
    r.raise_for_status()
    return r.json().get("values", [])


def cmd_sync(token, sheet_id):
    """Sheet edits -> db (match name+city), then rewrite the sheet from db."""
    values = read_tab(token, sheet_id, "Rent Call List")
    edited = 0
    if len(values) > 1:
        header, rows = values[0], values[1:]
        idx = {name: i for i, name in enumerate(header)}

        def cell(row, col):
            i = idx.get(col)
            return row[i].strip() if i is not None and i < len(row) else ""

        with engine.begin() as conn:
            for row in rows:
                name, city = cell(row, "Name"), cell(row, "City")
                if not name:
                    continue
                res = conn.execute(text("""
                    UPDATE rr_prospects
                       SET status=:st, notes=:no, last_call=:lc, callback=:cb,
                           updated_at=CURRENT_TIMESTAMP
                     WHERE name=:n AND city=:c
                """), {"st": cell(row, "Status") or "new", "no": cell(row, "Notes"),
                       "lc": cell(row, "Last Call"), "cb": cell(row, "Callback"),
                       "n": name, "c": city})
                edited += res.rowcount

    data, n = prospect_rows()
    write_rows(token, sheet_id, "Rent Call List", data)
    print(f"synced: {edited} sheet edit(s) -> db, {n} row(s) db -> sheet")


def save_env(**kv):
    path = os.path.abspath(ENV_PATH)
    content = Path(path).read_text() if os.path.exists(path) else ""
    for key, val in kv.items():
        line = f"{key}={val}"
        if re.search(rf"^{key}=", content, re.M):
            content = re.sub(rf"^{key}=.*$", line, content, flags=re.M)
        else:
            content = content.rstrip("\n") + "\n" + line + "\n"
    Path(path).write_text(content if content.endswith("\n") else content + "\n")


def main():
    ap = argparse.ArgumentParser(description="Bootstrap the Rank & Rent workbook.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-seed", action="store_true")
    ap.add_argument("--sync", action="store_true",
                    help="Round-trip the Rent Call List between the sheet and olive.db")
    args = ap.parse_args()

    folder_id = os.getenv("RR_FOLDER_ID")
    sheet_id = os.getenv("RR_SHEET_ID")

    if args.sync:
        if not sheet_id:
            raise SystemExit("RR_SHEET_ID not set. Run: python3 scripts/rr_setup.py")
        if not _prospects_ready():
            raise SystemExit("No rr_prospects table. Run: python3 scripts/rr_prospects.py --pull ...")
        cmd_sync(get_token(), sheet_id)
        return

    if args.dry_run:
        print(f"[dry-run] folder: {folder_id or '(would create ' + FOLDER_NAME + ')'}")
        print(f"[dry-run] sheet:  {sheet_id or '(would create ' + TITLE + ')'}")
        print(f"[dry-run] tabs:   {', '.join(TABS)}")
        return

    token = get_token()

    if not folder_id:
        folder_id = create_folder(token)
        print(f"Created Drive folder '{FOLDER_NAME}': {folder_id}")
    else:
        print(f"Reusing folder: {folder_id}")

    if not sheet_id:
        sheet_id = create_spreadsheet(token, folder_id)
        print(f"Created workbook '{TITLE}' in folder: {sheet_id}")
    else:
        print(f"Reusing workbook: {sheet_id}")

    have = existing_tabs(token, sheet_id)
    for title, header in TABS.items():
        if title not in have:
            add_tab(token, sheet_id, title)
            print(f"  + added tab: {title}")
        write_rows(token, sheet_id, title, [header])

    if not args.no_seed and _prospects_ready():
        rows, n = prospect_rows()
        if n:
            write_rows(token, sheet_id, "Rent Call List", rows)
            print(f"  seeded Rent Call List with {n} prospect(s) from olive.db")

    save_env(RR_FOLDER_ID=folder_id, RR_SHEET_ID=sheet_id)
    print(f"\nSaved RR_FOLDER_ID + RR_SHEET_ID to .env")
    print(f"Open: https://docs.google.com/spreadsheets/d/{sheet_id}")


if __name__ == "__main__":
    main()
