#!/usr/bin/env python3
"""
Archive all GoHighLevel conversations and extract newsletter audience.
Outputs to archives/ghl-export-deep-2026-07-07/
"""
import json
import subprocess
import time
import os
from pathlib import Path
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv(Path(__file__).parent.parent / ".env")

GHL_KEY = os.getenv("GHL_API_KEY")
GHL_LOC = os.getenv("GHL_LOCATION_ID")
BASE_URL = "https://services.leadconnectorhq.com"

def ghl_get(path, version="2021-04-15", params=None):
    """
    Call GHL API via curl with headers on stdin.
    Returns parsed JSON or None on error.
    """
    url = BASE_URL + path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"

    cfg = f'header = "Authorization: Bearer {GHL_KEY}"\nheader = "Version: {version}"\nheader = "Accept: application/json"\n'
    try:
        r = subprocess.run(
            ["curl", "-s", "-K", "-", url],
            input=cfg,
            capture_output=True,
            text=True,
            timeout=60
        )
        if r.returncode != 0:
            print(f"  curl error {r.returncode}: {r.stderr}")
            return None
        return json.loads(r.stdout, strict=False) if r.stdout else None
    except Exception as e:
        print(f"  Exception: {e}")
        return None

def fetch_all_conversations():
    """
    Paginate through all conversations using cursor-based pagination (startAfterDate).
    Yields (id, conversation_record).
    """
    print("[1] Fetching all conversations...")
    limit = 100
    total_fetched = 0
    start_after_date = None

    while True:
        params = {"locationId": GHL_LOC, "limit": limit}
        if start_after_date is not None:
            params["startAfterDate"] = start_after_date

        resp = ghl_get("/conversations/search", params=params)
        if not resp:
            print(f"  Failed to fetch (startAfterDate={start_after_date})")
            break

        conversations = resp.get("conversations", [])
        if not conversations:
            print(f"  No more conversations")
            break

        batch_count = len(conversations)
        print(f"  Batch: {batch_count} conversations (startAfterDate={start_after_date})")

        for conv in conversations:
            total_fetched += 1
            yield conv["id"], conv

        # Check pagination: if we got fewer than limit, we're done
        if batch_count < limit:
            print(f"  Reached end: {batch_count} < {limit}")
            break

        # Set cursor to last conversation's lastMessageDate for next iteration
        last_conv = conversations[-1]
        start_after_date = last_conv.get("lastMessageDate")
        if not start_after_date:
            print(f"  WARNING: No lastMessageDate on last conversation")
            break

        time.sleep(0.1)

    print(f"  Total conversations: {total_fetched}")

def fetch_conversation_messages(conv_id):
    """
    Fetch all messages for a conversation. Inspect response shape.
    Returns list of message records or empty list on error.
    """
    limit = 100
    offset = 0
    all_messages = []

    while True:
        params = {"limit": limit, "offset": offset}
        resp = ghl_get(f"/conversations/{conv_id}/messages", params=params)
        if not resp:
            print(f"    Failed to fetch messages at offset {offset}")
            break

        # Inspect response shape: messages may be under .messages or .messages.messages
        messages = resp.get("messages", [])
        if isinstance(messages, dict) and "messages" in messages:
            messages = messages["messages"]

        if not messages:
            break

        all_messages.extend(messages)

        if len(messages) < limit:
            break

        offset += limit
        time.sleep(0.1)

    return all_messages

def fetch_newsletter_campaigns():
    """
    Fetch newsletter schedules. Returns dict: {name: {"subject": ..., "createdAt": ...}}.
    """
    print("[3] Fetching newsletter campaigns...")
    campaigns = {}
    limit = 100
    offset = 0

    while True:
        params = {
            "locationId": GHL_LOC,
            "limit": limit,
            "offset": offset,
            "archived": "false",
            "status": "complete"
        }
        resp = ghl_get("/emails/schedule", version="2021-07-28", params=params)
        if not resp:
            print(f"  Failed to fetch at offset {offset}")
            break

        schedules = resp.get("schedules", [])
        if not schedules:
            print(f"  No more schedules at offset {offset}")
            break

        for schedule in schedules:
            name = schedule.get("name", "")
            if "newsletter" in name.lower():
                campaigns[name] = {
                    "subject": schedule.get("subject", ""),
                    "createdAt": schedule.get("createdAt", ""),
                    "updatedAt": schedule.get("updatedAt", "")
                }

        if len(schedules) < limit:
            break

        offset += limit
        time.sleep(0.1)

    print(f"  Found {len(campaigns)} newsletter campaigns")
    for name in campaigns:
        print(f"    - {name}: '{campaigns[name]['subject']}'")

    return campaigns

def extract_newsletter_audience(all_messages, campaigns):
    """
    Scan messages for email-type messages matching newsletter subjects.
    Returns dict with campaign->contactIds mapping.
    """
    print("[4] Extracting newsletter audience...")
    campaign_recipients = defaultdict(set)
    email_message_count = 0

    # Build a map of subjects to campaign names
    subject_to_campaign = {}
    for campaign_name, info in campaigns.items():
        subject = info.get("subject", "")
        if subject:
            subject_to_campaign[subject] = campaign_name

    # Scan all messages
    for msg in all_messages:
        msg_type = msg.get("type", "")

        # Check if this is an email message (type field may contain EMAIL or be numeric)
        is_email = (
            "EMAIL" in str(msg_type).upper() or
            msg_type == 3 or
            msg_type == "3"
        )

        if not is_email:
            continue

        email_message_count += 1

        # Try to extract subject from various locations
        subject = None
        if "meta" in msg and "email" in msg["meta"]:
            subject = msg["meta"]["email"].get("subject")
        if not subject and "subject" in msg:
            subject = msg.get("subject")

        if subject and subject in subject_to_campaign:
            campaign_name = subject_to_campaign[subject]
            contact_id = msg.get("contactId")
            if contact_id:
                campaign_recipients[campaign_name].add(contact_id)

    print(f"  Scanned {email_message_count} email messages")

    # Convert sets to sorted lists
    result = {}
    for campaign, ids in campaign_recipients.items():
        result[campaign] = {
            "subject": campaigns[campaign]["subject"],
            "contactIds": sorted(list(ids))
        }

    return result

def main():
    # Create output directory
    output_dir = Path(__file__).parent.parent / "archives" / "ghl-export-deep-2026-07-07"
    conv_dir = output_dir / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output: {output_dir}\n")

    # === Step 1: Fetch and archive conversations ===
    all_conversations = {}
    message_type_counts = defaultdict(int)
    total_messages = 0
    failed_convs = []

    for conv_id, conv_data in fetch_all_conversations():
        # Fetch messages for this conversation
        messages = fetch_conversation_messages(conv_id)

        # Count message types
        for msg in messages:
            msg_type = msg.get("type", "unknown")
            message_type_counts[str(msg_type)] += 1
            total_messages += 1

        # Save to file
        output = {
            "conversation": conv_data,
            "messages": messages
        }

        try:
            output_file = conv_dir / f"{conv_id}.json"
            with open(output_file, "w") as f:
                json.dump(output, f, indent=2)
            all_conversations[conv_id] = len(messages)
        except Exception as e:
            print(f"  Failed to write {conv_id}: {e}")
            failed_convs.append(conv_id)

        time.sleep(0.1)

    print(f"  Saved {len(all_conversations)} conversation files\n")

    # === Step 2: Fetch newsletter campaigns ===
    campaigns = fetch_newsletter_campaigns()

    # === Step 3: Extract newsletter audience ===
    # Collect all messages from all conversations
    all_messages = []
    for conv_id in all_conversations:
        conv_file = conv_dir / f"{conv_id}.json"
        with open(conv_file) as f:
            data = json.load(f)
            all_messages.extend(data.get("messages", []))

    print(f"  Total messages across all conversations: {len(all_messages)}\n")

    campaign_audience = extract_newsletter_audience(all_messages, campaigns)

    # === Step 4: Build audience file ===
    all_recipient_ids = set()
    for campaign_info in campaign_audience.values():
        all_recipient_ids.update(campaign_info["contactIds"])

    audience_output = {
        "campaigns": campaign_audience,
        "all_recipient_contactIds": sorted(list(all_recipient_ids))
    }

    audience_file = output_dir / "newsletter_audience.json"
    with open(audience_file, "w") as f:
        json.dump(audience_output, f, indent=2)

    print(f"  Saved: {audience_file}")
    print(f"  Unique newsletter recipients: {len(all_recipient_ids)}\n")

    # === Step 5: Write summary ===
    summary_file = output_dir / "conversations_summary.md"
    with open(summary_file, "w") as f:
        f.write("# GoHighLevel Conversations Archive Summary\n\n")
        f.write(f"**Export Date:** 2026-07-07\n")
        f.write(f"**Archive Location:** archives/ghl-export-deep-2026-07-07/\n\n")

        f.write("## Conversation Archival\n")
        f.write(f"- **Total Conversations:** {len(all_conversations)}\n")
        f.write(f"- **Total Messages:** {total_messages}\n")
        f.write(f"- **Failed Fetches:** {len(failed_convs)}\n")
        if failed_convs:
            f.write(f"  - {', '.join(failed_convs)}\n")

        f.write("\n## Message Type Breakdown\n")
        for msg_type in sorted(message_type_counts.keys()):
            count = message_type_counts[msg_type]
            f.write(f"- Type `{msg_type}`: {count} messages\n")

        f.write(f"\n## Newsletter Campaigns & Audience\n")
        f.write(f"- **Total Campaigns:** {len(campaigns)}\n")
        for campaign_name, info in campaign_audience.items():
            f.write(f"\n### {campaign_name}\n")
            f.write(f"- **Subject:** {info['subject']}\n")
            f.write(f"- **Recipients:** {len(info['contactIds'])}\n")

        f.write(f"\n## Audience Extraction\n")
        f.write(f"- **Total Unique Recipients:** {len(all_recipient_ids)}\n")
        f.write(f"- **Method:** Subject line matching (message.meta.email.subject or message.subject vs. campaign schedule subjects)\n")
        f.write(f"- **Files Generated:**\n")
        f.write(f"  - `conversations/` — one JSON per conversation (id + messages)\n")
        f.write(f"  - `newsletter_audience.json` — campaign->recipients mapping + unique IDs\n")
        f.write(f"  - `conversations_summary.md` — this file\n")

    print(f"  Saved: {summary_file}\n")

    # === Final Report ===
    print("\n" + "="*60)
    print("ARCHIVE COMPLETE")
    print("="*60)
    print(f"\nConversations archived: {len(all_conversations)}")
    print(f"Total messages: {total_messages}")
    print(f"Newsletter campaigns: {len(campaigns)}")
    print(f"Unique newsletter recipients: {len(all_recipient_ids)}\n")

    print("Campaign audience breakdown:")
    for campaign_name, info in campaign_audience.items():
        print(f"  {campaign_name}: {len(info['contactIds'])} recipients")

    if failed_convs:
        print(f"\nFailed conversations: {len(failed_convs)}")
        for conv_id in failed_convs:
            print(f"  - {conv_id}")

    print(f"\nMethod used: Subject line matching from message.meta.email.subject or message.subject")
    print(f"\nOutput files: {output_dir}/")

if __name__ == "__main__":
    main()
