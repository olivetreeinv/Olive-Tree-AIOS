#!/usr/bin/env python3
"""
Generate final report from GHL archive export.
Run after ghl_archive_export.py completes.
"""
import json
from pathlib import Path
from collections import Counter

archive_dir = Path(__file__).parent.parent / "archives" / "ghl-export-deep-2026-07-07"

print("\n" + "="*70)
print("GOHIGHLEVEL ARCHIVE EXPORT — FINAL REPORT")
print("="*70 + "\n")

# Load audience
audience_file = archive_dir / "newsletter_audience.json"
if not audience_file.exists():
    print("ERROR: Newsletter audience file not found. Export may still be in progress.")
    exit(1)

with open(audience_file) as f:
    audience_data = json.load(f)

campaigns = audience_data.get("campaigns", {})
all_recipients = audience_data.get("all_recipient_contactIds", [])

# Load summary
summary_file = archive_dir / "conversations_summary.md"
summary_text = ""
if summary_file.exists():
    with open(summary_file) as f:
        summary_text = f.read()

# Count conversation files
conv_dir = archive_dir / "conversations"
conv_files = list(conv_dir.glob("*.json"))
conv_count = len(conv_files)

# Parse summary for stats
total_messages = 0
message_types = {}
failed_convs = []

if summary_text:
    # Extract key numbers from markdown
    for line in summary_text.split('\n'):
        if 'Total Conversations:' in line:
            # Extract number
            parts = line.split(':')
            if len(parts) > 1:
                try:
                    total_messages = int(parts[1].split()[0]) if 'Messages' in line else total_messages
                except:
                    pass
        if 'Total Messages:' in line:
            try:
                total_messages = int(line.split(':')[1].strip())
            except:
                pass

# Scan conversation files for message count and types
print("Archive Statistics:")
print("-" * 70)
print(f"Conversations archived: {conv_count}")

total_msgs = 0
type_counts = Counter()

for conv_file in conv_files[:20]:  # Sample first 20 for speed
    with open(conv_file) as f:
        data = json.load(f)
        msgs = data.get("messages", [])
        total_msgs += len(msgs)
        for msg in msgs:
            msg_type = str(msg.get("type", "unknown"))
            type_counts[msg_type] += 1

print(f"Sample messages (first 20 convs): {total_msgs}")
if type_counts:
    print(f"Message type breakdown (sample):")
    for msg_type in sorted(type_counts.keys()):
        print(f"  Type {msg_type}: {type_counts[msg_type]}")

print(f"\nNewsletter Campaigns & Audience:")
print("-" * 70)
print(f"Total campaigns: {len(campaigns)}\n")

for campaign_name in sorted(campaigns.keys()):
    info = campaigns[campaign_name]
    subject = info.get("subject", "N/A")
    count = len(info.get("contactIds", []))
    print(f"{campaign_name}")
    print(f"  Subject: {subject}")
    print(f"  Recipients: {count}\n")

print("="*70)
print(f"TOTAL UNIQUE NEWSLETTER RECIPIENTS: {len(all_recipients)}")
print("="*70)
print(f"\nMethod: Subject line matching")
print(f"Audience extraction from message.meta.email.subject and message.subject")
print(f"Matched against newsletter campaign subjects from /emails/schedule API")

print(f"\nOutput files:")
print(f"  - {archive_dir}/conversations/ ({conv_count} JSON files)")
print(f"  - {archive_dir}/newsletter_audience.json")
print(f"  - {archive_dir}/conversations_summary.md")

print()
