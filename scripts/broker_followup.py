#!/usr/bin/env python3
"""
Olive Tree Investments — Broker Follow-Up Script

Reads the Brokers List tab from the Deal Sourcing spreadsheet,
identifies brokers with overdue follow-ups (Next Follow-Up ≤ today,
Status ≠ Dormant), and drafts follow-up emails.

Usage:
  python3 scripts/broker_followup.py --check                        # List overdue brokers
  python3 scripts/broker_followup.py --draft                        # Show email drafts (no send)
  python3 scripts/broker_followup.py --send-all --dry-run           # Sandbox: simulate full send
  python3 scripts/broker_followup.py --send-all                     # Production: send all overdue
  python3 scripts/broker_followup.py --send-all --exclude 16,23     # Skip specific sheet rows
  python3 scripts/broker_followup.py --mark-sent [row]              # Mark one row sent manually
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests
from gws_auth import get_token

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

SPREADSHEET_ID = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"
SHEETS_BASE    = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_BASE     = "https://gmail.googleapis.com/gmail/v1/users/me"
TODAY          = date.today()
TODAY_STR      = TODAY.strftime("%m/%d/%Y")
FOLLOW_UP_INTERVAL_DAYS = 7
MAX_FOLLOW_UPS = 3

MARKETS_BY_STATE = {
    "GA": [
        {"zip": "30341", "name": "Chamblee",   "strategy": "Value-add",            "price": "$90K–$140K/unit"},
        {"zip": "30080", "name": "Smyrna",     "strategy": "Stabilized w/ upside", "price": "$110K–$160K/unit"},
        {"zip": "30005", "name": "Alpharetta", "strategy": "Long-term hold",        "price": "$140K–$200K+/unit"},
    ],
    "TN": [
        {"zip": "37207", "name": "North Nashville",       "strategy": "Value-add/Emerging",   "price": None},
        {"zip": "37115", "name": "Madison",               "strategy": "Cash flow",            "price": None},
        {"zip": "37408", "name": "Chattanooga Southside", "strategy": "Selective/Off-market", "price": None},
        {"zip": "37087", "name": "Lebanon",               "strategy": "Value-add/Emerging",   "price": None},
    ],
    "AL": [
        {"zip": "35801", "name": "Huntsville Core",            "strategy": "Quality + upside", "price": None},
        {"zip": "35205", "name": "Birmingham Urban",           "strategy": "Value-add",        "price": None},
        {"zip": "35806", "name": "Huntsville Growth Corridor", "strategy": "Growth corridor",  "price": None},
    ],
}

BUY_BOX_HEADER = (
    "Here's what fits our box:\n"
    "- 15–50 units | multifamily only\n"
    "- Purchase price: $1M–$3M\n"
    "- Value-add or stabilized with operational upside — no fully priced stabilized deals\n"
    "- 1960s–1990s vintage preferred\n"
    "- Under-market rents, deferred maintenance, or off-market pricing"
)


def extract_states(markets_str):
    import re
    return list(dict.fromkeys(re.findall(r'\b(GA|TN|AL)\b', markets_str)))


def build_market_block(markets_str):
    states = extract_states(markets_str)
    if not states:
        return BUY_BOX_HEADER
    lines = [BUY_BOX_HEADER, "", "Active markets I'm targeting:"]
    seen = set()
    for state in states:
        for m in MARKETS_BY_STATE.get(state, []):
            if m["zip"] in seen:
                continue
            seen.add(m["zip"])
            price = f" — {m['price']}" if m["price"] else ""
            lines.append(f"  {m['zip']} {m['name']}, {state} — {m['strategy']}{price}")
    return "\n".join(lines)

# Brokers List column positions (0-indexed)
# Brokerage(0), Broker Name(1), Email(2), Phone(3), Markets/Zips(4),
# Specialty(5), Tier(6), Buy Box Sent(7), # Deals Sent(8),
# Last Contact(9), Next Follow-Up(10), Status(11), Notes(12)
COL = {
    "brokerage":    0, "name": 1, "email": 2, "phone": 3,
    "markets":      4, "specialty": 5, "tier": 6, "buy_box_sent": 7,
    "deals_sent":   8, "last_contact": 9, "next_followup": 10,
    "status":       11, "notes": 12
}

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────
# Sheet helpers
# ─────────────────────────────────────────────

def get_brokers(token):
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers%20List!A:M",
        headers=auth_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json().get("values", [])
    if len(rows) < 2:
        return []
    brokers = []
    for i, row in enumerate(rows[1:], start=2):  # start=2 because row 1 is header
        while len(row) < 13:
            row.append("")
        brokers.append({"row": i, "data": row})
    return brokers


def parse_date(date_str):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def is_overdue(broker_data):
    status      = broker_data[COL["status"]].strip()
    deals_sent  = broker_data[COL["deals_sent"]].strip()
    next_fup    = broker_data[COL["next_followup"]].strip()

    if "dormant" in status.lower():
        return False
    if not next_fup:
        return True  # never followed up — overdue by default
    follow_up_date = parse_date(next_fup)
    if follow_up_date is None:
        return True
    return TODAY >= follow_up_date


# ─────────────────────────────────────────────
# Email draft
# ─────────────────────────────────────────────

def draft_followup_email(broker_data):
    name           = broker_data[COL["name"]].strip()
    email          = broker_data[COL["email"]].strip()
    markets        = broker_data[COL["markets"]].strip()
    tier           = broker_data[COL["tier"]].strip().upper() or "B"
    deals_sent_str = broker_data[COL["deals_sent"]].strip()
    try:
        attempt_num = int(deals_sent_str) + 1 if deals_sent_str else 1
    except ValueError:
        attempt_num = 1

    first_name   = name.split()[0] if name else "there"
    last_name    = name.split()[-1] if name else ""
    market_str   = markets if markets else "your markets"
    market_block = build_market_block(markets)
    signature    = "-Brian"
    sig_full     = "-Brian\nBrian Norton | Olive Tree Investments\nbrian@olivetreeinv.io | 404-643-2356"

    # ── Tier A — casual (known relationship, no formal intro) ──
    if tier == "A":
        if attempt_num == 1:
            subject = f"Multifamily in {market_str} — {last_name}"
            body = (
                f"{first_name},\n\n"
                f"Wanted to check in — we're still actively looking in {market_str}.\n\n"
                f"{market_block}\n\n"
                f"Anything coming to market or off-market that might fit?\n\n"
                f"{signature}"
            )
        elif attempt_num == 2:
            subject = f"Multifamily in {market_str} — following up"
            body = (
                f"{first_name},\n\n"
                f"Circling back — still looking in {market_str}. Same criteria:\n\n"
                f"{market_block}\n\n"
                f"Anything coming to market?\n\n"
                f"{signature}"
            )
        else:
            subject = f"Multifamily in {market_str} — checking in"
            body = (
                f"{first_name},\n\n"
                f"Any new inventory in {market_str} that fits?\n\n"
                f"{market_block}\n\n"
                f"{signature}"
            )

    # ── Tier B — standard (some relationship, brief intro) ──
    elif tier == "B":
        if attempt_num == 1:
            subject = f"Multifamily in {market_str} — {last_name}"
            body = (
                f"Hi {first_name},\n\n"
                f"I'm Brian Norton with Olive Tree Investments. We're actively buying multifamily "
                f"in {market_str}.\n\n"
                f"{market_block}\n\n"
                f"Anything coming to market or off-market that might fit?\n\n"
                f"{signature}"
            )
        elif attempt_num == 2:
            subject = f"Multifamily in {market_str} — following up"
            body = (
                f"Hi {first_name},\n\n"
                f"Circling back on my last note — still actively looking in {market_str}:\n\n"
                f"{market_block}\n\n"
                f"Any new inventory or off-market opportunities?\n\n"
                f"{signature}"
            )
        else:
            subject = f"Multifamily in {market_str} — checking in"
            body = (
                f"Hi {first_name},\n\n"
                f"Wanted to touch base again — if anything in {market_str} matches this, "
                f"I'd love to hear about it:\n\n"
                f"{market_block}\n\n"
                f"Happy to connect whenever timing works.\n\n"
                f"{signature}"
            )

    # ── Tier C — formal (cold/new contact, full intro + signature) ──
    else:
        if attempt_num == 1:
            subject = f"Multifamily in {market_str} — {last_name}"
            body = (
                f"Hi {first_name},\n\n"
                f"My name is Brian Norton — founder of Olive Tree Investments, an Atlanta-based "
                f"multifamily investment firm. We're actively acquiring value-add apartment communities "
                f"in {market_str}.\n\n"
                f"{market_block}\n\n"
                f"Would love to connect if you have anything coming to market or off-market that fits. "
                f"We move quickly with the right deal.\n\n"
                f"{sig_full}"
            )
        elif attempt_num == 2:
            subject = f"Multifamily in {market_str} — following up"
            body = (
                f"Hi {first_name},\n\n"
                f"Following up on my last note. Still actively looking for value-add multifamily "
                f"in {market_str}:\n\n"
                f"{market_block}\n\n"
                f"Any inventory coming to market or off-market opportunities?\n\n"
                f"{sig_full}"
            )
        else:
            subject = f"Multifamily in {market_str} — checking in"
            body = (
                f"Hi {first_name},\n\n"
                f"One more check-in — if anything in {market_str} matches our criteria, "
                f"we'd love to hear about it:\n\n"
                f"{market_block}\n\n"
                f"Happy to connect at your convenience.\n\n"
                f"{sig_full}"
            )

    return {
        "to_name":  name,
        "to_email": email,
        "subject":  subject,
        "body":     body,
        "attempt":  attempt_num,
        "tier":     tier,
    }


def _to_html(text):
    """Convert plain text + markdown links to HTML for Gmail rendering."""
    import html
    import re
    body = html.escape(text)
    # Convert [label](url) → <a href="url">label</a>
    body = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)',
                  r'<a href="\2">\1</a>', body)
    body = body.replace("\n", "<br>\n")
    return f"<html><body style='font-family:sans-serif;font-size:14px'>{body}</body></html>"


def send_email(token, draft):
    import base64
    from email.header import Header
    from email.mime.text import MIMEText

    msg = MIMEText(_to_html(draft["body"]), "html", "utf-8")
    msg["to"]      = draft["to_email"]  # plain email only — avoids encoding issues with accented names
    msg["from"]    = "brian@olivetreeinv.io"
    msg["subject"] = str(Header(draft["subject"], "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    r = requests.post(
        f"{GMAIL_BASE}/messages/send",
        headers=auth_headers(token),
        json={"raw": raw},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def build_after_send_data(row_num, current_sent=0):
    """Build the batchUpdate range entries for one broker after a send."""
    next_fup = (TODAY + timedelta(days=FOLLOW_UP_INTERVAL_DAYS)).strftime("%m/%d/%Y")
    new_sent = current_sent + 1
    data = [
        {"range": f"Brokers List!I{row_num}", "values": [[new_sent]]},
        {"range": f"Brokers List!J{row_num}", "values": [[TODAY_STR]]},
        {"range": f"Brokers List!K{row_num}", "values": [[next_fup]]},
    ]
    return data, new_sent, next_fup


def batch_update_sheet(token, data_entries):
    """Apply all range updates in a single Sheets batchUpdate call."""
    if not data_entries:
        return
    r = requests.post(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values:batchUpdate",
        headers=auth_headers(token),
        json={"valueInputOption": "USER_ENTERED", "data": data_entries},
        timeout=30,
    )
    r.raise_for_status()


def update_broker_after_send(token, row_num, current_sent=0):
    data, new_sent, next_fup = build_after_send_data(row_num, current_sent)
    batch_update_sheet(token, data)
    print(f"✅ Updated broker row {row_num}: sent={new_sent}, next={next_fup}")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Olive Tree — Broker Follow-Up")
    parser.add_argument("--check",      action="store_true", help="List overdue brokers")
    parser.add_argument("--draft",      action="store_true", help="Generate email drafts for overdue brokers")
    parser.add_argument("--send",       type=int, metavar="INDEX", help="Send draft at given index (0-based)")
    parser.add_argument("--send-all",   action="store_true", help="Send all overdue brokers with valid emails")
    parser.add_argument("--dry-run",    action="store_true", help="Sandbox: show what would be sent without sending or updating sheet")
    parser.add_argument("--exclude",    type=str, metavar="ROWS", help="Comma-separated sheet row numbers to skip (e.g. 16,23)")
    parser.add_argument("--mark-sent",  type=int, metavar="ROW",   help="Mark sheet row as sent (sheet row number)")
    args = parser.parse_args()

    if not any([args.check, args.draft, args.send is not None, args.send_all, args.mark_sent is not None]):
        parser.print_help()
        sys.exit(0)

    try:
        token = get_token()
    except Exception as e:
        print(f"ERROR: Auth failed — {e}")
        print("Run: gws auth login -s gmail,sheets")
        sys.exit(1)

    # --mark-sent updates a single row — no need to fetch/filter the whole sheet
    if args.mark_sent is not None:
        update_broker_after_send(token, args.mark_sent)
        return

    brokers = get_brokers(token)
    overdue = [b for b in brokers if is_overdue(b["data"])]

    if args.check:
        print(f"\n📬 Overdue Follow-Ups — {len(overdue)} broker(s)\n")
        for b in overdue:
            d = b["data"]
            name     = d[COL["name"]]
            brokerage = d[COL["brokerage"]]
            markets  = d[COL["markets"]]
            last     = d[COL["last_contact"]] or "never"
            sent     = d[COL["deals_sent"]] or "0"
            print(f"  Row {b['row']}: {name} ({brokerage}) | {markets} | Last: {last} | Sent: {sent}")
        print()
        return

    if args.draft or args.send is not None or args.send_all:
        drafts = [draft_followup_email(b["data"]) for b in overdue]
        if not drafts:
            print("✅ No overdue follow-ups.")
            return

        if args.draft:
            print(f"\n📬 Follow-Up Drafts — {len(drafts)} broker(s)\n")
            for i, (d, b) in enumerate(zip(drafts, overdue)):
                print(f"  [{i}] To: {d['to_name']} <{d['to_email']}> | Tier {d['tier']} | Attempt {d['attempt']}")
                print(f"      Subject: {d['subject']}")
                print(f"      ---")
                print(f"      {d['body'].replace(chr(10), chr(10) + '      ')}")
                print()
            print(f"  To send: python3 scripts/broker_followup.py --send [INDEX]")
            return

        if args.send is not None:
            if args.send >= len(drafts):
                print(f"ERROR: Index {args.send} out of range (0–{len(drafts)-1})")
                sys.exit(1)
            draft = drafts[args.send]
            if not draft["to_email"]:
                print(f"⚠️  Skipped {draft['to_name']} — no email address on file.")
                return
            broker_row = overdue[args.send]["row"]
            current_sent_val = overdue[args.send]["data"][COL["deals_sent"]]
            try:
                current_sent_int = int(current_sent_val) if current_sent_val else 0
            except (ValueError, TypeError):
                current_sent_int = 0
            print(f"Sending to {draft['to_name']} <{draft['to_email']}>...")
            send_email(token, draft)
            update_broker_after_send(token, broker_row, current_sent_int)
            print(f"✅ Sent: {draft['subject']}")
            return

        if args.send_all:
            dry_run = args.dry_run
            exclude_rows = set()
            if args.exclude:
                for r in args.exclude.split(","):
                    try:
                        exclude_rows.add(int(r.strip()))
                    except ValueError:
                        pass

            if dry_run:
                print(f"\n🧪 DRY RUN — no emails will be sent, sheet will not be updated\n")

            # Build the work list upfront from the already-fetched overdue list (stable, no re-fetch)
            jobs = []
            skipped = 0
            for d, b in zip(drafts, overdue):
                row = b["row"]
                if row in exclude_rows:
                    print(f"⏭️  Excluded (row {row}): {d['to_name']}")
                    skipped += 1
                    continue
                if not d["to_email"]:
                    print(f"⚠️  Skipped {d['to_name'] or 'unknown'} — no email address on file.")
                    skipped += 1
                    continue
                b_sent_val = b["data"][COL["deals_sent"]]
                try:
                    b_sent_int = int(b_sent_val) if b_sent_val else 0
                except (ValueError, TypeError):
                    b_sent_int = 0
                jobs.append((d, row, b_sent_int))

            if dry_run:
                print(f"📬 Would send to {len(jobs)} broker(s):\n")
                for d, row, _ in jobs:
                    print(f"  ✉️  Row {row}: {d['to_name']} <{d['to_email']}>")
                    print(f"      Subject: {d['subject']}")
                    print(f"      ---")
                    print(f"      {d['body'].replace(chr(10), chr(10) + '      ')}")
                    print()
                print(f"✅ Dry run complete — {len(jobs)} would send, {skipped} would skip.")
                print(f"\nTo send for real: python3 scripts/broker_followup.py --send-all" +
                      (f" --exclude {args.exclude}" if args.exclude else ""))
                return

            # Production send — emails in parallel; collect successes for one batched sheet update
            def _send(job):
                d, row, sent_int = job
                try:
                    send_email(token, d)
                    return (True, d, row, sent_int, None)
                except Exception as e:
                    return (False, d, row, sent_int, e)

            sent = 0
            update_data = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                for ok, d, row, sent_int, err in executor.map(_send, jobs):
                    if ok:
                        data, _, _ = build_after_send_data(row, sent_int)
                        update_data.extend(data)
                        sent += 1
                        print(f"✅ Sent: {d['to_name']} — {d['subject']}")
                    else:
                        skipped += 1
                        print(f"❌ Failed: {d['to_name']} <{d['to_email']}> — {err}")

            # One Sheets batchUpdate for every successfully sent broker
            batch_update_sheet(token, update_data)
            print(f"\n📬 Done — {sent} sent, {skipped} skipped/failed.")
            return


if __name__ == "__main__":
    main()
