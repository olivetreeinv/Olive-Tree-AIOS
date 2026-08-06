#!/usr/bin/env python3
"""Quick stats from completed archive."""
import json
from pathlib import Path

archive = Path(__file__).parent.parent / "archives" / "ghl-export-deep-2026-07-07"

# Count conversation files
convs = len(list((archive / "conversations").glob("*.json")))

# Load audience file if it exists
audience_file = archive / "newsletter_audience.json"
recipients = 0
campaigns = 0

if audience_file.exists():
    with open(audience_file) as f:
        data = json.load(f)
        recipients = len(data.get("all_recipient_contactIds", []))
        campaigns = len(data.get("campaigns", {}))

print(f"Conversations: {convs}")
print(f"Campaigns: {campaigns}")
print(f"Recipients: {recipients}")
