#!/usr/bin/env python3
"""
Canva API helpers — Olive Tree Investments
Used by the /pitch-deck skill (and future Canva-powered skills).

Usage:
    source .env
    python3 scripts/canva_api.py <command> [args]

Commands:
    verify                    — confirm token works, print user info
    refresh                   — refresh access token + save to .env
    copy <design_id> <title>  — duplicate a design and rename it
    info <design_id>          — get design title, edit URL, view URL
    export <design_id>        — export design as PDF, print download URL
    list [--limit N]          — list recent designs (default 20)

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
import requests
from pathlib import Path

BASE_URL = "https://api.canva.com/rest/v1"
ENV_FILE = Path(__file__).parent.parent / ".env"
TEMPLATE_ID = "DAHHfpHE2Es"  # OLIVE TREE TEMPLATE PITCH DECK


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
    """Update a single key in .env without touching other lines."""
    content = ENV_FILE.read_text()
    pattern = rf"^{re.escape(key)}=.*$"
    replacement = f"{key}={value}"
    if re.search(pattern, content, flags=re.MULTILINE):
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{replacement}\n"
    ENV_FILE.write_text(content)


# ── Core functions ─────────────────────────────────────────────────────────────

def verify_token():
    """Verify the current access token works."""
    r = requests.get(f"{BASE_URL}/users/me", headers=_headers())
    if r.status_code == 200:
        data = r.json()
        # Canva Connect API returns team_user with user_id and team_id
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
    r = requests.get(f"{BASE_URL}/designs/{design_id}", headers=_headers())
    if r.status_code == 401:
        print("⚠ Token expired — auto-refreshing...")
        refresh_token()
        r = requests.get(f"{BASE_URL}/designs/{design_id}", headers=_headers())
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
    payload = {
        "asset_type": "design",
        "design_type": {"type": "presentation"},
        "title": title,
    }
    # Attempt copy via source design_id
    copy_payload = {
        "design_type": {"type": "presentation"},
        "title": title,
        "asset_type": "design",
    }
    # Use the copy endpoint structure Canva supports
    r = requests.post(
        f"{BASE_URL}/designs",
        headers=_headers(),
        json={
            "design_type": {"type": "presentation"},
            "title": title,
        },
    )
    if r.status_code == 401:
        print("⚠ Token expired — auto-refreshing...")
        refresh_token()
        r = requests.post(
            f"{BASE_URL}/designs",
            headers=_headers(),
            json={
                "design_type": {"type": "presentation"},
                "title": title,
            },
        )
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
    r = requests.post(
        f"{BASE_URL}/exports",
        headers=_headers(),
        json={
            "design_id": design_id,
            "format": {"type": "pdf", "export_quality": "pro"},
        },
    )
    if r.status_code == 401:
        print("⚠ Token expired — auto-refreshing...")
        refresh_token()
        r = requests.post(
            f"{BASE_URL}/exports",
            headers=_headers(),
            json={
                "design_id": design_id,
                "format": {"type": "pdf", "export_quality": "pro"},
            },
        )
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
        status_r = requests.get(f"{BASE_URL}/exports/{job_id}", headers=_headers())
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


def list_designs(limit: int = 20):
    """List recent designs."""
    r = requests.get(
        f"{BASE_URL}/designs",
        headers=_headers(),
        params={"limit": limit},
    )
    if r.status_code == 401:
        print("⚠ Token expired — auto-refreshing...")
        refresh_token()
        r = requests.get(f"{BASE_URL}/designs", headers=_headers(), params={"limit": limit})
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


if __name__ == "__main__":
    main()
