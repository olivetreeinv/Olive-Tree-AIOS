#!/usr/bin/env python3
"""
Olive Tree Investments — Deal Archive Script

Creates a dated subfolder in the "Deals" Drive folder for a passed
deal, auto-generates a Deal Summary, and uploads all pertinent documents.

Can be called standalone or triggered automatically by deal_analysis.py --archive.

Usage:
  # Standalone
  python3 scripts/deal_archive.py \
    --address "123 Main St, Chamblee, GA 30341" \
    --property "Maple Terrace" \
    --files /tmp/om.pdf /tmp/t12.pdf /tmp/rentroll.pdf

  # Dry run
  python3 scripts/deal_archive.py \
    --address "123 Main St, Chamblee, GA 30341" \
    --dry-run
"""

import argparse
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests
from gws_auth import get_token

PARENT_FOLDER_ID = "1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p"
DRIVE_BASE  = "https://www.googleapis.com/drive/v3/files"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3/files"
TODAY_ISO   = date.today().strftime("%Y-%m-%d")

MIME_MAP = {
    ".pdf":  "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":  "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc":  "application/msword",
    ".csv":  "text/csv",
    ".txt":  "text/plain",
    ".md":   "text/plain",
    ".json": "application/json",
}


def create_folder(token, name, parent_id):
    r = requests.post(
        DRIVE_BASE,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def upload_file(token, folder_id, filepath, display_name=None):
    filename = display_name or os.path.basename(filepath)
    ext  = os.path.splitext(filename)[1].lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")

    with open(filepath, "rb") as f:
        file_bytes = f.read()

    metadata  = json.dumps({"name": filename, "parents": [folder_id]})
    boundary  = "boundary_oti_archive"
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--".encode()

    r = requests.post(
        f"{UPLOAD_BASE}?uploadType=multipart",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("id")


def _fmt_dollar(v):
    return f"${v:,.0f}" if v is not None else "N/A"

def _fmt_pct(v):
    return f"{v:.1%}" if v is not None else "N/A"

def _fmt_x(v):
    return f"{v:.2f}x" if v is not None else "N/A"


def generate_summary(address, property_name, metrics, notes=""):
    lines = [
        "DEAL SUMMARY — PASS",
        "=" * 52,
        "",
        f"Property : {property_name or address}",
        f"Address  : {address}",
        f"Date     : {TODAY_ISO}",
        f"Verdict  : PASS",
        "",
    ]

    if metrics:
        lines += [
            "KEY METRICS",
            "-----------",
            f"Asking Price     : {_fmt_dollar(metrics.get('asking'))}",
            f"Units            : {metrics.get('units', 'N/A')}",
            f"Price / Unit     : {_fmt_dollar(metrics.get('ppu'))}",
            f"All-In Cost      : {_fmt_dollar(metrics.get('all_in'))}",
            "",
            f"Entry Cap        : {_fmt_pct(metrics.get('entry_cap') / 100) if metrics.get('entry_cap') else 'N/A'}",
            f"Exit Cap (est.)  : {_fmt_pct(metrics.get('exit_cap') / 100) if metrics.get('exit_cap') else 'N/A'}",
            f"Current NOI      : {_fmt_dollar(metrics.get('current_noi'))}",
            f"Stabilized NOI   : {_fmt_dollar(metrics.get('stabilized_noi'))}",
            "",
            f"DSCR             : {_fmt_x(metrics.get('dscr'))}",
            f"CoC Yr3 (est.)   : {_fmt_pct(metrics.get('coc_yr3'))}",
            f"IRR (est.)       : {_fmt_pct(metrics.get('irr_estimate'))}",
            f"Equity Multiple  : {_fmt_x(metrics.get('equity_multiple'))}",
            f"75% Rule         : {_fmt_pct(metrics.get('rule_75_ratio'))} "
            + (f"({'PASS' if metrics.get('rule_75_pass') else 'FAIL'})" if metrics.get('rule_75_pass') is not None else "(N/A)"),
            "",
        ]

    if notes:
        lines += ["REASON FOR PASS", "---------------", notes, ""]

    lines += ["=" * 52, "Archived by Olive Tree AIOS — deal_archive.py"]
    return "\n".join(lines)


def archive_deal(token, address, property_name="", metrics=None, notes="", files=None, dry_run=False):
    """
    Main entry point. Creates dated Drive folder, uploads summary + any provided files.
    Returns folder_id (or None on dry run).
    """
    folder_name = f"{TODAY_ISO} — {address}"
    files = files or []

    if dry_run:
        print(f"[DRY RUN] Would create: {folder_name}")
        print(f"[DRY RUN] Would upload: Deal Summary — {address}.txt")
        for fp in files:
            print(f"[DRY RUN] Would upload: {os.path.basename(fp)}")
        return None

    print(f"\nArchiving: {folder_name}")
    folder_id = create_folder(token, folder_name, PARENT_FOLDER_ID)
    print(f"✅ Folder created")
    print(f"   https://drive.google.com/drive/folders/{folder_id}")

    # Generate + upload Deal Summary
    summary_text = generate_summary(address, property_name, metrics, notes)
    summary_name = f"Deal Summary — {address}.txt"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(summary_text)
        tmp_path = tmp.name
    try:
        upload_file(token, folder_id, tmp_path, display_name=summary_name)
        print(f"✅ Uploaded: {summary_name}")
    finally:
        os.unlink(tmp_path)

    # Upload additional files (independent — run in parallel)
    existing = [fp for fp in files if os.path.exists(fp)]
    skipped = 0
    for fp in files:
        if fp not in existing:
            print(f"⚠️  Not found, skipping: {fp}")
            skipped += 1

    def _upload(filepath):
        upload_file(token, folder_id, filepath)
        return filepath

    if existing:
        with ThreadPoolExecutor(max_workers=5) as executor:
            for filepath in executor.map(_upload, existing):
                print(f"✅ Uploaded: {os.path.basename(filepath)}")

    uploaded = len(existing) + 1  # +1 for the Deal Summary
    print(f"\n{uploaded} file(s) archived → '{folder_name}'\n")
    return folder_id


def main():
    p = argparse.ArgumentParser(description="Olive Tree — Deal Archive")
    p.add_argument("--address",      required=True, help="Full property address (used as folder name)")
    p.add_argument("--property",     default="",    help="Property name (for summary header)")
    p.add_argument("--notes",        default="",    help="Reason for pass / freeform notes")
    p.add_argument("--files",        nargs="*", default=[], metavar="FILE",
                   help="Local file paths to upload (OM, T-12, Rent Roll, etc.)")
    p.add_argument("--metrics-json", default="",
                   help="JSON metrics dict from deal_analysis.py (populates summary)")
    p.add_argument("--dry-run",      action="store_true", help="Print without executing")
    args = p.parse_args()

    metrics = None
    if args.metrics_json:
        try:
            metrics = json.loads(args.metrics_json)
        except json.JSONDecodeError as e:
            print(f"⚠️  Could not parse --metrics-json: {e}")

    token = None
    if not args.dry_run:
        try:
            token = get_token()
        except Exception as e:
            print(f"ERROR: Auth failed — {e}")
            sys.exit(1)

    archive_deal(
        token=token,
        address=args.address,
        property_name=args.property,
        metrics=metrics,
        notes=args.notes,
        files=args.files,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
