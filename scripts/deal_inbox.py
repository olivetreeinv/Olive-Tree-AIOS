#!/usr/bin/env python3
"""
Olive Tree Investments — Deal Inbox Scanner

Searches Gmail for inbound broker deal emails (last N days).
Flags emails that look like deal submissions, cross-references against
the Brokers List, and reports on buy box match.

Usage:
  python3 scripts/deal_inbox.py --days 7          # Scan last 7 days
  python3 scripts/deal_inbox.py --days 14         # Scan last 14 days
  python3 scripts/deal_inbox.py --dry-run         # Print only, no sheet reads
"""

import argparse
import base64
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

SPREADSHEET_ID = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"
SHEETS_BASE    = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_BASE     = "https://gmail.googleapis.com/gmail/v1/users/me"

BUY_BOX = {
    "30341": "Chamblee, GA",
    "30080": "Smyrna, GA",
    "30005": "Alpharetta, GA",
    "37207": "North Nashville, TN",
    "37115": "Madison, TN",
    "37408": "Chattanooga Southside, TN",
    "37087": "Lebanon, TN",
    "35801": "Huntsville Core, AL",
    "35205": "Birmingham Urban, AL",
    "35806": "Huntsville Growth, AL",
}

# Gmail search queries for deal-like emails
DEAL_QUERIES = [
    '(subject:"offering memorandum" OR subject:" OM " OR subject:"multifamily" OR subject:"apartment" OR subject:"for sale") -from:me -from:crexi.com -from:loopnet.com',
    '("rent roll" OR "T-12" OR "T12" OR "cap rate" OR "asking price" OR "NOI") -from:me -from:crexi.com -from:loopnet.com',
]

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def get_token():
    result = subprocess.run(
        ["gws", "auth", "export", "--unmasked"],
        capture_output=True, text=True, check=True
    )
    creds = json.loads(result.stdout)
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type":    "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────
# Gmail helpers
# ─────────────────────────────────────────────

def search_messages(token, query, days):
    after = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    full_query = f"{query} after:{after}"
    r = requests.get(
        f"{GMAIL_BASE}/messages",
        headers=auth_headers(token),
        params={"q": full_query, "maxResults": 50}
    )
    r.raise_for_status()
    return r.json().get("messages", [])


def get_message_meta(token, msg_id):
    r = requests.get(
        f"{GMAIL_BASE}/messages/{msg_id}",
        headers=auth_headers(token),
        params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]}
    )
    r.raise_for_status()
    return r.json()


def get_message_full(token, msg_id):
    r = requests.get(
        f"{GMAIL_BASE}/messages/{msg_id}",
        headers=auth_headers(token),
        params={"format": "full"}
    )
    r.raise_for_status()
    return r.json()


def extract_header(msg, name):
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def extract_body_preview(message, max_chars=200):
    parts = message.get("payload", {}).get("parts", [])
    text = ""

    def walk(parts_list):
        nonlocal text
        for part in parts_list:
            if text:
                return
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            elif mime == "text/html" and not text:
                data = part.get("body", {}).get("data", "")
                if data:
                    html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            elif "parts" in part:
                walk(part["parts"])

    if not parts:
        data = message.get("payload", {}).get("body", {}).get("data", "")
        if data:
            text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    else:
        walk(parts)

    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def has_attachments(message):
    parts = message.get("payload", {}).get("parts", [])

    def check(parts_list):
        for part in parts_list:
            if part.get("filename") and part.get("body", {}).get("attachmentId"):
                return True
            if "parts" in part:
                if check(part["parts"]):
                    return True
        return False

    return check(parts)


# ─────────────────────────────────────────────
# Buy box detection
# ─────────────────────────────────────────────

def detect_zip_in_text(text):
    zips = re.findall(r'\b(\d{5})\b', text)
    for z in zips:
        if z in BUY_BOX:
            return z, BUY_BOX[z]
    return None, None


def check_buy_box(subject, preview):
    combined = f"{subject} {preview}"
    zip_code, market = detect_zip_in_text(combined)
    if zip_code:
        return "IN_BOX", zip_code, market

    # Check for market name mentions
    for city in ["chamblee", "smyrna", "alpharetta", "nashville", "madison", "chattanooga",
                 "huntsville", "birmingham"]:
        if city in combined.lower():
            # Match to zip
            for z, m in BUY_BOX.items():
                if city in m.lower():
                    return "IN_BOX", z, m

    # State mentions without zip — flag as possible
    for state in ["georgia", " ga ", "tennessee", " tn ", "alabama", " al "]:
        if state.lower() in combined.lower():
            return "POSSIBLE", None, None

    return "UNKNOWN", None, None


# ─────────────────────────────────────────────
# Brokers List lookup
# ─────────────────────────────────────────────

def get_known_brokers(token):
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers%20List!B:C",
        headers=auth_headers(token)
    )
    r.raise_for_status()
    rows = r.json().get("values", [])
    known = {}
    for row in rows[1:]:
        if len(row) >= 2:
            known[row[1].lower().strip()] = row[0].strip()  # email → name
    return known


def parse_sender(from_header):
    m = re.match(r'^(.*?)\s*<(.+?)>$', from_header.strip())
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip().lower()
    return "", from_header.strip().lower()


# ─────────────────────────────────────────────
# Main scan
# ─────────────────────────────────────────────

def scan_inbox(token, days, dry_run):
    # Gather message IDs from all queries, deduplicate
    all_ids = {}
    for query in DEAL_QUERIES:
        msgs = search_messages(token, query, days)
        for m in msgs:
            all_ids[m["id"]] = True

    if not all_ids:
        print(f"📥 No deal emails found in the last {days} days.")
        return []

    # Load known broker emails
    known_brokers = {} if dry_run else get_known_brokers(token)

    results = []
    for msg_id in list(all_ids.keys())[:30]:  # cap at 30
        try:
            msg = get_message_full(token, msg_id)
        except Exception:
            continue

        from_header = extract_header(msg, "From")
        subject     = extract_header(msg, "Subject")
        date_str    = extract_header(msg, "Date")
        sender_name, sender_email = parse_sender(from_header)
        preview     = extract_body_preview(msg)
        attachments = has_attachments(msg)

        bb_status, bb_zip, bb_market = check_buy_box(subject, preview)
        known_name = known_brokers.get(sender_email, None)

        results.append({
            "id":           msg_id,
            "from_name":    sender_name or known_name or "Unknown",
            "from_email":   sender_email,
            "subject":      subject,
            "date":         date_str,
            "preview":      preview,
            "attachments":  attachments,
            "bb_status":    bb_status,
            "bb_zip":       bb_zip,
            "bb_market":    bb_market,
            "known_broker": known_name is not None,
        })

    # Sort: IN_BOX first, then POSSIBLE, then UNKNOWN
    order = {"IN_BOX": 0, "POSSIBLE": 1, "UNKNOWN": 2}
    results.sort(key=lambda x: order.get(x["bb_status"], 3))
    return results


def print_results(results):
    if not results:
        print("📥 No deal emails found.")
        return

    print(f"\n📥 Inbound Deal Emails — {len(results)} found\n")
    for i, r in enumerate(results):
        bb_icon = {"IN_BOX": "✅", "POSSIBLE": "⚠️", "UNKNOWN": "❓"}[r["bb_status"]]
        broker_label = f"[Known broker: {r['from_name']}]" if r["known_broker"] else "[New contact]"
        attach_label = "📎 Docs attached" if r["attachments"] else "No attachments"

        print(f"  {i+1}. From: {r['from_name']} <{r['from_email']}> {broker_label}")
        print(f"     Subject: {r['subject']}")
        print(f"     Date: {r['date']}")
        print(f"     Preview: {r['preview']}")
        bb_detail = f"{r['bb_zip']} ({r['bb_market']})" if r["bb_zip"] else r["bb_status"]
        print(f"     Buy box: {bb_icon} {bb_detail} | {attach_label}")
        print()

    print("  Actions:")
    print("  - To analyze a deal: python3 scripts/deal_analysis.py --analyze --property '[name]' --asking [price] --units [n] --zip [zip]")
    print("  - For full pipeline: run /lets-get-to-work\n")


# ─────────────────────────────────────────────
# Doc request
# ─────────────────────────────────────────────

def parse_property_name(subject):
    """Best-effort property name extraction from email subject."""
    cleaned = re.sub(r'^(?:re|fwd|fw):\s*', '', subject, flags=re.IGNORECASE).strip()
    # Strip common prefixes
    for prefix in ["Offering Memorandum", "OM:", "OM —", "OM -", "Multifamily —", "Multifamily -"]:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip(" —-")
    return cleaned or "your property"


def draft_doc_request(result):
    """Generate a doc-request email draft from a scan result."""
    from_name   = result["from_name"]
    from_email  = result["from_email"]
    subject_raw = result["subject"]
    market      = result["bb_market"] or "your market"

    first_name   = from_name.split()[0] if from_name and from_name != "Unknown" else "there"
    property_name = parse_property_name(subject_raw)

    subject = f"Re: {subject_raw}" if not subject_raw.lower().startswith("re:") else subject_raw
    body = (
        f"Hi {first_name},\n\n"
        f"Thanks for reaching out about {property_name}. We're interested in taking a look. "
        f"Could you send over the following when available?\n\n"
        f"- Offering memorandum\n"
        f"- T-12 (trailing 12-month P&L)\n"
        f"- Current rent roll\n\n"
        f"We're active in {market} buying 15–50 unit value-add deals and can move quickly.\n\n"
        f"-Brian"
    )
    return {
        "to_name":  from_name,
        "to_email": from_email,
        "subject":  subject,
        "body":     body,
    }


def send_doc_request(token, draft):
    import base64
    from email.header import Header
    from email.mime.text import MIMEText

    msg = MIMEText(draft["body"], "plain", "utf-8")
    msg["to"]      = draft["to_email"]
    msg["from"]    = "brian@olivetreeinv.io"
    msg["subject"] = str(Header(draft["subject"], "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    r = requests.post(
        f"{GMAIL_BASE}/messages/send",
        headers=auth_headers(token),
        json={"raw": raw}
    )
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Olive Tree — Deal Inbox Scanner")
    parser.add_argument("--days",        type=int, default=7,  help="Days to scan back (default: 7)")
    parser.add_argument("--dry-run",     action="store_true",  help="Don't read Brokers List — just scan Gmail")
    parser.add_argument("--doc-request", type=int, metavar="INDEX", help="Draft a doc-request email for result INDEX (1-based)")
    parser.add_argument("--send",        action="store_true",  help="Send the doc-request draft immediately (use with --doc-request)")
    args = parser.parse_args()

    try:
        token = get_token()
    except Exception as e:
        print(f"ERROR: Auth failed — {e}")
        print("Run: gws auth login -s gmail,sheets")
        sys.exit(1)

    if args.doc_request is not None:
        results = scan_inbox(token, args.days, args.dry_run)
        idx = args.doc_request - 1  # convert to 0-based
        if idx < 0 or idx >= len(results):
            print(f"ERROR: Index {args.doc_request} out of range (1–{len(results)})")
            sys.exit(1)
        result = results[idx]
        if result["attachments"]:
            print(f"⚠️  Deal #{args.doc_request} already has attachments — doc request may not be needed.")
        draft = draft_doc_request(result)
        print(f"\n📄 Doc Request Draft\n")
        print(f"  To:      {draft['to_name']} <{draft['to_email']}>")
        print(f"  Subject: {draft['subject']}")
        print(f"  ---")
        print(f"  {draft['body'].replace(chr(10), chr(10) + '  ')}")
        print()
        if args.send:
            send_doc_request(token, draft)
            print(f"✅ Sent to {draft['to_email']}")
        else:
            print(f"  To send: python3 scripts/deal_inbox.py --doc-request {args.doc_request} --send")
        return

    results = scan_inbox(token, args.days, args.dry_run)
    print_results(results)
    return results


if __name__ == "__main__":
    main()
