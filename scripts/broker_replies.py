#!/usr/bin/env python3
"""
Olive Tree Investments — Broker Reply Monitor

Watches Gmail for inbound email from anyone in the Brokers List, classifies
each message, and recommends (or applies) the follow-through:

  DEAL     — looks like a listing/deal submission → run the deal pipeline
             (/deal-analysis or /lets-get-to-work); buy-box zip flagged when found
  CONTACT  — signature contains a phone we don't have → update the sheet
  REPLY    — a real response that needs Brian to read/answer

Usage:
  python3 scripts/broker_replies.py                # report last 7 days
  python3 scripts/broker_replies.py --days 14
  python3 scripts/broker_replies.py --apply        # also write contact updates +
                                                   # Last Contact + Status to the sheet
"""

import argparse
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from gws_auth import get_token
from deal_inbox import (
    SHEETS_BASE, SPREADSHEET_ID, auth_headers, check_buy_box, extract_full_body,
    extract_header, extract_signature_info, get_message_full, has_attachments,
    parse_email_date, search_messages,
)

DEAL_KEYWORDS = [
    "offering memorandum", " om ", "rent roll", "t-12", "t12", "cap rate",
    "asking price", "under contract", "for sale", "listing", "units", "doors",
    "portfolio", "noi", "pro forma", "proforma",
]
QUERY_CHUNK = 25  # emails per Gmail from:(...) query


def strip_quoted(body):
    """Drop quoted reply text so my own outbound email doesn't trigger the classifiers."""
    body = re.split(r"On .{5,150}? wrote:", body, flags=re.S)[0]
    body = re.split(r"-{3,}\s*Original Message\s*-{3,}", body, flags=re.I)[0]
    body = re.split(r"From:\s*Brian Norton|From:.{0,80}brian@olivetreeinv", body, flags=re.I)[0]
    return "\n".join(l for l in body.splitlines() if not l.lstrip().startswith(">"))


def _digits(phone):
    return re.sub(r"\D", "", phone)


def detect_email_change(body, current_email):
    """Catch 'my email address has changed ... to new@domain' auto-replies."""
    if not re.search(r"email (address )?(has )?changed", body, re.I):
        return ""
    clean = re.sub(r"<mailto:[^>]+>", "", body)  # Outlook artifacts carry unrelated addresses
    m = re.search(r"\bto[:\s]+([\w.+-]+@[\w-]+\.[\w.]{2,})", clean, re.I)
    if m:
        new = m.group(1).rstrip(".")
        if new.lower() != current_email.lower():
            return new
    return ""


def get_broker_rows(token):
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers%20List!A1:Z2000",
        headers=auth_headers(token), timeout=30,
    )
    r.raise_for_status()
    rows = r.json().get("values", [])
    brokers = {}
    for i, row in enumerate(rows[1:], start=2):
        email = row[2].strip().lower() if len(row) > 2 else ""
        if email:
            brokers[email] = {
                "row": i,
                "brokerage": row[0].strip() if len(row) > 0 else "",
                "name": row[1].strip() if len(row) > 1 else "",
                "phone": row[3].strip() if len(row) > 3 else "",
            }
    return brokers


AUTO_REPLY_MARKERS = ("automatic reply", "auto-reply", "auto reply",
                      "out of office", "out-of-office", "away from my", "autoresponder")


def is_auto_reply(subject, body):
    s = subject.lower()
    return (s.startswith(("automatic reply", "auto:", "out of office"))
            or any(m in s for m in AUTO_REPLY_MARKERS)
            or "out of office" in body[:200].lower())


def classify(subject, body, message):
    text = f"{subject} {body}".lower()
    verdict, zip_code, market = check_buy_box(subject, body[:2000])
    deal_hits = sum(1 for k in DEAL_KEYWORDS if k in text)
    auto = is_auto_reply(subject, body)
    # an auto-reply is never a real deal email, even if it echoes deal keywords
    is_deal = not auto and (deal_hits >= 2 or has_attachments(message) or verdict == "IN_BOX")
    return is_deal, verdict, zip_code, market, auto


def scan(token, days):
    brokers = get_broker_rows(token)
    emails = list(brokers)
    findings, seen_msgs = [], set()
    for i in range(0, len(emails), QUERY_CHUNK):
        chunk = emails[i:i + QUERY_CHUNK]
        query = f"from:({' OR '.join(chunk)})"
        for m in search_messages(token, query, days):
            if m["id"] in seen_msgs:
                continue
            seen_msgs.add(m["id"])
            msg = get_message_full(token, m["id"])
            sender = extract_header(msg, "From").lower()
            broker = next((b for e, b in brokers.items() if e in sender), None)
            if not broker:
                continue
            subject = extract_header(msg, "Subject")
            body = strip_quoted(extract_full_body(msg))
            sig_phone, _ = extract_signature_info(body)
            sender_email = next(e for e in brokers if e in sender)
            is_deal, verdict, zip_code, market, auto = classify(subject, body, msg)
            findings.append({
                "broker": broker,
                "date": parse_email_date(extract_header(msg, "Date")),
                "subject": subject,
                "preview": " ".join(body.split())[:180],
                "is_deal": is_deal,
                "auto_reply": auto,
                "buy_box": (verdict, zip_code, market),
                "new_phone": sig_phone if sig_phone and _digits(sig_phone) != _digits(broker["phone"]) else "",
                "new_email": detect_email_change(body, sender_email),
            })
    return findings


def report(findings):
    if not findings:
        print("No inbound broker email in the window.")
        return
    deals = [f for f in findings if f["is_deal"]]
    contacts = [f for f in findings if f["new_phone"] or f["new_email"]]
    replies = [f for f in findings if not f["is_deal"] and not f["auto_reply"] and f not in contacts]

    if deals:
        print(f"📦 DEAL EMAILS ({len(deals)}) — run /deal-analysis or /lets-get-to-work:")
        for f in deals:
            verdict, zip_code, market = f["buy_box"]
            tag = f"BUY BOX: {market} ({zip_code})" if verdict == "IN_BOX" else (
                  "possible buy-box state" if verdict == "POSSIBLE" else "market unknown")
            print(f"  • {f['date']} {f['broker']['name']} ({f['broker']['brokerage']}) — "
                  f"\"{f['subject']}\" [{tag}]")
            print(f"      {f['preview']}")
    if contacts:
        print(f"\n📞 CONTACT UPDATES ({len(contacts)}):")
        for f in contacts:
            b = f["broker"]
            if f["new_phone"]:
                print(f"  • {b['name']} (row {b['row']}): phone {f['new_phone']}"
                      f"{'  (sheet: ' + b['phone'] + ')' if b['phone'] else '  (sheet blank)'}")
            if f["new_email"]:
                print(f"  • {b['name']} (row {b['row']}): EMAIL CHANGED → {f['new_email']}")
    if replies:
        print(f"\n💬 REPLIES TO READ ({len(replies)}):")
        for f in replies:
            print(f"  • {f['date']} {f['broker']['name']} — \"{f['subject']}\"")
            print(f"      {f['preview']}")


def apply_updates(token, findings):
    data = []
    for f in findings:
        row = f["broker"]["row"]
        # contact-data updates apply even from an auto-reply (a bounce/OOO often
        # carries the new email or a direct line)
        if f["new_phone"] and not f["broker"]["phone"]:
            data.append({"range": f"Brokers List!D{row}", "values": [[f["new_phone"]]]})
        if f["new_email"]:
            data.append({"range": f"Brokers List!C{row}", "values": [[f["new_email"]]]})
        # but only a GENUINE reply marks the broker engaged / bumps last contact
        if not f["auto_reply"]:
            data.append({"range": f"Brokers List!J{row}", "values": [[f["date"]]]})   # Last Contact
            data.append({"range": f"Brokers List!L{row}", "values": [["Responded — engaged"]]})
    if not data:
        return 0
    r = requests.post(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values:batchUpdate",
        headers=auth_headers(token),
        json={"valueInputOption": "USER_ENTERED", "data": data},
        timeout=30,
    )
    r.raise_for_status()
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--apply", action="store_true",
                    help="write Last Contact/Status + blank-phone fills to the sheet")
    args = ap.parse_args()

    token = get_token()
    findings = scan(token, args.days)
    report(findings)
    if args.apply and findings:
        n = apply_updates(token, findings)
        print(f"\n✅ sheet updated ({n} cell range(s)).")


if __name__ == "__main__":
    main()
