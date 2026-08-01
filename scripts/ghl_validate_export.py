#!/usr/bin/env python3
"""
Validate the GHL archive export and report counts.
Run after ghl_archive_export.py completes.
"""
import json
from pathlib import Path
from collections import defaultdict

def main():
    archive_dir = Path(__file__).parent.parent / "archives" / "ghl-export-deep-2026-07-07"
    conv_dir = archive_dir / "conversations"

    if not conv_dir.exists():
        print("ERROR: No conversations directory found")
        return

    # Count conversations and messages
    conv_count = 0
    total_messages = 0
    message_type_counts = defaultdict(int)
    email_count = 0
    newsletter_subjects_seen = set()

    conv_files = sorted(conv_dir.glob("*.json"))
    print(f"Validating {len(conv_files)} conversation files...\n")

    for conv_file in conv_files:
        with open(conv_file) as f:
            data = json.load(f)
            messages = data.get("messages", [])
            conv_count += 1
            total_messages += len(messages)

            for msg in messages:
                msg_type = msg.get("type", "unknown")
                msg_type_str = str(msg_type)
                message_type_counts[msg_type_str] += 1

                # Detect email messages
                is_email = (
                    "EMAIL" in str(msg_type).upper() or
                    msg_type == 3 or
                    msg_type == "3"
                )
                if is_email:
                    email_count += 1
                    # Check for subject
                    subject = msg.get("meta", {}).get("email", {}).get("subject")
                    if not subject:
                        subject = msg.get("subject")
                    if subject:
                        newsletter_subjects_seen.add(subject)

    # Load newsletter audience if it exists
    audience_file = archive_dir / "newsletter_audience.json"
    newsletter_recipients_total = 0
    campaigns_found = 0

    if audience_file.exists():
        with open(audience_file) as f:
            audience = json.load(f)
            campaigns_found = len(audience.get("campaigns", {}))
            newsletter_recipients_total = len(audience.get("all_recipient_contactIds", []))

    # Load summary if it exists
    summary_file = archive_dir / "conversations_summary.md"
    summary_exists = summary_file.exists()

    # Report
    print("="*60)
    print("VALIDATION REPORT")
    print("="*60)
    print(f"\nConversations archived: {conv_count}")
    print(f"Total messages: {total_messages}")
    print(f"Email messages: {email_count}")
    print(f"Unique newsletter subjects seen in messages: {len(newsletter_subjects_seen)}")
    print(f"\nMessage type breakdown:")
    for msg_type in sorted(message_type_counts.keys()):
        count = message_type_counts[msg_type]
        print(f"  Type {msg_type}: {count}")

    print(f"\nNewsletter extraction:")
    print(f"  Campaigns processed: {campaigns_found}")
    print(f"  Total unique recipients: {newsletter_recipients_total}")
    print(f"  Summary file exists: {summary_exists}")

    print(f"\nOutput location: {archive_dir}")
    print(f"\nFiles:")
    for f in sorted(archive_dir.glob("*")):
        if f.is_file():
            size = f.stat().st_size / 1024
            print(f"  {f.name} ({size:.1f} KB)")
        else:
            file_count = len(list(f.glob("*.json")))
            if file_count > 0:
                print(f"  {f.name}/ ({file_count} files)")

if __name__ == "__main__":
    main()
