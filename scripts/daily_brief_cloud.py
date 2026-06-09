#!/usr/bin/env python3
"""
Daily Brief — cloud fetch/send helper — Olive Tree Investments

Self-contained Google Workspace access for the cloud `/daily-brief` routine.
The cloud VM has neither the `gws` CLI nor MCP connectors nor `requests`, so this
uses ONLY the Python standard library (urllib) and reads OAuth creds straight
from environment variables. Direct Google REST API — no MCP. Matches Brian's
"always direct API" rule.

Auth: refreshes a short-lived access token from three env vars:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
(For local testing these are auto-loaded from a .env file in the project root if
present. In the cloud routine, set them in the environment's Environment Variables.)

Usage:
  # Pull today's calendar + last-24h deal/investor/starred Gmail as JSON
  python3 scripts/daily_brief_cloud.py fetch

  # Send the finished brief to Brian (body from a file or stdin)
  python3 scripts/daily_brief_cloud.py send \
      --to brian@olivetreeinv.io --subject "Daily Brief — Jun 10" --body-file brief.txt
  echo "..." | python3 scripts/daily_brief_cloud.py send --to brian@olivetreeinv.io --subject "..."

Scopes required on the refresh token: gmail.readonly, gmail.send, calendar.readonly.
"""

import argparse
import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.header import Header

# Trust the system CA store first — on the Claude Code cloud sandbox, outbound
# HTTPS goes through a TLS-inspecting proxy whose CA lives in the system store
# (and/or SSL_CERT_FILE). Then additionally trust certifi's bundle, which some
# local Python builds (e.g. python.org macOS) need because their system store is
# empty. Additive load_verify_locations means both are trusted.
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(cafile=certifi.where())
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9
    ZoneInfo = None

EASTERN = "America/New_York"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
CAL_BASE = "https://www.googleapis.com/calendar/v3"

# Gmail search queries — mirror the daily-brief SKILL.md buckets.
DEAL_Q = ('is:unread newer_than:1d (broker OR LOI OR listing OR multifamily OR '
          'apartment OR "cap rate" OR units OR doors OR "offering memorandum" OR '
          'OM OR NOI OR "under contract" OR "due diligence")')
INVESTOR_Q = ('is:unread newer_than:1d (invest OR LP OR "limited partner" OR '
              'commitment OR capital OR accredited OR PPM OR webinar OR "soft commit")')
STARRED_Q = "is:starred newer_than:1d"


def _load_dotenv():
    """Populate os.environ from a project-root .env (local testing only)."""
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
            "Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN. "
            "Set them in .env (local) or the cloud environment's Environment Variables."
        )
    payload = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    resp = _http("POST", TOKEN_URL,
                 headers={"Content-Type": "application/x-www-form-urlencoded"},
                 data=payload)
    return resp["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Calendar ----------

def fetch_calendar(token):
    if ZoneInfo:
        now = datetime.now(ZoneInfo(EASTERN))
    else:  # fallback: naive local
        now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    params = urllib.parse.urlencode({
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "20",
    })
    data = _http("GET", f"{CAL_BASE}/calendars/primary/events?{params}", headers=_auth(token))
    events = []
    for ev in data.get("items", []):
        start_dt = ev.get("start", {})
        when = start_dt.get("dateTime") or start_dt.get("date") or ""
        events.append({
            "summary": ev.get("summary", "(no title)"),
            "start": when,
            "location": ev.get("location", ""),
            "hangoutLink": ev.get("hangoutLink", ""),
        })
    return events


# ---------- Gmail ----------

def _gmail_search(token, query, limit):
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
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    return {
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", "(no subject)"),
        "date": headers.get("Date", ""),
        "snippet": data.get("snippet", ""),
    }


def fetch_bucket(token, query, limit=10):
    out = []
    for msg_id in _gmail_search(token, query, limit):
        try:
            out.append(_gmail_meta(token, msg_id))
        except RuntimeError:
            continue
    return out


def cmd_fetch(_args):
    token = get_token()
    tz = ZoneInfo(EASTERN) if ZoneInfo else None
    today = datetime.now(tz).strftime("%A, %B %d") if tz else datetime.now().strftime("%A, %B %d")
    result = {
        "date": today,
        "calendar": fetch_calendar(token),
        "deals": fetch_bucket(token, DEAL_Q),
        "investors": fetch_bucket(token, INVESTOR_Q),
        "starred": fetch_bucket(token, STARRED_Q),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_guard(args):
    """Exit 0 if the current Eastern hour matches --hour, else exit 3.

    Lets a UTC-only cron fire at both candidate hours (e.g. 12:00 and 13:00 UTC)
    and run only at the one that is the target local time — auto-handling DST
    with no cron edits across the spring/fall switch.
    """
    if ZoneInfo:
        hour = datetime.now(ZoneInfo(EASTERN)).hour
    else:
        hour = datetime.now().hour
    if hour == args.hour:
        sys.exit(0)
    print(f"skip: Eastern hour is {hour:02d}, not {args.hour:02d}")
    sys.exit(3)


def cmd_send(args):
    token = get_token()
    if args.body_file and args.body_file != "-":
        with open(args.body_file) as fh:
            body = fh.read()
    else:
        body = sys.stdin.read()

    # Subject headers must be ASCII; MIME encoded-word for any non-ASCII (em-dash etc.)
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


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Daily Brief cloud fetch/send helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Print today's calendar + last-24h Gmail buckets as JSON")

    p_guard = sub.add_parser("guard", help="Exit 0 only if current Eastern hour == --hour (else exit 3)")
    p_guard.add_argument("--hour", type=int, required=True, help="Target Eastern hour (0-23)")

    p_send = sub.add_parser("send", help="Email the finished brief")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body-file", help="Path to body text, or '-' for stdin (default stdin)")

    args = parser.parse_args()
    if args.cmd == "fetch":
        cmd_fetch(args)
    elif args.cmd == "guard":
        cmd_guard(args)
    elif args.cmd == "send":
        cmd_send(args)


if __name__ == "__main__":
    main()
