#!/usr/bin/env python3
"""
Extract and display newsletter audience summary from the archive.
Run after ghl_archive_export.py completes.
"""
import json
from pathlib import Path

archive_dir = Path(__file__).parent.parent / "archives" / "ghl-export-deep-2026-07-07"
audience_file = archive_dir / "newsletter_audience.json"

if not audience_file.exists():
    print("Newsletter audience file not found. Archive may still be processing.")
    exit(1)

with open(audience_file) as f:
    data = json.load(f)

campaigns = data.get("campaigns", {})
all_recipients = data.get("all_recipient_contactIds", [])

print("="*70)
print("NEWSLETTER AUDIENCE EXTRACTION")
print("="*70)
print(f"\nTotal unique recipients: {len(all_recipients)}\n")

print("Audience by campaign:")
print("-" * 70)

for campaign_name in sorted(campaigns.keys()):
    info = campaigns[campaign_name]
    subject = info.get("subject", "N/A")
    count = len(info.get("contactIds", []))
    print(f"\n{campaign_name}")
    print(f"  Subject: {subject}")
    print(f"  Recipients: {count}")

    # Show first few recipient IDs
    ids = info.get("contactIds", [])[:3]
    if ids:
        print(f"  Sample IDs: {', '.join(ids)}")

print(f"\n{'='*70}")
print(f"All unique recipient IDs (comma-separated):")
print(f"{'='*70}")
print(",".join(all_recipients))
print()
