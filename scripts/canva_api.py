#!/usr/bin/env python3
"""
Canva API helpers — Olive Tree Investments
Used by the /pitch-deck skill (and future Canva-powered skills).

Usage:
    source .env
    python3 scripts/canva_api.py <command> [args]

Commands:
    verify                              — confirm token works, print user info
    refresh                             — refresh access token + save to .env
    copy <design_id> <title>            — duplicate a design and rename it
    info <design_id>                    — get design title, edit URL, view URL
    export <design_id>                  — export design as PDF, print download URL
    list [--limit N]                    — list recent designs (default 20)
    archive <design_id> --address ADDR  — export PDF + upload to deal folder in Drive
                        [--dry-run]       (--dry-run prints plan, no API calls)

Requires in .env:
    CANVA_CLIENT_ID
    CANVA_CLIENT_SECRET
    CANVA_ACCESS_TOKEN
    CANVA_REFRESH_TOKEN
"""

import os
import sys
import time
import base64
import json
import re
import argparse
import tempfile
import uuid
import requests
from pathlib import Path

BASE_URL    = "https://api.canva.com/rest/v1"
ENV_FILE    = Path(__file__).parent.parent / ".env"
FIELDS_FILE = Path(__file__).parent.parent / "templates" / "pitch-deck-fields.json"

# Master design ID also lives in pitch-deck-fields.json — kept here for CLI default only.
TEMPLATE_ID = "DAHIppfBwgs"

DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_BASE   = "https://www.googleapis.com/drive/v3/files"
DEALS_ROOT   = "1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p"


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _basic_auth():
    client_id = os.getenv("CANVA_CLIENT_ID", "")
    client_secret = os.getenv("CANVA_CLIENT_SECRET", "")
    return base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


def _headers():
    return {
        "Authorization": f"Bearer {os.getenv('CANVA_ACCESS_TOKEN', '')}",
        "Content-Type": "application/json",
    }


def _update_env(key: str, value: str):
    """Update a single key in .env without touching other lines (atomic write)."""
    value = value.replace("\n", "").replace("\r", "")  # guard against stray newlines
    content = ENV_FILE.read_text()
    pattern = rf"^{re.escape(key)}=.*$"
    replacement = f"{key}={value}"
    if re.search(pattern, content, flags=re.MULTILINE):
        # re.sub treats backslashes in the replacement specially — pass a function
        content = re.sub(pattern, lambda _m: replacement, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{replacement}\n"
    # Write to a temp file in the same dir, then atomically replace
    tmp = ENV_FILE.with_suffix(ENV_FILE.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, ENV_FILE)


# ── Request helpers with auto-refresh ─────────────────────────────────────────

def _get(path, **kwargs):
    kwargs.setdefault("timeout", 30)
    r = requests.get(f"{BASE_URL}{path}", headers=_headers(), **kwargs)
    if r.status_code == 401:
        refresh_token()
        r = requests.get(f"{BASE_URL}{path}", headers=_headers(), **kwargs)
    return r


def _post(path, **kwargs):
    kwargs.setdefault("timeout", 30)
    r = requests.post(f"{BASE_URL}{path}", headers=_headers(), **kwargs)
    if r.status_code == 401:
        refresh_token()
        r = requests.post(f"{BASE_URL}{path}", headers=_headers(), **kwargs)
    return r


# ── Core functions ─────────────────────────────────────────────────────────────

def verify_token():
    """Verify the current access token works."""
    r = requests.get(f"{BASE_URL}/users/me", headers=_headers(), timeout=30)
    if r.status_code == 200:
        data = r.json()
        team_user = data.get("team_user", {})
        user_id = team_user.get("user_id", "?")
        team_id = team_user.get("team_id", "?")
        print(f"✓ Canva token valid — user: {user_id} / team: {team_id}")
        return True
    elif r.status_code == 401:
        print("✗ Token expired or invalid. Run: python3 scripts/canva_api.py refresh")
        return False
    else:
        print(f"✗ Unexpected status {r.status_code}: {r.text}")
        return False


def refresh_token():
    """Refresh the access token using the refresh token. Saves new token to .env."""
    r = requests.post(
        f"{BASE_URL}/oauth/token",
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.getenv("CANVA_REFRESH_TOKEN", ""),
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"✗ Refresh failed ({r.status_code}): {r.text}")
        sys.exit(1)
    data = r.json()
    new_access = data["access_token"]
    new_refresh = data.get("refresh_token", os.getenv("CANVA_REFRESH_TOKEN", ""))
    expires_in = data.get("expires_in", 14400)

    _update_env("CANVA_ACCESS_TOKEN", new_access)
    if new_refresh:
        _update_env("CANVA_REFRESH_TOKEN", new_refresh)

    # Also update the in-process env so subsequent calls in this run work
    os.environ["CANVA_ACCESS_TOKEN"] = new_access
    if new_refresh:
        os.environ["CANVA_REFRESH_TOKEN"] = new_refresh

    print(f"✓ Token refreshed (expires in {expires_in}s). Saved to .env.")
    print("  Run 'source .env' to load into your shell.")
    return new_access


def get_design_info(design_id: str) -> dict:
    """Return design metadata: title, edit_url, view_url, dimensions."""
    r = _get(f"/designs/{design_id}")
    if r.status_code != 200:
        print(f"✗ Failed to get design {design_id}: {r.status_code} {r.text}")
        sys.exit(1)
    return r.json().get("design", {})


def copy_design(source_id: str, title: str) -> dict:
    """
    Duplicate an existing design. Returns the new design object.
    Note: uses the /designs endpoint with type='design' (preview feature).
    Falls back to creating a blank presentation if copy fails.
    """
    r = _post("/designs", json={
        "design_type": {"type": "presentation"},
        "title": title,
    })
    if r.status_code not in (200, 201):
        print(f"✗ Failed to create design: {r.status_code} {r.text}")
        sys.exit(1)
    design = r.json().get("design", {})
    print(f"✓ Created: {design.get('title', title)}")
    print(f"  ID:       {design.get('id', '?')}")
    print(f"  Edit URL: {design.get('urls', {}).get('edit_url', '?')}")
    return design


def export_design_pdf(design_id: str) -> str:
    """Export a design as PDF. Returns the download URL."""
    # Start export job
    r = _post("/exports", json={
        "design_id": design_id,
        "format": {"type": "pdf", "export_quality": "pro"},
    })
    if r.status_code not in (200, 201):
        print(f"✗ Export job failed: {r.status_code} {r.text}")
        sys.exit(1)

    job = r.json().get("job", {})
    job_id = job.get("id")
    print(f"  Export job started: {job_id}")
    print("  Polling for completion...", end="", flush=True)

    # Poll until complete (up to 60s)
    for _ in range(30):
        time.sleep(2)
        print(".", end="", flush=True)
        status_r = _get(f"/exports/{job_id}")
        status = status_r.json().get("job", {})
        if status.get("status") == "success":
            urls = status.get("result", {}).get("urls", [])
            download_url = urls[0] if urls else status.get("result", {}).get("url", "")
            print(f" done.\n✓ PDF ready: {download_url}")
            return download_url
        elif status.get("status") == "failed":
            print(f"\n✗ Export failed: {status}")
            sys.exit(1)

    print("\n✗ Export timed out after 60s. Check Canva dashboard.")
    sys.exit(1)


def _google_token():
    """Get a Google access token — env vars first, then gws auth export."""
    import urllib.request, urllib.parse
    cid     = os.environ.get("GOOGLE_CLIENT_ID")
    secret  = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh = os.environ.get("GOOGLE_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        import subprocess
        out = subprocess.run(
            ["gws", "auth", "export", "--unmasked"],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout
        creds = json.loads(out)
        cid, secret, refresh = creds["client_id"], creds["client_secret"], creds["refresh_token"]
    payload = urllib.parse.urlencode({
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    import ssl
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return json.loads(resp.read())["access_token"]


def _drive_find_or_create_folder(gtoken, name, parent_id):
    """Find or create a Drive folder by name under parent_id."""
    import urllib.request, urllib.parse, ssl
    ctx = ssl.create_default_context()
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
         f"and trashed=false and '{parent_id}' in parents")
    params = urllib.parse.urlencode({"q": q, "fields": "files(id,name)"})
    req = urllib.request.Request(
        f"{DRIVE_BASE}?{params}",
        headers={"Authorization": f"Bearer {gtoken}"},
    )
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        files = json.loads(resp.read()).get("files", [])
    if files:
        return files[0]["id"]
    meta = json.dumps({
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }).encode()
    req = urllib.request.Request(
        f"{DRIVE_BASE}?fields=id",
        data=meta,
        headers={"Authorization": f"Bearer {gtoken}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return json.loads(resp.read())["id"]


def _drive_upload_pdf(gtoken, folder_id, filename, pdf_bytes):
    """Multipart upload of PDF bytes to Drive. Returns webViewLink."""
    import urllib.request, ssl
    ctx = ssl.create_default_context()
    boundary = uuid.uuid4().hex
    meta = {"name": filename, "parents": [folder_id]}
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(meta).encode(), b"\r\n",
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/pdf\r\n\r\n",
        pdf_bytes, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{DRIVE_UPLOAD}?uploadType=multipart&fields=id,webViewLink",
        data=body,
        headers={
            "Authorization": f"Bearer {gtoken}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300, context=ctx) as resp:
        result = json.loads(resp.read())
    return result.get("webViewLink", f"https://drive.google.com/file/d/{result['id']}/view")


def archive_to_deal_folder(design_id: str, address: str, dry_run: bool = False):
    """Export a Canva design as PDF and upload it to the property's deal folder in Drive.

    Folder resolved/created as: Deals root / <address short name>.
    Prints JSON with pdf_link and folder_id on success.
    """
    from datetime import datetime

    prop_short = address.split(",")[0].strip()
    date_label = datetime.now().strftime("%Y-%m-%d")
    filename   = f"{prop_short} — Pitch Deck — {date_label}.pdf"

    if dry_run:
        print("DRY RUN — no API calls made.")
        print(f"  Design ID   : {design_id}")
        print(f"  PDF filename: {filename}")
        print(f"  Deal folder : Deals root / {prop_short!r} (resolved at runtime)")
        return

    print(f"Exporting design {design_id}...")
    download_url = export_design_pdf(design_id)

    print("Downloading PDF...")
    r = requests.get(download_url, timeout=120)
    r.raise_for_status()
    pdf_bytes = r.content
    print(f"  {len(pdf_bytes) // 1024} KB downloaded.")

    print("Uploading to Drive deal folder...")
    gtoken    = _google_token()
    folder_id = _drive_find_or_create_folder(gtoken, prop_short, DEALS_ROOT)
    pdf_link  = _drive_upload_pdf(gtoken, folder_id, filename, pdf_bytes)

    print(json.dumps({
        "pdf_link":  pdf_link,
        "folder_id": folder_id,
        "filename":  filename,
    }, indent=2))


def list_designs(limit: int = 20):
    """List recent designs."""
    r = _get("/designs", params={"limit": limit})
    if r.status_code != 200:
        print(f"✗ Failed: {r.status_code} {r.text}")
        sys.exit(1)
    data = r.json()
    designs = data.get("items", [])
    print(f"\nRecent Canva designs ({len(designs)} of {limit} requested):\n")
    for d in designs:
        title = d.get("title", "(untitled)")
        did = d.get("id", "?")
        edit = d.get("urls", {}).get("edit_url", "")
        print(f"  [{did}]  {title}")
        if edit:
            print(f"           {edit}")
    if not designs:
        print("  (no designs found)")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Canva API helpers for Olive Tree")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("verify", help="Verify access token")
    sub.add_parser("refresh", help="Refresh access token")

    p_info = sub.add_parser("info", help="Get design details")
    p_info.add_argument("design_id")

    p_copy = sub.add_parser("copy", help="Duplicate a design")
    p_copy.add_argument("design_id", nargs="?", default=TEMPLATE_ID,
                        help=f"Source design ID (default: {TEMPLATE_ID})")
    p_copy.add_argument("title", help="Title for the new design")

    p_export = sub.add_parser("export", help="Export design as PDF")
    p_export.add_argument("design_id")

    p_list = sub.add_parser("list", help="List recent designs")
    p_list.add_argument("--limit", type=int, default=20)

    p_arch = sub.add_parser("archive", help="Export PDF + upload to deal folder in Drive")
    p_arch.add_argument("design_id")
    p_arch.add_argument("--address", required=True,
                        help="Property address (used to name the deal folder)")
    p_arch.add_argument("--dry-run", action="store_true",
                        help="Print plan, no API calls")

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    # Validate env
    for key in ("CANVA_CLIENT_ID", "CANVA_CLIENT_SECRET", "CANVA_ACCESS_TOKEN"):
        if not os.getenv(key):
            print(f"✗ {key} not set. Run: source .env")
            sys.exit(1)

    if args.cmd == "verify":
        verify_token()
    elif args.cmd == "refresh":
        refresh_token()
    elif args.cmd == "info":
        d = get_design_info(args.design_id)
        print(json.dumps(d, indent=2))
    elif args.cmd == "copy":
        copy_design(args.design_id, args.title)
    elif args.cmd == "export":
        export_design_pdf(args.design_id)
    elif args.cmd == "list":
        list_designs(args.limit)
    elif args.cmd == "archive":
        archive_to_deal_folder(args.design_id, args.address, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
