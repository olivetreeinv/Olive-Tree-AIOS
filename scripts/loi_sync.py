#!/usr/bin/env python3
"""
Olive Tree Investments — LOI Sync

Searches Google Drive for LOI Google Docs (name contains 'LOI' or
'Letter of Intent'), exports each as a PDF, archives it to the
"Olive Tree Investments - LOI" folder, logs a row to the LOI tracking
sheet, and writes a wiki note. Deduped by source Doc ID.

Mirrors canva_sync.py / loom_sync.py — reuses loom_sync stdlib infra.
Stdlib-only (urllib) — cloud-ready with no extra packages.

Auth: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN
(read from env or ../.env; falls back to `gws auth export` locally)

Usage:
  python3 scripts/loi_sync.py                 # archive new LOI docs
  python3 scripts/loi_sync.py --dry-run       # list matches, no export/write

Config (env-overridable):
  LOI_SHEET_ID         Google Sheet to log into
  LOI_SHEET_TAB        Tab name (default: LOIs)
  LOI_DRIVE_FOLDER_ID  Drive folder for archived PDFs
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

import loom_sync as G
from loom_sync import _http, _auth, _load_dotenv, get_token, find_or_create_folder, slug

DEALS_FOLDER_ID    = "1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p"
LOI_FOLDER_NAME    = "Olive Tree Investments - LOI"
WIKI_LOIS_DIR      = Path(__file__).parent.parent / "wiki" / "lois"

# Hardcoded defaults (env-overridable) so the cloud routine needs no extra setup.
SHEET_TAB       = os.environ.get("LOI_SHEET_TAB", "LOIs")
SHEET_ID        = os.environ.get("LOI_SHEET_ID",
                                 "1S8KuW1n8vTnMnP7U5AYWqosjl8sTxudamNybNqkZ8P4").strip()
DRIVE_FOLDER_ID = os.environ.get("LOI_DRIVE_FOLDER_ID",
                                 "1o2Soa4FxxSpgGxrpFSOqFBD-p7z5-S_O").strip()

SHEET_HEADER = [
    "Date Archived", "Property / Address", "Deal Folder",
    "LOI Doc", "LOI PDF", "Offer Price", "Status", "Wiki Note",
]

# Drive search — catches both naming conventions used by /loi skill:
#   "641 Powder Springs St — LOI — 2026-06-11"
#   "Letter of Intent - 2000 Old Tullahoma"
LOI_QUERY = (
    "mimeType='application/vnd.google-apps.document' and trashed=false "
    "and (name contains 'LOI' or name contains 'Letter of Intent')"
)


# ─────────────────────────────────────────────
# Drive search
# ─────────────────────────────────────────────

def search_loi_docs(token):
    """Return list of Drive file metadata dicts for all LOI Google Docs."""
    items, page_token = [], None
    params_base = {
        "q": LOI_QUERY,
        "fields": "nextPageToken,files(id,name,webViewLink,parents)",
        "pageSize": "100",
    }
    while True:
        params = dict(params_base)
        if page_token:
            params["pageToken"] = page_token
        url = f"{G.DRIVE_BASE}/files?{urllib.parse.urlencode(params)}"
        data = _http("GET", url, headers=_auth(token), timeout=30)
        items.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return items


def get_parent_folder_link(token, file_meta):
    """Return (folder_name, webViewLink) for the first parent of a Drive file."""
    parents = file_meta.get("parents", [])
    if not parents:
        return "", ""
    try:
        folder = _http("GET",
                       f"{G.DRIVE_BASE}/files/{parents[0]}?fields=id,name,webViewLink",
                       headers=_auth(token), timeout=15)
        return folder.get("name", ""), folder.get("webViewLink", "")
    except RuntimeError:
        return "", ""


# ─────────────────────────────────────────────
# Export → PDF
# ─────────────────────────────────────────────

def export_doc_pdf(token, doc_id):
    """Export a Google Doc to PDF bytes via the Drive export endpoint."""
    url = (f"{G.DRIVE_BASE}/files/{doc_id}/export"
           f"?mimeType={urllib.parse.quote('application/pdf')}")
    return _http("GET", url, headers=_auth(token), raw=True, timeout=120)


# ─────────────────────────────────────────────
# Drive upload (PDF)
# ─────────────────────────────────────────────

def drive_upload_pdf(token, folder_id, filename, content):
    """Multipart upload of PDF bytes; returns webViewLink."""
    import uuid as _uuid
    boundary = _uuid.uuid4().hex
    meta = {"name": filename, "parents": [folder_id]}
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(meta).encode(), b"\r\n",
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/pdf\r\n\r\n",
        content, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    headers = {**_auth(token),
               "Content-Type": f"multipart/related; boundary={boundary}"}
    resp = _http("POST",
                 f"{G.DRIVE_UPLOAD}?uploadType=multipart&fields=id,webViewLink",
                 headers=headers, data=body, timeout=300)
    return resp.get("webViewLink", f"https://drive.google.com/file/d/{resp['id']}/view")


# ─────────────────────────────────────────────
# Sheets
# ─────────────────────────────────────────────

def get_existing_doc_ids(token):
    """Return set of source Doc IDs already logged in the sheet (column E = LOI Doc)."""
    rng = urllib.parse.quote(f"{SHEET_TAB}!A1:H")
    try:
        data = _http("GET", f"{G.SHEETS_BASE}/{SHEET_ID}/values/{rng}",
                     headers=_auth(token), timeout=30)
    except RuntimeError:
        return set()
    rows = data.get("values", [])
    if not rows:
        append_rows(token, [SHEET_HEADER])
        return set()
    # Column D (index 3) = "LOI Doc" link; extract doc ID from URL
    ids = set()
    for row in rows[1:]:
        if len(row) > 3:
            m = re.search(r"/d/([a-zA-Z0-9_-]+)", row[3])
            if m:
                ids.add(m.group(1))
    return ids


def append_rows(token, rows):
    rng = urllib.parse.quote(f"{SHEET_TAB}!A1")
    _http("POST",
          f"{G.SHEETS_BASE}/{SHEET_ID}/values/{rng}:append"
          "?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS",
          headers={**_auth(token), "Content-Type": "application/json"},
          data=json.dumps({"values": rows, "majorDimension": "ROWS"}).encode(),
          timeout=30)


# ─────────────────────────────────────────────
# Wiki
# ─────────────────────────────────────────────

def write_wiki_note(date_str, title, doc_link, pdf_link, folder_link):
    WIKI_LOIS_DIR.mkdir(parents=True, exist_ok=True)
    path = WIKI_LOIS_DIR / f"{slug(title)}.md"
    if path.exists():
        return path.name
    lines = [
        f"# {title}",
        f"**Archived:** {date_str}  ",
        f"**LOI Doc:** {doc_link or '—'}  ",
        f"**LOI PDF:** {pdf_link or '—'}  ",
        f"**Deal Folder:** {folder_link or '—'}",
        "",
        "## Property",
        "_Address / market._",
        "",
        "## Offer",
        "- **Price:** $",
        "- **Terms:**",
        "- **Status:**",
        "",
        "## Notes",
        "- ",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path.name


# ─────────────────────────────────────────────
# Per-doc processing
# ─────────────────────────────────────────────

def process_doc(token, doc, folder_id, dry_run):
    name = doc.get("name", f"LOI {doc['id']}")
    doc_link = doc.get("webViewLink", "")
    print(f"  • {name}")
    if dry_run:
        print(f"      {doc['id']}  (dry-run, skipping export)")
        return None

    folder_name, folder_link = get_parent_folder_link(token, doc)

    date_str = datetime.now().strftime("%m/%d/%Y")
    pdf_link, status = "", "Archived"
    try:
        pdf_bytes = export_doc_pdf(token, doc["id"])
        fname = f"{slug(name)}.pdf"
        pdf_link = drive_upload_pdf(token, folder_id, fname, pdf_bytes)
        print(f"      exported + archived → Drive ({len(pdf_bytes)//1024} KB)")
    except RuntimeError as e:
        status = "Export failed"
        print(f"      WARN: {e}")

    wiki_name = write_wiki_note(date_str, name, doc_link, pdf_link, folder_link)
    return [date_str, folder_name, folder_link, doc_link, pdf_link,
            "", status, wiki_name]


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Olive Tree — LOI Sync")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    global SHEET_ID, SHEET_TAB, DRIVE_FOLDER_ID
    SHEET_ID        = os.environ.get("LOI_SHEET_ID", SHEET_ID).strip()
    SHEET_TAB       = os.environ.get("LOI_SHEET_TAB", SHEET_TAB)
    DRIVE_FOLDER_ID = os.environ.get("LOI_DRIVE_FOLDER_ID", DRIVE_FOLDER_ID).strip()

    token = get_token()

    print("Searching Drive for LOI docs...")
    docs = search_loi_docs(token)
    print(f"  Found {len(docs)} LOI doc(s)")
    if not docs:
        print("Nothing to sync.")
        return

    existing = set()
    folder_id = DRIVE_FOLDER_ID
    if not args.dry_run:
        existing = get_existing_doc_ids(token)
        folder_id = DRIVE_FOLDER_ID or find_or_create_folder(
            token, LOI_FOLDER_NAME, DEALS_FOLDER_ID)

    new_rows = []
    for doc in docs:
        if doc["id"] in existing:
            print(f"  • already archived: {doc.get('name', doc['id'])}")
            continue
        row = process_doc(token, doc, folder_id, args.dry_run)
        if row:
            new_rows.append(row)

    if new_rows:
        append_rows(token, new_rows)
        print(f"\nDone. Archived {len(new_rows)} new LOI(s).")
        print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    elif not args.dry_run:
        print("\nDone. No new LOIs to add.")


if __name__ == "__main__":
    main()
