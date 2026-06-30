#!/usr/bin/env python3
"""
Morning Brief — cloud fetch/send helper — Olive Tree Investments

Self-contained Google Workspace access for the cloud `/daily-brief` routine.
Stdlib-only (urllib). Reads OAuth creds from env vars; direct Google REST API.

Auth env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

Usage:
  python3 scripts/daily_brief_cloud.py fetch      # Print all brief data as JSON
  python3 scripts/daily_brief_cloud.py guard --hour 5
  python3 scripts/daily_brief_cloud.py send \\
      --to brian@olivetreeinv.io --subject "..." --body-file /tmp/brief.txt

Scopes needed on refresh token:
  gmail.readonly, gmail.send, calendar.readonly, tasks.readonly (optional)
"""

import argparse
import base64
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.header import Header

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

EASTERN       = "America/New_York"
TOKEN_URL     = "https://oauth2.googleapis.com/token"
GMAIL_BASE    = "https://gmail.googleapis.com/gmail/v1/users/me"
CAL_BASE      = "https://www.googleapis.com/calendar/v3"
TASKS_BASE    = "https://tasks.googleapis.com/tasks/v1"

# Both calendars to pull
CALENDARS = [
    "brian@olivetreeinv.io",
    "briannorton79@gmail.com",
]

DEAL_Q = (
    'is:unread newer_than:1d (broker OR LOI OR listing OR multifamily OR '
    'apartment OR "cap rate" OR units OR doors OR "offering memorandum" OR '
    'OM OR NOI OR "under contract" OR "due diligence")'
)
INVESTOR_Q = (
    'is:unread newer_than:1d (invest OR LP OR "limited partner" OR '
    'commitment OR capital OR accredited OR PPM OR webinar OR "soft commit")'
)
STARRED_Q = "is:starred newer_than:1d"

SPECIAL_KEYWORDS = ("birthday", "bday", "anniversary", "born", "b-day")


# ─── Infra ───────────────────────────────────────────────────────────────────

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
    cid     = os.environ.get("GOOGLE_CLIENT_ID")
    secret  = os.environ.get("GOOGLE_CLIENT_SECRET")
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


def _now_eastern():
    tz = ZoneInfo(EASTERN) if ZoneInfo else None
    return datetime.now(tz) if tz else datetime.now()


# ─── Calendar ────────────────────────────────────────────────────────────────

def _fetch_calendar_events(token, calendar_id, time_min, time_max):
    """Fetch events from one calendar between two datetimes."""
    params = urllib.parse.urlencode({
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "50",
    })
    cal_id_enc = urllib.parse.quote(calendar_id, safe="")
    try:
        data = _http("GET", f"{CAL_BASE}/calendars/{cal_id_enc}/events?{params}",
                     headers=_auth(token))
    except RuntimeError:
        return []

    events = []
    for ev in data.get("items", []):
        start = ev.get("start", {})
        end   = ev.get("end", {})
        when  = start.get("dateTime") or start.get("date") or ""
        when_end = end.get("dateTime") or end.get("date") or ""
        is_allday = "dateTime" not in start
        events.append({
            "summary":    ev.get("summary", "(no title)"),
            "start":      when,
            "end":        when_end,
            "all_day":    is_allday,
            "location":   ev.get("location", ""),
            "calendar":   calendar_id,
        })
    return events


def fetch_all_events(token, days=7):
    """Fetch events from all calendars for today + next N days, grouped by date."""
    now   = _now_eastern()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=days + 1)

    all_events = []
    for cal_id in CALENDARS:
        all_events.extend(_fetch_calendar_events(token, cal_id, start, end))

    # Deduplicate by (summary, start)
    seen, deduped = set(), []
    for ev in all_events:
        key = (ev["summary"], ev["start"])
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    # Group by date string YYYY-MM-DD
    by_date: dict = {}
    for ev in deduped:
        dt_str = ev["start"][:10] if ev["start"] else "unknown"
        by_date.setdefault(dt_str, []).append(ev)

    # Build ordered week list
    today_str = start.strftime("%Y-%m-%d")
    week = []
    for i in range(days + 1):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        week.append({"date": d, "events": by_date.get(d, [])})

    today_events = by_date.get(today_str, [])
    return {"today": today_events, "week": week}


def detect_special_dates(calendar_data):
    """Find birthday/anniversary events across all fetched events."""
    specials = []
    now = _now_eastern().date()
    for day in calendar_data.get("week", []):
        for ev in day.get("events", []):
            title = ev.get("summary", "").lower()
            if any(kw in title for kw in SPECIAL_KEYWORDS):
                try:
                    ev_date = date.fromisoformat(day["date"])
                    days_away = (ev_date - now).days
                except ValueError:
                    days_away = None
                ev_type = "anniversary" if "anniversary" in title else "birthday"
                specials.append({
                    "type":      ev_type,
                    "summary":   ev["summary"],
                    "date":      day["date"],
                    "days_away": days_away,
                })
    return specials


# ─── Tasks ───────────────────────────────────────────────────────────────────

def fetch_tasks(token):
    """Fetch incomplete tasks due this week. Returns gracefully on 403 (scope missing)."""
    try:
        lists_data = _http("GET", f"{TASKS_BASE}/users/@me/lists", headers=_auth(token))
    except RuntimeError as e:
        if "403" in str(e):
            return {"available": False, "items": [], "note": "Re-auth with tasks scope: gws auth login -s gmail,calendar,drive,sheets,tasks"}
        return {"available": False, "items": [], "note": str(e)}

    now  = _now_eastern()
    week_end = (now + timedelta(days=7)).isoformat()

    tasks = []
    for tasklist in lists_data.get("items", []):
        tl_id    = urllib.parse.quote(tasklist["id"], safe="")
        tl_title = tasklist.get("title", "Tasks")
        params   = urllib.parse.urlencode({
            "showCompleted": "false",
            "showHidden":    "false",
            "maxResults":    "20",
        })
        try:
            data = _http("GET", f"{TASKS_BASE}/lists/{tl_id}/tasks?{params}",
                         headers=_auth(token))
        except RuntimeError:
            continue
        for t in data.get("items", []):
            due = t.get("due", "")
            tasks.append({
                "title":    t.get("title", "(untitled)"),
                "due":      due[:10] if due else "",
                "notes":    t.get("notes", ""),
                "list":     tl_title,
                "status":   t.get("status", ""),
            })

    # Sort by due date; undated last
    tasks.sort(key=lambda t: t["due"] or "9999")
    return {"available": True, "items": tasks}


# ─── Gmail ───────────────────────────────────────────────────────────────────

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
    hdrs = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    return {
        "from":    hdrs.get("From", ""),
        "subject": hdrs.get("Subject", "(no subject)"),
        "date":    hdrs.get("Date", ""),
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


# ─── Monday Pipeline ─────────────────────────────────────────────────────────

def fetch_monday_pipeline():
    """Run pipeline_cloud.py fetch as subprocess."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            [sys.executable, os.path.join(here, "pipeline_cloud.py"), "fetch"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


# ─── Fetch command ────────────────────────────────────────────────────────────

def cmd_fetch(_args):
    token = get_token()
    now   = _now_eastern()
    today_str = now.strftime("%A, %B %d, %Y")

    calendar_data  = fetch_all_events(token, days=7)
    special_dates  = detect_special_dates(calendar_data)
    tasks_data     = fetch_tasks(token)
    pipeline       = fetch_monday_pipeline()

    result = {
        "date":          today_str,
        "today_iso":     now.strftime("%Y-%m-%d"),
        "is_monday":     now.weekday() == 0,
        "calendar":      calendar_data,
        "special_dates": special_dates,
        "tasks":         tasks_data,
        "deals":         fetch_bucket(token, DEAL_Q),
        "investors":     fetch_bucket(token, INVESTOR_Q),
        "starred":       fetch_bucket(token, STARRED_Q),
        "pipeline":      pipeline,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ─── Guard ────────────────────────────────────────────────────────────────────

def cmd_guard(args):
    """Exit 0 if current Eastern hour == --hour, else exit 3."""
    hour = _now_eastern().hour
    if hour == args.hour:
        sys.exit(0)
    print(f"skip: Eastern hour is {hour:02d}, not {args.hour:02d}")
    sys.exit(3)


# ─── Send ─────────────────────────────────────────────────────────────────────

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
    raw  = base64.urlsafe_b64encode(msg.encode()).decode()
    resp = _http("POST", f"{GMAIL_BASE}/messages/send",
                 headers={**_auth(token), "Content-Type": "application/json"},
                 data=json.dumps({"raw": raw}).encode())
    print(f"Sent. Gmail message id: {resp.get('id', '?')}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Morning Brief cloud helper")
    sub    = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Print all brief data as JSON")

    p_guard = sub.add_parser("guard", help="DST-safe hour gate")
    p_guard.add_argument("--hour", type=int, required=True)

    p_send = sub.add_parser("send", help="Email the finished brief")
    p_send.add_argument("--to",        required=True)
    p_send.add_argument("--subject",   required=True)
    p_send.add_argument("--body-file", help="Path to body text, or '-' for stdin")

    args = parser.parse_args()
    {"fetch": cmd_fetch, "guard": cmd_guard, "send": cmd_send}[args.cmd](args)


if __name__ == "__main__":
    main()
