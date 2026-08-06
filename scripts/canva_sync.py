#!/usr/bin/env python3
"""
Olive Tree Investments — Canva Pitch Deck Sync

Searches Canva for designs matching a query (default "Pitch Deck"),
exports each as a PDF, archives it to the "Olive Tree Investments -
Pitch Decks" Drive folder, logs a row to the Pitch Decks sheet, and
writes a wiki note per deck. Deduped by Canva design ID.

Mirrors loom_sync.py — reuses its Google/Drive/Sheets infra. Stdlib-only
(urllib) so it runs in the cloud schedule with the laptop off.

Auth:
  Google — GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN
  Canva  — CANVA_CLIENT_ID / CANVA_CLIENT_SECRET / CANVA_REFRESH_TOKEN
  (read from env or ../.env; Google falls back to `gws auth export` locally)

Usage:
  python3 scripts/canva_sync.py                 # archive new "Pitch Deck" designs
  python3 scripts/canva_sync.py --query "OM"    # different search term
  python3 scripts/canva_sync.py --dry-run       # list matches, no export/write

Config (env-overridable):
  PITCHDECK_SHEET_ID         Google Sheet to log into
  PITCHDECK_SHEET_TAB        Tab name (default: Sheet1)
  PITCHDECK_DRIVE_FOLDER_ID  Drive folder for archived PDFs
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

# Reuse the stdlib Google/Drive/Sheets infra from loom_sync (same repo).
import loom_sync as G
from loom_sync import _http, _auth, _load_dotenv, get_token, find_or_create_folder, slug

CANVA_BASE = "https://api.canva.com/rest/v1"

DEFAULT_QUERY = "Pitch Deck"
DRIVE_FOLDER_NAME = "Olive Tree Investments - Pitch Decks"
WIKI_DECKS_DIR = Path(__file__).parent.parent / "wiki" / "pitch-decks"

# Non-secret IDs default here so the cloud routine needs no extra env setup.
SHEET_TAB = os.environ.get("PITCHDECK_SHEET_TAB", "Sheet1")
SHEET_ID  = os.environ.get(
    "PITCHDECK_SHEET_ID", "1588hYP4Vc6F1ELEskmEWKm8USTmgZ0jNYn_dxVAI_yQ").strip()
DRIVE_FOLDER_ID = os.environ.get(
    "PITCHDECK_DRIVE_FOLDER_ID", "1adQqTkqe-DR69_NedjX5McapBHBS-zEI").strip()

SHEET_HEADER = [
    "Date Archived", "Title", "Design ID", "Canva Edit URL",
    "Drive PDF", "Pages", "Wiki Note", "Status",
]


# ─────────────────────────────────────────────
# Canva auth + API
# ─────────────────────────────────────────────

def _persist_env(key, value):
    """Best-effort write of key=value to ../.env (local only; no-op in cloud)."""
    import re
    env_path = Path(__file__).resolve().parent.parent / ".env"
    os.environ[key] = value
    if not env_path.exists():
        return
    value = value.replace("\n", "").replace("\r", "")
    content = env_path.read_text()
    pattern = rf"^{re.escape(key)}=.*$"
    if re.search(pattern, content, flags=re.MULTILINE):
        content = re.sub(pattern, lambda _m: f"{key}={value}", content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{key}={value}\n"
    tmp = env_path.with_suffix(".tmp")
    tmp.write_text(content)
    os.replace(tmp, env_path)


def _access_ok(token):
    try:
        _http("GET", f"{CANVA_BASE}/users/me",
              headers={"Authorization": f"Bearer {token}"}, timeout=15)
        return True
    except RuntimeError:
        return False


def canva_token(gtoken=None):
    """Return a working Canva access token.

    Canva refresh tokens are SINGLE-USE / rotating. The Drive token store
    (when gtoken is given) is the durable source of truth so cloud runs
    survive rotation; .env is the local copy. Order:
      1. If a Drive store exists, load its tokens into env (store wins for
         the refresh token — it's the freshest).
      2. Use the access token if still valid (avoids burning a refresh).
      3. Otherwise refresh, then persist the rotated pair to BOTH the store
         and .env.
    """
    store = None
    if gtoken is not None:
        try:
            import canva_token_store as store_mod
            store = store_mod
            saved = store.load_tokens(gtoken)
            if saved.get("refresh_token"):
                os.environ["CANVA_REFRESH_TOKEN"] = saved["refresh_token"]
            if saved.get("access_token"):
                os.environ["CANVA_ACCESS_TOKEN"] = saved["access_token"]
        except Exception:
            store = None  # fall back to env-only

    access = os.environ.get("CANVA_ACCESS_TOKEN", "").strip()
    if access and _access_ok(access):
        return access

    cid     = os.environ.get("CANVA_CLIENT_ID")
    secret  = os.environ.get("CANVA_CLIENT_SECRET")
    refresh = os.environ.get("CANVA_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        raise RuntimeError(
            "Missing CANVA_CLIENT_ID / CANVA_CLIENT_SECRET / CANVA_REFRESH_TOKEN.")
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    body = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh}).encode()
    try:
        resp = _http("POST", f"{CANVA_BASE}/oauth/token",
                     headers={"Authorization": f"Basic {basic}",
                              "Content-Type": "application/x-www-form-urlencoded"},
                     data=body, timeout=30)
    except RuntimeError as e:
        raise RuntimeError(
            "Canva refresh failed (token likely expired/rotated). "
            "Re-auth locally: python3 scripts/canva_oauth_setup.py, then "
            "re-seed the store: python3 scripts/canva_token_store.py seed") from e

    new_access = resp["access_token"]
    new_refresh = resp.get("refresh_token", refresh)
    # Persist the rotated pair everywhere so the next run has a valid token.
    _persist_env("CANVA_ACCESS_TOKEN", new_access)
    _persist_env("CANVA_REFRESH_TOKEN", new_refresh)
    if store is not None:
        try:
            store.save_tokens(gtoken,
                              {"access_token": new_access,
                               "refresh_token": new_refresh})
        except Exception as e:
            # The store is the cloud's source of truth — if this save fails,
            # the rotated token only lives in .env (local). Warn loudly so a
            # cloud run doesn't silently break next week with a stale token.
            print(f"  WARN: refreshed token NOT saved to Drive store ({e}). "
                  "Cloud runs may fail until re-seeded: "
                  "python3 scripts/canva_token_store.py seed", file=sys.stderr)
    return new_access


def canva_search(token, query, limit=100):
    """Return design items matching query (paginates via continuation token)."""
    items, cont = [], None
    while len(items) < limit:
        params = {"query": query}
        if cont:
            params["continuation"] = cont
        url = f"{CANVA_BASE}/designs?{urllib.parse.urlencode(params)}"
        data = _http("GET", url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        items.extend(data.get("items", []))
        cont = data.get("continuation")
        if not cont:
            break
    return items[:limit]


def canva_export_pdf(token, design_id, tries=40):
    """Start a PDF export job, poll to completion, return the download URL."""
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    job = _http("POST", f"{CANVA_BASE}/exports", headers=hdr,
                data=json.dumps({
                    "design_id": design_id,
                    "format": {"type": "pdf", "export_quality": "pro"},
                }).encode(), timeout=30).get("job", {})
    job_id = job.get("id")
    for _ in range(tries):
        status = _http("GET", f"{CANVA_BASE}/exports/{job_id}",
                       headers={"Authorization": f"Bearer {token}"}, timeout=30).get("job", {})
        st = status.get("status")
        if st == "success":
            # Export URLs are at job.urls (older API nested them under result).
            urls = status.get("urls") or status.get("result", {}).get("urls", [])
            if not urls:
                raise RuntimeError(f"export succeeded but no URL: {status}")
            return urls[0]
        if st == "failed":
            raise RuntimeError(f"Canva export failed: {status.get('error', status)}")
        time.sleep(2)
    raise RuntimeError("Canva export timed out")


# ─────────────────────────────────────────────
# Drive (PDF upload)
# ─────────────────────────────────────────────

def drive_upload_pdf(token, folder_id, filename, content):
    import uuid
    boundary = uuid.uuid4().hex
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
    resp = _http("POST", f"{G.DRIVE_UPLOAD}?uploadType=multipart&fields=id,webViewLink",
                 headers=headers, data=body, timeout=300)
    return resp.get("webViewLink", f"https://drive.google.com/file/d/{resp['id']}/view")


# ─────────────────────────────────────────────
# Sheets
# ─────────────────────────────────────────────

def get_existing_design_ids(token):
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
    return {row[2].strip() for row in rows[1:] if len(row) > 2 and row[2].strip()}


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

def write_wiki_note(date_str, title, design, drive_link):
    WIKI_DECKS_DIR.mkdir(parents=True, exist_ok=True)
    path = WIKI_DECKS_DIR / f"{slug(title)}.md"
    if path.exists():
        return path.name
    edit = design.get("urls", {}).get("edit_url", "")
    view = design.get("urls", {}).get("view_url", "")
    pages = design.get("page_count", "")
    lines = [
        f"# {title}",
        f"**Archived:** {date_str}  ",
        f"**Pages:** {pages}  ",
        f"**Canva (edit):** {edit or '—'}  ",
        f"**Canva (view):** {view or '—'}  ",
        f"**Drive (PDF):** {drive_link or '—'}",
        "",
        "## What this deck is for",
        "_Deal / audience / status._",
        "",
        "## Notes",
        "- ",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path.name


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def process_design(gtoken, ctoken, design, folder_id, dry_run):
    title = design.get("title") or f"Deck {design['id']}"
    pages = design.get("page_count", "")
    edit_url = design.get("urls", {}).get("edit_url", "")
    print(f"  • {title}  ({pages} pages)")
    if dry_run:
        print(f"      {design['id']}  (dry-run, not exported)")
        return None

    date_str = datetime.now().strftime("%m/%d/%Y")
    drive_link, status = "", "Archived"
    try:
        pdf_url = canva_export_pdf(ctoken, design["id"])
        content = _http("GET", pdf_url, headers={}, raw=True, timeout=300)
        fname = f"{slug(title)}.pdf"
        drive_link = drive_upload_pdf(gtoken, folder_id, fname, content)
        print(f"      exported + archived → Drive ({len(content)//1024} KB)")
    except RuntimeError as e:
        status = "Export failed"
        print(f"      WARN: {e}")

    wiki_name = write_wiki_note(date_str, title, design, drive_link)
    return [date_str, title, design["id"], edit_url, drive_link,
            str(pages), wiki_name, status]


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Olive Tree — Canva Pitch Deck Sync")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    global SHEET_ID, SHEET_TAB, DRIVE_FOLDER_ID
    SHEET_ID = os.environ.get("PITCHDECK_SHEET_ID", SHEET_ID).strip()
    SHEET_TAB = os.environ.get("PITCHDECK_SHEET_TAB", SHEET_TAB)
    DRIVE_FOLDER_ID = os.environ.get("PITCHDECK_DRIVE_FOLDER_ID", DRIVE_FOLDER_ID).strip()

    gtoken = get_token()
    ctoken = canva_token(gtoken)

    print(f"Searching Canva for '{args.query}'...")
    designs = canva_search(ctoken, args.query)
    print(f"  Found {len(designs)} design(s)")
    if not designs:
        print("Nothing to sync.")
        return

    existing = set()
    folder_id = DRIVE_FOLDER_ID
    if not args.dry_run:
        existing = get_existing_design_ids(gtoken)
        folder_id = DRIVE_FOLDER_ID or find_or_create_folder(gtoken, DRIVE_FOLDER_NAME)

    new_rows = []
    for design in designs:
        if design["id"] in existing:
            print(f"  • already archived: {design.get('title', design['id'])}")
            continue
        row = process_design(gtoken, ctoken, design, folder_id, args.dry_run)
        if row:
            new_rows.append(row)

    if new_rows:
        append_rows(gtoken, new_rows)
        print(f"\nDone. Archived {len(new_rows)} new deck(s).")
        print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    elif not args.dry_run:
        print("\nDone. No new decks to add.")


if __name__ == "__main__":
    main()
