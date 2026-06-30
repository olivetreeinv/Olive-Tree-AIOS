#!/usr/bin/env python3
"""
Olive Tree Investments — Loom Sync

Pulls Loom share links out of Gmail (videos Brian shares to
brian@olivetreeinv.io), downloads the MP4, archives it to Google Drive,
logs a row to the Looms sheet, and writes a wiki note per video.
Skips videos already logged (deduped by Loom share URL).

Stdlib-only (urllib) so it runs in the cloud schedule with the laptop off.
Auth: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN
(read from env or ../.env). Falls back to `gws auth export` locally.

Usage:
  python3 scripts/loom_sync.py                 # sync last 8 days (default)
  python3 scripts/loom_sync.py --days 30       # look back N days
  python3 scripts/loom_sync.py --dry-run       # find links, no download/write
  python3 scripts/loom_sync.py --url <share>   # process one share URL directly

Config (env-overridable):
  LOOM_SHEET_ID         Google Sheet to log into
  LOOM_SHEET_TAB        Tab name (default: Looms)
  LOOM_DRIVE_FOLDER_ID  Drive folder for archived MP4s (auto-created if unset)
"""

import argparse
import base64
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(cafile=certifi.where())
except Exception:
    pass

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

TOKEN_URL   = "https://oauth2.googleapis.com/token"
GMAIL_BASE  = "https://gmail.googleapis.com/gmail/v1/users/me"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_BASE  = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

DEFAULT_DAYS   = 8
DRIVE_FOLDER_NAME = "Olive Tree Investments - Looms"
WIKI_LOOMS_DIR = Path(__file__).parent.parent / "wiki" / "looms"

# Non-secret IDs default here so the cloud routine works without extra env
# setup; override via env if they ever change.
SHEET_TAB = os.environ.get("LOOM_SHEET_TAB", "Looms")
SHEET_ID  = os.environ.get(
    "LOOM_SHEET_ID", "17hWdl1pzA1Ifr_5gAmWUEteEbAJOtW3my_XYS7AUjBw").strip()
DRIVE_FOLDER_ID = os.environ.get(
    "LOOM_DRIVE_FOLDER_ID", "18SRZ-FXvAwE6A9kQ7EdMZRrnZcejIr4A").strip()

# Columns logged to the sheet (header written on first run)
SHEET_HEADER = [
    "Date Shared", "Title", "Loom URL", "Drive MP4", "Description",
    "Wiki Note", "Status",
]

LOOM_SHARE_RE = re.compile(r"https?://(?:www\.)?loom\.com/share/([0-9a-fA-F]{16,})")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# ─────────────────────────────────────────────
# Infra / auth
# ─────────────────────────────────────────────

def _load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _http(method, url, headers=None, data=None, raw=False, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            payload = resp.read()
            return payload if raw else json.loads(payload.decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {body[:300]}") from e


def get_token():
    """Prefer GOOGLE_* env (cloud + local .env); fall back to gws export."""
    cid     = os.environ.get("GOOGLE_CLIENT_ID")
    secret  = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh = os.environ.get("GOOGLE_REFRESH_TOKEN")

    if not (cid and secret and refresh):
        try:
            out = subprocess.run(
                ["gws", "auth", "export", "--unmasked"],
                capture_output=True, text=True, check=True, timeout=30,
            ).stdout
            creds = json.loads(out)
            cid, secret, refresh = (
                creds["client_id"], creds["client_secret"], creds["refresh_token"],
            )
        except Exception as e:
            raise RuntimeError(
                "No Google creds. Set GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN "
                "in .env, or run: gws auth login -s gmail,drive,sheets"
            ) from e

    payload = urllib.parse.urlencode({
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token",
    }).encode()
    resp = _http("POST", TOKEN_URL,
                 headers={"Content-Type": "application/x-www-form-urlencoded"},
                 data=payload, timeout=30)
    return resp["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────
# Gmail — find Loom share links
# ─────────────────────────────────────────────

def gmail_search(token, days):
    after = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"loom.com/share after:{after}"
    params = urllib.parse.urlencode({"q": query, "maxResults": "50"})
    data = _http("GET", f"{GMAIL_BASE}/messages?{params}", headers=_auth(token), timeout=30)
    return [m["id"] for m in data.get("messages", [])]


def _b64decode(data):
    return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")


def gmail_message(token, msg_id):
    data = _http("GET", f"{GMAIL_BASE}/messages/{msg_id}?format=full",
                 headers=_auth(token), timeout=30)
    headers = {h["name"].lower(): h["value"]
               for h in data.get("payload", {}).get("headers", [])}

    # Walk all parts collecting decoded text
    text = []

    def walk(part):
        body = part.get("body", {})
        if body.get("data"):
            text.append(_b64decode(body["data"]))
        for sub in part.get("parts", []):
            walk(sub)

    walk(data.get("payload", {}))
    blob = "\n".join(text)
    return {
        "date":    headers.get("date", ""),
        "subject": headers.get("subject", ""),
        "body":    blob,
        "snippet": data.get("snippet", ""),
    }


def find_loom_links(token, days):
    """Return list of (loom_url, video_id, email_meta) for unique videos."""
    found = {}
    for msg_id in gmail_search(token, days):
        try:
            msg = gmail_message(token, msg_id)
        except RuntimeError:
            continue
        for m in LOOM_SHARE_RE.finditer(msg["body"] + " " + msg["snippet"]):
            url = f"https://www.loom.com/share/{m.group(1)}"
            if m.group(1) not in found:
                found[m.group(1)] = (url, m.group(1), msg)
    return list(found.values())


# ─────────────────────────────────────────────
# Loom — title + MP4 URL
# ─────────────────────────────────────────────

def loom_page(video_id):
    url = f"https://www.loom.com/share/{video_id}"
    try:
        html = _http("GET", url, headers={"User-Agent": BROWSER_UA}, raw=True, timeout=60)
        return html.decode("utf-8", errors="replace")
    except RuntimeError:
        return ""


def _meta(html, prop):
    m = re.search(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
        html,
    )
    return m.group(1).strip() if m else ""


def loom_mp4_url(video_id, html=""):
    """Resolve a downloadable MP4 URL. Tries the API endpoint, then HTML scrape."""
    # 1) Official-ish transcoded-url endpoint (works for public videos)
    try:
        data = _http(
            "POST",
            f"https://www.loom.com/api/campaigns/sessions/{video_id}/transcoded-url",
            headers={"User-Agent": BROWSER_UA, "Content-Type": "application/json"},
            data=b"{}", timeout=60,
        )
        if data.get("url"):
            return data["url"]
    except RuntimeError:
        pass

    # 2) Regex the CDN link out of the share page HTML
    m = re.search(
        r"https://cdn\.loom\.com/sessions/(?:transcoded|raw)/[^\"'\s\\]+\.mp4", html)
    return m.group(0) if m else ""


# ─────────────────────────────────────────────
# Drive
# ─────────────────────────────────────────────

def find_folder(token, name, parent_id=None):
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
         "and trashed=false")
    if parent_id:
        q += f" and '{parent_id}' in parents"
    params = urllib.parse.urlencode({"q": q, "fields": "files(id,name)"})
    data = _http("GET", f"{DRIVE_BASE}/files?{params}", headers=_auth(token), timeout=30)
    files = data.get("files", [])
    return files[0]["id"] if files else None


def find_or_create_folder(token, name, parent_id=None):
    existing = find_folder(token, name, parent_id)
    if existing:
        return existing
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    created = _http("POST", f"{DRIVE_BASE}/files?fields=id",
                    headers={**_auth(token), "Content-Type": "application/json"},
                    data=json.dumps(meta).encode(), timeout=30)
    return created["id"]


def drive_upload_mp4(token, folder_id, filename, content):
    """Multipart upload of MP4 bytes; returns webViewLink."""
    boundary = uuid.uuid4().hex
    meta = {"name": filename, "parents": [folder_id]}
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(meta).encode(), b"\r\n",
        f"--{boundary}\r\n".encode(),
        b"Content-Type: video/mp4\r\n\r\n",
        content, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    headers = {
        **_auth(token),
        "Content-Type": f"multipart/related; boundary={boundary}",
    }
    resp = _http("POST", f"{DRIVE_UPLOAD}?uploadType=multipart&fields=id,webViewLink",
                 headers=headers, data=body, timeout=300)
    # Make it link-viewable so the sheet link is useful
    try:
        _http("POST", f"{DRIVE_BASE}/files/{resp['id']}/permissions",
              headers={**_auth(token), "Content-Type": "application/json"},
              data=json.dumps({"role": "reader", "type": "anyone"}).encode(),
              timeout=30)
    except RuntimeError:
        pass
    return resp.get("webViewLink", f"https://drive.google.com/file/d/{resp['id']}/view")


# ─────────────────────────────────────────────
# Sheets
# ─────────────────────────────────────────────

def ensure_sheet_tab(token):
    meta = _http("GET", f"{SHEETS_BASE}/{SHEET_ID}", headers=_auth(token), timeout=30)
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if SHEET_TAB in tabs:
        return
    body = {"requests": [{"addSheet": {"properties": {"title": SHEET_TAB}}}]}
    _http("POST", f"{SHEETS_BASE}/{SHEET_ID}:batchUpdate",
          headers={**_auth(token), "Content-Type": "application/json"},
          data=json.dumps(body).encode(), timeout=30)


def get_existing_loom_urls(token):
    rng = urllib.parse.quote(f"{SHEET_TAB}!A1:G")
    try:
        data = _http("GET", f"{SHEETS_BASE}/{SHEET_ID}/values/{rng}",
                     headers=_auth(token), timeout=30)
    except RuntimeError:
        return set()
    rows = data.get("values", [])
    if not rows:  # write header
        append_rows(token, [SHEET_HEADER])
        return set()
    return {row[2].strip() for row in rows[1:] if len(row) > 2 and row[2].strip()}


def append_rows(token, rows):
    rng = urllib.parse.quote(f"{SHEET_TAB}!A1")
    _http("POST",
          f"{SHEETS_BASE}/{SHEET_ID}/values/{rng}:append"
          "?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS",
          headers={**_auth(token), "Content-Type": "application/json"},
          data=json.dumps({"values": rows, "majorDimension": "ROWS"}).encode(),
          timeout=30)


# ─────────────────────────────────────────────
# Wiki
# ─────────────────────────────────────────────

def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "loom").lower()).strip("-")[:60] or "loom"


def write_wiki_note(date_str, title, loom_url, drive_link, description):
    WIKI_LOOMS_DIR.mkdir(parents=True, exist_ok=True)
    iso = "0000-00-00"
    try:
        iso = datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    path = WIKI_LOOMS_DIR / f"{iso}-{slug(title)}.md"
    if path.exists():
        return path.name
    lines = [
        f"# {title}",
        f"**Date Shared:** {date_str}  ",
        f"**Loom:** {loom_url}  ",
        f"**Drive (MP4):** {drive_link or '—'}",
        "",
        "## Summary",
        description or "_Add notes here._",
        "",
        "## Key Points",
        "- ",
        "",
        "## Related",
        "- ",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path.name


# ─────────────────────────────────────────────
# Per-video processing
# ─────────────────────────────────────────────

def parse_email_date(date_header):
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(date_header.strip(), fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return datetime.now().strftime("%m/%d/%Y")


def process_video(token, loom_url, video_id, email, folder_id, dry_run):
    html = loom_page(video_id)
    title = _meta(html, "og:title") or email.get("subject") or f"Loom {video_id[:8]}"
    title = re.sub(r"\s*[\|·]\s*Loom\s*$", "", title).strip()
    description = _meta(html, "og:description") or email.get("snippet", "")
    date_str = parse_email_date(email.get("date", "")) if email.get("date") else \
        datetime.now().strftime("%m/%d/%Y")

    print(f"  • {title}")
    if dry_run:
        print(f"      {loom_url}  (dry-run, not downloaded)")
        return None

    drive_link = ""
    status = "Logged"
    mp4_url = loom_mp4_url(video_id, html)
    if mp4_url:
        try:
            content = _http("GET", mp4_url, headers={"User-Agent": BROWSER_UA},
                            raw=True, timeout=300)
            fname = f"{date_str.replace('/', '-')}-{slug(title)}.mp4"
            drive_link = drive_upload_mp4(token, folder_id, fname, content)
            print(f"      archived → Drive ({len(content)//1024} KB)")
        except RuntimeError as e:
            status = "Link only (download failed)"
            print(f"      WARN: download/upload failed: {e}")
    else:
        status = "Link only (no MP4 — is it public?)"
        print("      WARN: could not resolve MP4 (set video to 'anyone with link')")

    wiki_name = write_wiki_note(date_str, title, loom_url, drive_link, description)
    return [date_str, title, loom_url, drive_link, description[:500], wiki_name, status]


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Olive Tree — Loom Sync")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--url", help="Process a single Loom share URL")
    args = parser.parse_args()

    global DRIVE_FOLDER_ID, SHEET_ID, SHEET_TAB
    SHEET_ID = os.environ.get("LOOM_SHEET_ID", SHEET_ID).strip()
    SHEET_TAB = os.environ.get("LOOM_SHEET_TAB", SHEET_TAB)
    DRIVE_FOLDER_ID = os.environ.get("LOOM_DRIVE_FOLDER_ID", DRIVE_FOLDER_ID).strip()
    token = get_token()

    # Resolve videos to process
    if args.url:
        m = LOOM_SHARE_RE.search(args.url)
        if not m:
            print("ERROR: not a Loom share URL (need loom.com/share/<id>)")
            sys.exit(1)
        videos = [(f"https://www.loom.com/share/{m.group(1)}", m.group(1),
                   {"date": "", "subject": "", "snippet": "", "body": ""})]
    else:
        print(f"Scanning Gmail for Loom links (last {args.days} days)...")
        videos = find_loom_links(token, args.days)
        print(f"  Found {len(videos)} unique Loom video(s)")

    if not videos:
        print("Nothing to sync.")
        return

    if not args.dry_run and not SHEET_ID:
        print("ERROR: LOOM_SHEET_ID not set. Add it to .env "
              "(or run with --dry-run to just list links).")
        sys.exit(1)

    folder_id = None
    existing = set()
    if not args.dry_run:
        ensure_sheet_tab(token)
        existing = get_existing_loom_urls(token)
        folder_id = DRIVE_FOLDER_ID or find_or_create_folder(token, DRIVE_FOLDER_NAME)

    new_rows = []
    for loom_url, video_id, email in videos:
        if loom_url in existing:
            print(f"  • already logged: {loom_url}")
            continue
        row = process_video(token, loom_url, video_id, email, folder_id, args.dry_run)
        if row:
            new_rows.append(row)

    if new_rows:
        append_rows(token, new_rows)
        print(f"\nDone. Logged {len(new_rows)} new video(s) to '{SHEET_TAB}'.")
        print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    elif not args.dry_run:
        print("\nDone. No new videos to add.")


if __name__ == "__main__":
    main()
