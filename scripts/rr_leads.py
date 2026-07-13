#!/usr/bin/env python3
"""
Olive Tree — Rank & Rent Lead Ledger (the /rr_leads engine)

Pulls Twilio call logs for each rented tracking number, logs them to
olive.db, and produces the monthly billing report to send the renter.
Sites/numbers/billing terms live in rank-rent/numbers.json.

Usage:
  python3 scripts/rr_leads.py --sync
  python3 scripts/rr_leads.py --sync --month 2026-07
  python3 scripts/rr_leads.py --report
  python3 scripts/rr_leads.py --report 2026-07
  python3 scripts/rr_leads.py --setup-help
"""

import argparse
import calendar
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import text

from db.connection import engine  # noqa: E402

load_dotenv()

NUMBERS_FILE = Path(__file__).parent.parent / "rank-rent" / "numbers.json"

_DDL = """
CREATE TABLE IF NOT EXISTS rr_leads (
    call_sid TEXT PRIMARY KEY,
    site_slug TEXT NOT NULL,
    from_number TEXT,
    to_number TEXT,
    start_time TEXT,
    duration_sec INTEGER,
    billable INTEGER NOT NULL DEFAULT 0
)
"""


def _ensure_table():
    with engine.begin() as conn:
        conn.execute(text(_DDL))


def _load_numbers():
    if not NUMBERS_FILE.exists():
        sys.exit(f"Missing {NUMBERS_FILE}. Add a site entry first.")
    sites = json.loads(NUMBERS_FILE.read_text())
    for s in sites:
        missing = {"site_slug", "tracking_number", "billing"} - s.keys()
        if missing:
            sys.exit(f"numbers.json entry missing keys: {sorted(missing)} in {s}")
    return sites


def _month_bounds(month_str):
    """'2026-07' -> ('2026-07-01', '2026-07-31'); defaults to current month."""
    if month_str:
        y, m = (int(x) for x in month_str.split("-"))
    else:
        today = date.today()
        y, m = today.year, today.month
    # Twilio treats "StartTime<=YYYY-MM-DD" as midnight of that date, so the
    # end bound must be the 1st of the NEXT month or the last day's calls drop.
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01", f"{y:04d}-{m:02d}"


def _fetch_calls(sid, token, to_number, start, end):
    """Twilio Calls list API, paginated. Returns raw call dicts."""
    import requests
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    params = {"To": to_number, "StartTime>=": start, "StartTime<=": end, "PageSize": 50}
    calls = []
    while url:
        resp = requests.get(url, params=params, auth=(sid, token), timeout=20)
        resp.raise_for_status()
        data = resp.json()
        calls.extend(data.get("calls", []))
        next_uri = data.get("next_page_uri")
        url = f"https://api.twilio.com{next_uri}" if next_uri else None
        params = None  # next_page_uri already has the query string baked in
    return calls


def cmd_sync(a):
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        sys.exit("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env.")
    _ensure_table()
    numbers = _load_numbers()
    start, end, month = _month_bounds(a.month)

    total_new = 0
    for site in numbers:
        min_seconds = site["billing"].get("min_seconds", 60)
        calls = _fetch_calls(sid, token, site["tracking_number"], start, end)
        with engine.begin() as conn:
            for c in calls:
                dur = int(c.get("duration") or 0)
                conn.execute(text("""
                    INSERT INTO rr_leads
                        (call_sid, site_slug, from_number, to_number, start_time,
                         duration_sec, billable)
                    VALUES (:sid, :slug, :from_n, :to_n, :start, :dur, :billable)
                    ON CONFLICT(call_sid) DO UPDATE SET
                        duration_sec=excluded.duration_sec, billable=excluded.billable
                """), {
                    "sid": c["sid"], "slug": site["site_slug"],
                    "from_n": c.get("from"), "to_n": c.get("to"),
                    "start": c.get("start_time"), "dur": dur,
                    "billable": int(dur >= min_seconds),
                })
        total_new += len(calls)
        print(f"  {site['site_slug']}: {len(calls)} call(s) synced for {month}")
    print(f"\n{total_new} call(s) synced across {len(numbers)} site(s).")


def cmd_report(a):
    _ensure_table()
    numbers = _load_numbers()
    _, _, month = _month_bounds(a.month)

    with engine.begin() as conn:
        any_rows = conn.execute(text("SELECT COUNT(*) FROM rr_leads")).scalar()
    if not any_rows:
        print("No leads synced yet. Run --sync first.")
        return

    print(f"\n  Lead report — {month}\n")
    for site in numbers:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT COUNT(*) AS total, SUM(billable) AS billable
                FROM rr_leads WHERE site_slug=:slug AND start_time LIKE :m
            """), {"slug": site["site_slug"], "m": f"{month}%"}).first()
        total = rows.total or 0
        billable = rows.billable or 0
        billing = site["billing"]
        if billing["type"] == "flat":
            due = billing["flat_monthly"]
            rate_desc = f"flat ${billing['flat_monthly']}/mo"
        else:
            due = billable * billing["per_call"]
            rate_desc = f"${billing['per_call']}/call"

        print(f"  {'='*55}")
        print(f"  {site['site_slug']}  ({site['renter_name']})")
        print(f"  {'='*55}")
        print(f"  Total calls:     {total}")
        print(f"  Billable calls:  {billable}  (>= {billing.get('min_seconds', 60)}s)")
        print(f"  Rate:            {rate_desc}")
        print(f"  Amount due:      ${due:,.2f}")
        print(f"\n  --- paste into renter email ---")
        print(f"  Hi {site['renter_name']}, here's your {month} lead report for "
              f"{site['site_slug']}: {total} calls, {billable} billable. "
              f"Amount due: ${due:,.2f}.\n")


def cmd_setup_help(_a):
    print("""
  Provisioning a Twilio tracking number (manual, one-time per site):

  1. Twilio Console -> Phone Numbers -> Buy a Number (local, matching the
     site's market area code where possible). ~$1.15/mo.
  2. Open the number -> Voice Configuration -> "A call comes in":
     set to "TwiML Bin" and create a bin with:
       <Response><Dial>+1RENTERPHONE</Dial></Response>
     (or simpler: set "A call comes in" directly to "Forward to" the
     renter's phone if your Twilio plan supports it without a TwiML Bin.)
  3. Copy the number in E.164 format (+1XXXXXXXXXX) into
     rank-rent/numbers.json as tracking_number, with forwards_to,
     renter_name, and billing terms for that site.
  4. Put the same tracking number as the phone/click-to-call number on
     the rented site itself.
  5. Test: call the tracking number, confirm it forwards, then run
     `rr_leads.py --sync` after the call to confirm it logs.
""")


def main():
    ap = argparse.ArgumentParser(description="Rank & Rent lead ledger + billing.")
    ap.add_argument("--sync", action="store_true", help="Pull Twilio call logs")
    ap.add_argument("--report", nargs="?", const="", metavar="YYYY-MM",
                    help="Print monthly billing report")
    ap.add_argument("--month", metavar="YYYY-MM", help="Month for --sync (default: current)")
    ap.add_argument("--setup-help", action="store_true",
                    help="Print Twilio number provisioning steps")
    a = ap.parse_args()

    if a.setup_help:
        cmd_setup_help(a)
    elif a.sync:
        cmd_sync(a)
    elif a.report is not None:
        a.month = a.report or None
        cmd_report(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
