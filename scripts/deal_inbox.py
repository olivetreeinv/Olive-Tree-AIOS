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
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from gws_auth import get_token

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

SPREADSHEET_ID = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"
SHEETS_BASE    = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_BASE     = "https://gmail.googleapis.com/gmail/v1/users/me"

# keep in sync with references/buy-box.md
BUY_BOX = {
    "30341": "Chamblee, GA",
    "30340": "Doraville, GA",
    "30360": "Doraville, GA",
    "30080": "Smyrna, GA",
    "30005": "Alpharetta, GA",
    "37207": "North Nashville, TN",
    "37115": "Madison, TN",
    "37408": "Chattanooga Southside, TN",
    "37087": "Lebanon, TN",
    "37918": "Knoxville, TN",
    "37804": "Maryville, TN",
    "37615": "Johnson City, TN",
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

def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────
# Gmail helpers
# ─────────────────────────────────────────────

def search_messages(token, query, days):
    after = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    full_query = f"{query} after:{after}"
    messages, page_token = [], None
    while True:  # paginate — an active inbox can exceed one page and silently drop deals
        params = {"q": full_query, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(
            f"{GMAIL_BASE}/messages",
            headers=auth_headers(token),
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        messages.extend(data.get("messages", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return messages


def get_message_full(token, msg_id):
    r = requests.get(
        f"{GMAIL_BASE}/messages/{msg_id}",
        headers=auth_headers(token),
        params={"format": "full"},
        timeout=30,
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
        headers=auth_headers(token),
        timeout=30,
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
    # Run all search queries in parallel, then deduplicate message IDs
    all_ids = {}
    with ThreadPoolExecutor(max_workers=len(DEAL_QUERIES)) as executor:
        for msgs in executor.map(lambda q: search_messages(token, q, days), DEAL_QUERIES):
            for m in msgs:
                all_ids[m["id"]] = True

    if not all_ids:
        print(f"📥 No deal emails found in the last {days} days.")
        return []

    # Load known broker emails (sheet read can overlap with message fetches)
    known_brokers = {} if dry_run else get_known_brokers(token)

    # Fetch the (capped) full messages in parallel
    msg_ids = list(all_ids.keys())[:30]

    def _fetch(msg_id):
        try:
            return msg_id, get_message_full(token, msg_id)
        except Exception:
            return msg_id, None

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for msg_id, msg in executor.map(_fetch, msg_ids):
            if msg is None:
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


def _to_html(text):
    """Convert plain text + markdown links to HTML for Gmail rendering."""
    import html
    import re
    body = html.escape(text)
    body = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)',
                  r'<a href="\2">\1</a>', body)
    body = body.replace("\n", "<br>\n")
    return f"<html><body style='font-family:sans-serif;font-size:14px'>{body}</body></html>"


def send_doc_request(token, draft):
    import base64
    from email.header import Header
    from email.mime.text import MIMEText

    msg = MIMEText(_to_html(draft["body"]), "html", "utf-8")
    msg["to"]      = draft["to_email"]
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


# ─────────────────────────────────────────────
# Broker extraction from inbound emails
# ─────────────────────────────────────────────

def extract_full_body(message):
    """Return full decoded body text (plain preferred, HTML fallback)."""
    parts = message.get("payload", {}).get("parts", [])
    plain, html = "", ""

    def walk(parts_list):
        nonlocal plain, html
        for part in parts_list:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if data:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                if mime == "text/plain":
                    plain += decoded
                elif mime == "text/html":
                    html += decoded
            if "parts" in part:
                walk(part["parts"])

    payload = message.get("payload", {})
    if not parts:
        data = payload.get("body", {}).get("data", "")
        if data:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            if payload.get("mimeType") == "text/html":
                html = decoded
            else:
                plain = decoded
    else:
        walk(parts)

    if plain:
        return plain
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True) if html else ""


# Domains that map directly to a brokerage name
DOMAIN_BROKERAGES = {
    "marcusmillichap.com":      "Marcus & Millichap",
    "cbre.com":                 "CBRE",
    "jll.com":                  "JLL",
    "colliers.com":             "Colliers",
    "cushmanwakefield.com":     "Cushman & Wakefield",
    "svn.com":                  "SVN",
    "bullrealtyinc.com":        "Bull Realty",
    "bullrealtyinc.ccsend.com": "Bull Realty",
    "grea.com":                 "GREA",
    "pwa-properties.com":       "PWA Properties",
    "northmarq.com":            "Northmarq",
    "walkerdunlop.com":         "Walker & Dunlop",
    "matthews.com":             "Matthews",
    "kidder.com":               "Kidder Mathews",
    "avisonyoung.com":          "Avison Young",
    "leeandassociates.com":     "Lee & Associates",
    "berkadia.com":             "Berkadia",
    "taillefercommercial.com":  "Taillefer Commercial",
    "multifamilyadvisors.com":  "Multifamily Advisors",
}

# Automated senders / non-broker domains to skip
SKIP_DOMAINS = {
    "fathom.video", "credaily.com", "mail.mfschooled.com", "mfschooled.com",
    "bestevercre.com", "beehiiv.com", "mailchimp.com", "constantcontact.com",
    "hubspot.com", "marketo.com", "klaviyo.com", "news.credaily.com",
    "e.berkadia.com",    # Berkadia marketing list — not a direct broker contact
    "ccsend.com",        # Constant Contact bulk email platform
    "carvedcapital.com", # Capital raising firm, not a broker
    # Free consumer email — commercial RE brokers use company addresses
    "hotmail.com", "yahoo.com", "aol.com", "outlook.com",
}

SKIP_EMAIL_PREFIXES = (
    "no-reply@", "noreply@", "support@", "mail@", "newsletter@",
    "notifications@", "digest@", "donotreply@", "do-not-reply@",
    "alerts@",
)


def is_broker_sender(email, name):
    """Return True if this looks like a real broker, False if automated/noise."""
    email_lower = email.lower()
    domain = email_lower.split("@")[-1] if "@" in email_lower else ""

    # Exact domain match or subdomain match (e.g. bullrealtyinc.ccsend.com → ccsend.com)
    if domain in SKIP_DOMAINS or any(domain.endswith("." + d) for d in SKIP_DOMAINS):
        return False
    if any(email_lower.startswith(p) for p in SKIP_EMAIL_PREFIXES):
        return False
    if not name or name.lower() in ("unknown", ""):
        return False
    return True


def brokerage_from_domain(email):
    """Infer brokerage from sender email domain."""
    domain = email.lower().split("@")[-1] if "@" in email else ""
    return DOMAIN_BROKERAGES.get(domain, "")


def extract_signature_info(body_text):
    """Pull phone number and brokerage name from email signature (last ~800 chars)."""
    phone, brokerage = "", ""

    # Scan full body for phone (signatures vary in position)
    ph = re.search(r'[\(]?\d{3}[\)\-.\s]?\d{3}[\-.\s]\d{4}', body_text)
    if ph:
        phone = ph.group(0).strip()

    # Only look at the signature area for brokerage to avoid false matches
    sig_zone = body_text[-800:] if len(body_text) > 800 else body_text
    known_brokerages = [
        "Marcus & Millichap", "CBRE", "JLL", "Cushman & Wakefield", "SVN",
        "Bull Realty", "Colliers", "Northmarq", "Walker & Dunlop",
        "Berkshire Hathaway", "BHHS", "GREA", "Watts Realty", "PWA Properties",
        "Kidder Mathews", "Avison Young", "NAI", "Lee & Associates", "Matthews",
        "Berkadia", "Taillefer Commercial", "Multifamily Advisors",
    ]
    tl = sig_zone.lower()
    for b in known_brokerages:
        if b.lower() in tl:
            brokerage = b
            break

    if not brokerage:
        m = re.search(
            r'(?:[Cc]ompany|[Bb]rokerage|[Ff]irm)[:\s]+([A-Z][A-Za-z\s&,\.]+?)(?:\n|\|)',
            sig_zone,
        )
        if m:
            brokerage = m.group(1).strip()

    return phone, brokerage


def parse_email_date(date_header):
    """Parse RFC 2822 date header → MM/DD/YYYY string."""
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
    ]:
        try:
            return datetime.strptime(date_header.strip(), fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return date.today().strftime("%m/%d/%Y")


def get_existing_brokers_full(token):
    """Return (emails_set, names_set) from the full Brokers List sheet."""
    r = requests.get(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers%20List!A1:Z2000",
        headers=auth_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json().get("values", [])
    emails, names = set(), set()
    for row in rows[1:]:
        email = row[2].strip().lower() if len(row) > 2 else ""
        name  = row[1].strip().lower() if len(row) > 1 else ""
        if email: emails.add(email)
        if name:  names.add(name)
    return emails, names


def build_broker_row_from_email(entry):
    """Build a Brokers List row from an inbound-email broker entry."""
    return [
        entry["brokerage"],
        entry["name"],
        entry["email"],
        entry["phone"],
        entry["zip"] or "",              # Markets / Zips
        "Multifamily",                   # Specialty
        "B",                             # Tier — new, no relationship yet
        "No",                            # Buy Box Sent
        str(entry["email_count"]),       # # Deals Sent (emails received)
        entry["last_contact"],           # Last Contact
        "",                              # Next Follow-Up
        "New — Found via Inbound Email", # Status
        f"Auto-added: {entry['email_count']} deal email(s) received. Subject: {entry['last_subject'][:80]}",
    ]


def append_broker_rows(token, rows):
    if not rows:
        return
    r = requests.post(
        f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers%20List!A1:append",
        headers=auth_headers(token),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": rows, "majorDimension": "ROWS"},
        timeout=30,
    )
    r.raise_for_status()


def extract_and_add_brokers(token, results, dry_run, min_contacts=1):
    """
    From scan results, find senders not in the Brokers List and add them.
    min_contacts: minimum number of deal emails to qualify (default 1 —
    direct outreach is already high signal).
    """
    today_str = date.today().strftime("%m/%d/%Y")
    print(f"\n{'='*50}")
    print(f"BROKER EXTRACTION — scanning {len(results)} inbound email(s)\n")

    # Group results by sender email
    by_email = {}
    for result in results:
        email = result["from_email"].lower().strip()
        if not email or "@" not in email:
            continue
        if email not in by_email:
            by_email[email] = []
        by_email[email].append(result)

    # Load existing brokers for dedup
    print("Cross-referencing Brokers List...")
    existing_emails, existing_names = get_existing_brokers_full(token)
    print(f"  {len(existing_emails)} broker(s) already on record\n")

    qualifying, already_in, below_threshold, filtered_out = [], [], [], []

    for email, email_results in by_email.items():
        name = email_results[0]["from_name"]

        # Filter out automated senders / noise (newsletters, no-reply, meeting services)
        if not is_broker_sender(email, name):
            filtered_out.append(email_results[0])
            continue

        # Dedup check
        if email in existing_emails or name.lower() in existing_names:
            already_in.append(email_results[0])
            continue

        if len(email_results) < min_contacts:
            below_threshold.append(email_results[0])
            continue

        qualifying.append(email_results)

    # For qualifying contacts, fetch full bodies to extract phone + brokerage
    broker_rows = []
    print(f"NEW BROKERS QUALIFYING ({len(qualifying)}):")

    for email_results in qualifying:
        first = email_results[0]
        name  = first["from_name"]
        email = first["from_email"]

        # Infer brokerage from sender domain first (more reliable than body scan)
        brokerage = brokerage_from_domain(email)
        phone = ""
        if not brokerage:
            try:
                full_msg  = get_message_full(token, first["id"])
                body_text = extract_full_body(full_msg)
                phone, brokerage = extract_signature_info(body_text)
            except Exception:
                pass

        # Aggregate zips from all emails for this broker
        zips = {r["bb_zip"] for r in email_results if r.get("bb_zip")}
        zip_str = ", ".join(sorted(zips)) if zips else ""

        last_contact  = parse_email_date(first["date"])
        last_subject  = first["subject"]
        email_count   = len(email_results)

        entry = {
            "name":         name,
            "email":        email,
            "phone":        phone,
            "brokerage":    brokerage,
            "zip":          zip_str,
            "last_contact": last_contact,
            "last_subject": last_subject,
            "email_count":  email_count,
        }

        brokerage_label = f" — {brokerage}" if brokerage else ""
        zip_label       = f" | zips: {zip_str}" if zip_str else ""
        print(f"  ✅ {name} <{email}>{brokerage_label} | {email_count} email(s){zip_label}")
        broker_rows.append(build_broker_row_from_email(entry))

    if filtered_out:
        print(f"\nFILTERED (automated/newsletter/noise) ({len(filtered_out)} skipped):")
        for r in filtered_out:
            print(f"  \U0001f6ab {r['from_name']} <{r['from_email']}>")

    if already_in:
        print(f"\nALREADY IN LIST ({len(already_in)} skipped):")
        for r in already_in:
            print(f"  \U000021a9️  {r['from_name']} <{r['from_email']}>")

    if below_threshold:
        print(f"\nBELOW THRESHOLD ({len(below_threshold)} — need {min_contacts}+ email(s)):")
        for r in below_threshold:
            print(f"  —  {r['from_name']} <{r['from_email']}>")

    print(f"\n{'='*50}")
    if dry_run:
        print("[DRY RUN] No changes written.")
    elif broker_rows:
        append_broker_rows(token, broker_rows)
        print(f"✅ {len(broker_rows)} new broker(s) added to Brokers List.")
        print(f"   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    else:
        print("No new brokers to add.")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Olive Tree — Deal Inbox Scanner")
    parser.add_argument("--days",             type=int, default=7,   help="Days to scan back (default: 7)")
    parser.add_argument("--dry-run",          action="store_true",   help="Sandbox mode: scan Gmail but don't send emails or write to sheet")
    parser.add_argument("--doc-request",      type=int, metavar="INDEX", help="Draft a doc-request email for result INDEX (1-based)")
    parser.add_argument("--send",             action="store_true",   help="Send the doc-request draft immediately (use with --doc-request)")
    parser.add_argument("--extract-brokers",  action="store_true",   help="Promote new inbound contacts to the Brokers List")
    parser.add_argument("--min-contacts",     type=int, default=1,   help="Min emails from a sender to qualify (default: 1)")
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
        if args.dry_run:
            print(f"  🧪 DRY RUN — would send to {draft['to_email']} (not sent)")
            print(f"  To send for real: python3 scripts/deal_inbox.py --doc-request {args.doc_request} --send")
        elif args.send:
            send_doc_request(token, draft)
            print(f"✅ Sent to {draft['to_email']}")
        else:
            print(f"  To send: python3 scripts/deal_inbox.py --doc-request {args.doc_request} --send")
        return

    results = scan_inbox(token, args.days, args.dry_run)
    print_results(results)

    if args.extract_brokers:
        extract_and_add_brokers(token, results, args.dry_run,
                                min_contacts=args.min_contacts)

    return results


if __name__ == "__main__":
    main()
