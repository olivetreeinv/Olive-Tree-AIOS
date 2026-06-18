#!/usr/bin/env python3
"""
Monday Pipeline — cloud fetch/send helper — Olive Tree Investments

Runs the data-gather phases of /lets-get-to-work and emails a Monday War Room
digest to Brian before he's at his desk. No interactive steps — approvals,
LOIs, and deal analysis happen in the follow-up session.

Stdlib-only (urllib). Reads OAuth creds from env vars; direct Google REST API.
Auth: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.

Usage:
  python3 scripts/pipeline_cloud.py fetch      # Print pipeline data as JSON
  python3 scripts/pipeline_cloud.py send \\
      --to brian@olivetreeinv.io \\
      --subject "Monday War Room — Jun 23" \\
      --body-file /tmp/war_room.txt
  python3 scripts/pipeline_cloud.py guard --hour 7   # DST-safe cron guard

Cloud cron: 0 11,12 * * 1   (Mon 11:00 + 12:00 UTC; guard keeps only 7am ET)
"""

import argparse
import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.header import Header

# Trust system CA (proxy CA) + certifi (macOS python.org builds) — same as daily_brief_cloud.py
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(cafile=certifi.where())
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

EASTERN = "America/New_York"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

SPREADSHEET_ID = "1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4"

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
    "37918": "Knoxville, TN",
    "37804": "Maryville, TN",
    "37615": "Johnson City, TN",
}

# Gmail queries
LISTING_Q = (
    'newer_than:7d from:(crexi.com OR loopnet.com OR noreply@crexi.com OR alerts@loopnet.com) '
    '(multifamily OR apartment OR units OR "for sale")'
)
DEAL_INBOX_Q = (
    'newer_than:7d -from:me '
    '(subject:"offering memorandum" OR subject:"OM" OR subject:"multifamily" '
    'OR subject:"for sale" OR subject:"apartment" OR subject:"rent roll" '
    'OR subject:"T-12" OR "cap rate" OR "asking price")'
)


# ─── HTTP ───────────────────────────────────────────────────────────────────

def _load_dotenv():
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(os.path.dirname(here), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {body}") from e


def get_token():
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh = os.environ.get("GOOGLE_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        raise RuntimeError(
            "Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN."
        )
    payload = urllib.parse.urlencode({
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token",
    }).encode()
    resp = _http("POST", TOKEN_URL,
                 headers={"Content-Type": "application/x-www-form-urlencoded"},
                 data=payload)
    return resp["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Gmail ──────────────────────────────────────────────────────────────────

def _gmail_search(token, query, limit=20):
    params = urllib.parse.urlencode({"q": query, "maxResults": str(limit)})
    data = _http("GET", f"{GMAIL_BASE}/messages?{params}", headers=_auth(token))
    return [m["id"] for m in data.get("messages", [])]


def _gmail_meta(token, msg_id):
    params = urllib.parse.urlencode(
        [("format", "metadata"),
         ("metadataHeaders", "From"),
         ("metadataHeaders", "Subject"),
         ("metadataHeaders", "Date")]
    )
    data = _http("GET", f"{GMAIL_BASE}/messages/{msg_id}?{params}", headers=_auth(token))
    hdrs = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    return {
        "id": msg_id,
        "from": hdrs.get("From", ""),
        "subject": hdrs.get("Subject", "(no subject)"),
        "date": hdrs.get("Date", ""),
        "snippet": data.get("snippet", ""),
    }


def _fetch_emails(token, query, limit=20):
    results = []
    for msg_id in _gmail_search(token, query, limit):
        try:
            results.append(_gmail_meta(token, msg_id))
        except RuntimeError:
            continue
    return results


def _buy_box_flag(text):
    """Return matched zip + market name if any buy-box zip appears in text."""
    for z, market in BUY_BOX.items():
        if z in text:
            return z, market
    return None, None


def fetch_listings(token):
    """Scan listing alert emails for buy-box matches."""
    emails = _fetch_emails(token, LISTING_Q, limit=30)
    in_box, outside = [], []
    seen_subjects = set()
    for em in emails:
        subj = em["subject"]
        if subj in seen_subjects:
            continue
        seen_subjects.add(subj)
        combined = f"{subj} {em['snippet']}"
        zip_match, market = _buy_box_flag(combined)
        entry = {
            "subject": subj,
            "from": em["from"],
            "date": em["date"],
            "snippet": em["snippet"][:120],
        }
        if zip_match:
            entry["zip"] = zip_match
            entry["market"] = market
            in_box.append(entry)
        else:
            outside.append(entry)
    return {"in_buy_box": in_box, "outside": outside}


def fetch_inbound_deals(token):
    """Scan inbound broker deal submission emails."""
    emails = _fetch_emails(token, DEAL_INBOX_Q, limit=20)
    results = []
    seen = set()
    for em in emails:
        key = (em["from"], em["subject"])
        if key in seen:
            continue
        seen.add(key)
        combined = f"{em['subject']} {em['snippet']}"
        zip_match, market = _buy_box_flag(combined)
        results.append({
            "from": em["from"],
            "subject": em["subject"],
            "date": em["date"],
            "snippet": em["snippet"][:140],
            "buy_box_zip": zip_match,
            "buy_box_market": market,
        })
    return results


# ─── Sheets — Broker overdue follow-ups ─────────────────────────────────────

def fetch_overdue_brokers(token):
    """Read the Brokers List tab and return brokers with overdue follow-ups."""
    url = (f"{SHEETS_BASE}/{SPREADSHEET_ID}/values/Brokers%20List!A1:Z500")
    data = _http("GET", url, headers=_auth(token))
    rows = data.get("values", [])
    if not rows:
        return []

    headers = [h.strip() for h in rows[0]]
    col = {h: i for i, h in enumerate(headers)}

    def get(row, name):
        i = col.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    today = date.today()
    overdue = []
    for row in rows[1:]:
        status = get(row, "Status")
        if status.lower() == "dormant":
            continue
        follow_up_str = get(row, "Next Follow-Up")
        if not follow_up_str:
            continue
        try:
            follow_up = datetime.strptime(follow_up_str, "%m/%d/%Y").date()
        except ValueError:
            try:
                follow_up = datetime.strptime(follow_up_str, "%Y-%m-%d").date()
            except ValueError:
                continue
        if follow_up <= today:
            name = get(row, "Name") or get(row, "Broker Name")
            overdue.append({
                "name": name,
                "brokerage": get(row, "Brokerage"),
                "email": get(row, "Email"),
                "markets": get(row, "Markets") or get(row, "Zips"),
                "last_contact": get(row, "Last Contact"),
                "next_follow_up": follow_up_str,
                "tier": get(row, "Tier"),
                "status": status,
            })
    return overdue


# ─── Fetch command ───────────────────────────────────────────────────────────

def cmd_fetch(_args):
    token = get_token()
    tz = ZoneInfo(EASTERN) if ZoneInfo else None
    today_str = (datetime.now(tz) if tz else datetime.now()).strftime("%A, %B %d, %Y")
    result = {
        "date": today_str,
        "listings": fetch_listings(token),
        "inbound_deals": fetch_inbound_deals(token),
        "overdue_brokers": fetch_overdue_brokers(token),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ─── Guard command ───────────────────────────────────────────────────────────

def cmd_guard(args):
    """Exit 0 only if current Eastern hour == --hour (else exit 3)."""
    tz = ZoneInfo(EASTERN) if ZoneInfo else None
    hour = (datetime.now(tz) if tz else datetime.now()).hour
    if hour == args.hour:
        sys.exit(0)
    print(f"skip: Eastern hour is {hour:02d}, not {args.hour:02d}")
    sys.exit(3)


# ─── Send command ────────────────────────────────────────────────────────────

def cmd_send(args):
    token = get_token()
    if args.body_file and args.body_file != "-":
        with open(args.body_file) as fh:
            body = fh.read()
    else:
        body = sys.stdin.read()

    subject = Header(args.subject, "utf-8").encode()
    msg = (
        f"From: brian@olivetreeinv.io\r\n"
        f"To: {args.to}\r\n"
        f"Subject: {subject}\r\n"
        f"Content-Type: text/plain; charset=UTF-8\r\n\r\n"
        f"{body}"
    )
    raw = base64.urlsafe_b64encode(msg.encode()).decode()
    payload = json.dumps({"raw": raw}).encode()
    resp = _http("POST", f"{GMAIL_BASE}/messages/send",
                 headers={**_auth(token), "Content-Type": "application/json"},
                 data=payload)
    print(f"Sent. Gmail message id: {resp.get('id', '?')}")


# ─── Format helper (used by cloud agent in the routine prompt) ───────────────

def format_war_room(data: dict) -> str:
    """Format pipeline fetch JSON into the Monday War Room email body."""
    lines = [
        f"Monday War Room — {data.get('date', 'Today')}",
        "=" * 50,
        "",
    ]

    # Listings
    listings = data.get("listings", {})
    in_box = listings.get("in_buy_box", [])
    outside = listings.get("outside", [])
    lines.append(f"NEW LISTINGS — {len(in_box)} in buy box | {len(outside)} outside")
    if in_box:
        for i, l in enumerate(in_box[:10], 1):
            lines.append(f"  {i}. {l['subject']}")
            lines.append(f"     {l.get('market', l.get('zip', '?'))} | {l['snippet']}")
    else:
        lines.append("  None found in buy-box zips.")
    lines.append("")

    # Overdue brokers
    overdue = data.get("overdue_brokers", [])
    lines.append(f"BROKER FOLLOW-UPS DUE — {len(overdue)} overdue (nothing sent — review in session)")
    if overdue:
        for b in overdue[:10]:
            tier = f"Tier {b['tier']}" if b.get("tier") else ""
            mkt = b.get("markets", "")
            lines.append(f"  - {b['name']} | {b['brokerage']} | {tier} | last: {b['last_contact']} | {mkt}")
    else:
        lines.append("  None overdue.")
    lines.append("")

    # Inbound deals
    inbound = data.get("inbound_deals", [])
    lines.append(f"INBOUND DEAL EMAILS — {len(inbound)} found")
    if inbound:
        for i, d in enumerate(inbound[:10], 1):
            bb = f"  buy box: {d['buy_box_market']}" if d.get("buy_box_market") else "  buy box: unverified"
            lines.append(f"  {i}. {d['subject']}")
            lines.append(f"     From: {d['from']} |{bb}")
            lines.append(f"     {d['snippet']}")
    else:
        lines.append("  None found.")
    lines.append("")

    lines += [
        "─" * 50,
        "Drafts ready. Nothing sent. Run /lets-get-to-work to action this.",
        "",
        "-Olive",
    ]
    return "\n".join(lines)


def cmd_format(args):
    """Read fetch JSON from --input file (or stdin) and print formatted body."""
    if args.input and args.input != "-":
        with open(args.input) as fh:
            data = json.load(fh)
    else:
        data = json.load(sys.stdin)
    print(format_war_room(data))


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Monday Pipeline cloud fetch/send helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Print pipeline data as JSON")

    p_guard = sub.add_parser("guard", help="Exit 0 only if current Eastern hour == --hour")
    p_guard.add_argument("--hour", type=int, required=True)

    p_fmt = sub.add_parser("format", help="Format fetch JSON into email body")
    p_fmt.add_argument("--input", help="JSON file from fetch (default stdin)")

    p_send = sub.add_parser("send", help="Email the war room digest")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body-file", help="Path to body text, or '-' for stdin")

    args = parser.parse_args()
    if args.cmd == "fetch":
        cmd_fetch(args)
    elif args.cmd == "guard":
        cmd_guard(args)
    elif args.cmd == "format":
        cmd_format(args)
    elif args.cmd == "send":
        cmd_send(args)


if __name__ == "__main__":
    main()
