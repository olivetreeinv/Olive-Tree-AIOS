#!/usr/bin/env python3
"""
Olive Tree Investments — Fathom Meeting Sync
Pulls completed meetings from Fathom API and appends new rows to the
Meetings Google Sheet. Skips meetings already logged (deduped by Fathom link).

Usage:
  python3 scripts/fathom_sync.py           # sync last 30 days
  python3 scripts/fathom_sync.py --days 7  # sync last N days
  python3 scripts/fathom_sync.py --all     # sync all available meetings
"""

import json
import os
import re
import subprocess
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

SHEET_ID   = "1PyPmgCAB92aPjPSAYqbDbC6iVKQ9gi3Ti9m3xXOqoYo"
SHEET_URL  = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
FATHOM_BASE = "https://api.fathom.ai/external/v1"
DEFAULT_DAYS = 30
WIKI_CALLS_DIR = Path(__file__).parent.parent / "wiki" / "meetings"


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def get_fathom_key():
    key = os.environ.get("FATHOM_API_KEY", "").strip()
    if not key:
        # Try loading from .env in project root
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("FATHOM_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break
    if not key:
        print("ERROR: FATHOM_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)
    return key


def get_google_token():
    try:
        result = subprocess.run(
            ["gws", "auth", "export", "--unmasked"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        creds = json.loads(result.stdout)
    except Exception as e:
        print(f"ERROR: Could not export gws credentials: {e}")
        print("Run: gws auth login -s sheets")
        sys.exit(1)

    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type":    "refresh_token",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ─────────────────────────────────────────────
# Fathom API
# ─────────────────────────────────────────────

def fathom_get(path, fathom_key, params=None):
    resp = requests.get(
        f"{FATHOM_BASE}{path}",
        headers={"X-Api-Key": fathom_key, "Content-Type": "application/json"},
        params=params or {},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_meetings(fathom_key, since_dt=None):
    """Return list of completed meetings. Paginates automatically."""
    meetings = []
    page = 1

    while True:
        data = fathom_get("/meetings", fathom_key, {"per_page": 50, "page": page})
        items = data.get("items", [])
        if not items:
            break

        for item in items:
            started = item.get("started_at") or item.get("created_at", "")
            if since_dt and started:
                item_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                if item_dt < since_dt:
                    return meetings
            meetings.append(item)

        # Stop if fewer results than page size (last page)
        if len(items) < 50:
            break
        page += 1

    return meetings


def fetch_recording_data(fathom_key, recording_id):
    """Fetch summary endpoint once; return (summary_str, action_items_str)."""
    try:
        data = fathom_get(f"/recordings/{recording_id}/summary", fathom_key)
    except Exception as e:
        print(f"    WARN: could not fetch recording {recording_id}: {e}")
        return "", ""

    raw = data.get("summary") or data.get("text") or data.get("content") or ""
    if isinstance(raw, dict):
        parts = []
        for section in raw.get("sections", []):
            heading = section.get("heading", "")
            body    = section.get("body", "")
            if heading and body:
                parts.append(f"{heading}: {body}")
            elif body:
                parts.append(body)
        summary = " | ".join(parts)
    else:
        summary = str(raw)

    items = data.get("action_items") or []
    if isinstance(items, list):
        action_items = "\n".join(
            f"• {a.get('text') or a.get('description') or str(a)}"
            for a in items if a
        )
    else:
        action_items = ""

    return summary, action_items


def parse_meeting_row(meeting, fathom_key):
    """Convert a Fathom meeting object into the 8-column sheet row."""
    started = meeting.get("started_at") or meeting.get("created_at", "")
    if started:
        dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        date_str = dt.strftime("%m/%d/%Y")
    else:
        date_str = ""

    title = meeting.get("title") or meeting.get("name") or "Untitled Meeting"

    attendees_raw = meeting.get("attendees") or []
    if isinstance(attendees_raw, list):
        attendees = ", ".join(
            a.get("name") or a.get("email") or ""
            for a in attendees_raw
            if isinstance(a, dict)
        )
    else:
        attendees = str(attendees_raw)

    recording_id = meeting.get("recording_id") or meeting.get("id")
    summary, action_items = fetch_recording_data(fathom_key, recording_id) if recording_id else ("", "")

    fathom_link = (
        meeting.get("share_url")
        or meeting.get("recording_url")
        or (f"https://fathom.video/calls/{recording_id}" if recording_id else "")
    )

    return [date_str, title, attendees, summary, action_items, "", "Fathom", fathom_link]


# ─────────────────────────────────────────────
# Sheets API helpers
# ─────────────────────────────────────────────

def sheets_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_first_tab_name(token):
    resp = requests.get(SHEET_URL, headers=sheets_headers(token), timeout=30)
    resp.raise_for_status()
    sheets = resp.json().get("sheets", [])
    return sheets[0]["properties"]["title"] if sheets else "Sheet1"


def get_existing_links(token, tab):
    """Return the set of Fathom links already in column H (index 7)."""
    range_name = f"{tab}!H:H"
    resp = requests.get(
        f"{SHEET_URL}/values/{range_name}",
        headers=sheets_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    values = resp.json().get("values", [])
    return {row[0].strip() for row in values if row and row[0].strip()}


def ensure_header_format(token):
    """Freeze row 1, light grey bg, not bold. Idempotent."""
    meta = requests.get(SHEET_URL, headers=sheets_headers(token), timeout=30)
    meta.raise_for_status()
    tab_id = meta.json()["sheets"][0]["properties"]["sheetId"]

    body = {"requests": [
        {"updateSheetProperties": {
            "properties": {"sheetId": tab_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"
        }},
        {"repeatCell": {
            "range": {"sheetId": tab_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85},
                "textFormat": {"bold": True}
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat.bold)"
        }}
    ]}
    requests.post(f"{SHEET_URL}:batchUpdate", headers=sheets_headers(token), json=body, timeout=30).raise_for_status()


def append_rows(token, tab, rows):
    body = {"values": rows, "majorDimension": "ROWS"}
    resp = requests.post(
        f"{SHEET_URL}/values/{tab}!A1:append",
        headers=sheets_headers(token),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()


# ─────────────────────────────────────────────
# Wiki
# ─────────────────────────────────────────────

def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _wiki_filename(row):
    date_str, title = row[0], row[1]
    try:
        iso_date = datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        iso_date = "0000-00-00"
    return f"{iso_date}-{slug(title)}.md"


def write_wiki_note(row):
    """Write a markdown call note to wiki/calls/YYYY-MM-DD-<slug>.md."""
    date_str, title, attendees, summary, action_items, _, source, fathom_link = row

    filename = _wiki_filename(row)
    path = WIKI_CALLS_DIR / filename

    if path.exists():
        return  # already written

    WIKI_CALLS_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# {title}",
        f"**Date:** {date_str}  ",
        f"**Attendees:** {attendees or '—'}  ",
        f"**Source:** {source}  ",
        f"**Recording:** {fathom_link or '—'}",
        "",
        "## Summary",
        summary or "_No summary available._",
        "",
        "## Action Items",
        action_items or "_None recorded._",
    ]

    path.write_text("\n".join(lines) + "\n")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    sync_all = "--all" in sys.argv
    days = DEFAULT_DAYS
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        if idx + 1 >= len(sys.argv):
            print("ERROR: --days requires a value (e.g. --days 7)")
            sys.exit(1)
        days = int(sys.argv[idx + 1])

    since_dt = None if sync_all else (
        datetime.now(timezone.utc) - timedelta(days=days)
    )

    print("Authenticating...")
    fathom_key   = get_fathom_key()
    google_token = get_google_token()

    ensure_header_format(google_token)

    print(f"Fetching Fathom meetings {'(all)' if sync_all else f'(last {days} days)'}...")
    meetings = fetch_meetings(fathom_key, since_dt)
    print(f"  Found {len(meetings)} meeting(s)")

    if not meetings:
        print("Nothing to sync.")
        return

    tab = get_first_tab_name(google_token)
    print(f"  Sheet tab: {tab}")

    existing_links = get_existing_links(google_token, tab)
    print(f"  Already logged: {len(existing_links)} meeting(s)")

    all_rows = [parse_meeting_row(m, fathom_key) for m in meetings]

    # Sheet: only append rows not already logged
    new_rows = [r for r in all_rows if not (r[7] and r[7] in existing_links)]

    # Wiki: write notes for all meetings (path.exists() guard skips duplicates)
    wiki_written = 0
    for row in all_rows:
        before = (WIKI_CALLS_DIR / f"{_wiki_filename(row)}").exists()
        write_wiki_note(row)
        if not before:
            wiki_written += 1

    if not new_rows and not wiki_written:
        print("All meetings already logged. Nothing to add.")
        return

    if new_rows:
        print(f"  Adding {len(new_rows)} new sheet row(s)...")
        append_rows(google_token, tab, new_rows)
        for row in new_rows:
            print(f"  ✓ sheet  {row[0]}  {row[1]}")

    if wiki_written:
        print(f"  ✓ wiki   {wiki_written} new note(s) written to wiki/meetings/")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
