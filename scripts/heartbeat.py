#!/usr/bin/env python3
"""
heartbeat.py — one morning ops check so Brian never has to ask
"is the trading desk running?" / "did the brief send?" again.

Checks: launchd jobs, trading-desk log freshness, daily-scan freshness,
Morning Brief email arrival, olive.db, new deal-doc drops, top loose ends.
Prints GREEN/RED per system; --notify pushes the summary via ntfy (notify.sh).

Usage:
  python3 scripts/heartbeat.py            # print report
  python3 scripts/heartbeat.py --notify   # + push summary to phone

launchd: com.olivetree.heartbeat — weekdays 7:45am ET.
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO / ".env")

import requests

from scripts.deal_intake import find_candidates, _seen as intake_seen
from scripts.loose_ends import harvest

TRADING_LOG = Path.home() / "Library/Logs/trading-desk.log"
SCAN_LOG = REPO / "output" / "daily_scan" / "scan.log"
DB = REPO / "data" / "olive.db"

# KeepAlive jobs must show a PID; calendar jobs must be loaded with exit 0.
# (label, kind, plain-language name)
EXPECTED_JOBS = {
    "com.olivetree.trading-desk": ("keepalive", "Trading desk (paper-trading loop)"),
    "com.olivetree.dailyscan": ("calendar", "Daily deal scan (Crexi/LoopNet/FMLS listings)"),
    "com.olivetree.aios-autocommit": ("calendar", "AIOS auto-commit (hourly git backup)"),
    "com.olivetree.heartbeat": ("calendar", "Heartbeat (this 7:45am check)"),
    "com.olivetree.usage-audit": ("calendar", "Monthly usage audit (1st of month)"),
}


def _age_minutes(p: Path) -> float | None:
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 60


def check_launchd() -> list[tuple[bool, str]]:
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=15).stdout
    except Exception as e:
        return [(False, f"launchctl unreachable: {e}")]
    rows = {}
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            rows[parts[2]] = (parts[0], parts[1])  # (pid, last exit status)
    results = []
    for label, (kind, name) in EXPECTED_JOBS.items():
        if label not in rows:
            results.append((False, f"{name}: NOT SCHEDULED — macOS lost the job; reload with `launchctl load ~/Library/LaunchAgents/{label}.plist`"))
            continue
        pid, status = rows[label]
        if kind == "keepalive":
            ok = pid != "-"
            results.append((ok, f"{name}: running now (pid {pid})" if ok
                            else f"{name}: DOWN — process not running, last exit code {status}"))
        else:
            ok = status == "0"
            results.append((ok, f"{name}: scheduled, last run finished clean" if ok
                            else f"{name}: scheduled, but last run FAILED (exit code {status}) — check its log"))
    return results


def check_trading_log() -> tuple[bool, str]:
    age = _age_minutes(TRADING_LOG)
    if age is None:
        return False, "Trading desk activity: no log file — the desk has never written anything; is it installed?"
    # loop interval is 300s; 20 min of silence means the loop is wedged
    ok = age < 20
    return ok, (f"Trading desk activity: alive, last log write {age:.0f} min ago" if ok
                else f"Trading desk activity: WEDGED — no log writes in {age:.0f} min (expects one every ~5); restart the desk")


def check_daily_scan() -> tuple[bool, str]:
    age = _age_minutes(SCAN_LOG)
    if age is None:
        return False, "Daily deal scan output: no scan log found — the scan has never run"
    # ponytail: 4-day threshold dodges weekend/7:45-vs-9:40 false alarms;
    # catches sustained failure, not a single miss
    ok = age < 60 * 24 * 4
    return ok, (f"Daily deal scan output: last scan ran {age / 60 / 24:.1f} days ago" if ok
                else f"Daily deal scan output: STALE — no scan in {age / 60 / 24:.1f} days; check the dailyscan job")


def _google_token() -> str:
    """Local auth lives in the gws keyring; .env GOOGLE_* is the fallback."""
    try:
        from scripts.gws_auth import get_token
        return get_token()
    except Exception:
        pass
    cid, secret, refresh = (os.getenv(k) for k in
                            ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"))
    if not all([cid, secret, refresh]):
        raise RuntimeError("no gws keyring access and no GOOGLE_* creds in .env")
    return requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token",
    }, timeout=15).json()["access_token"]


def check_morning_brief() -> tuple[bool, str]:
    if datetime.now().weekday() >= 5:
        return True, "Morning Brief email: weekend — no brief expected today"
    try:
        tok = _google_token()
        r = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": 'subject:"morning brief" newer_than:1d', "maxResults": 1},
            headers={"Authorization": f"Bearer {tok}"}, timeout=15,
        ).json()
        ok = bool(r.get("messages"))
        return ok, ("Morning Brief email: today's brief is in your inbox" if ok
                    else "Morning Brief email: NOT in inbox yet — the 8am cloud routine may have failed; check claude.ai/code")
    except Exception as e:
        return False, f"Morning Brief email: couldn't check Gmail ({e})"


def unreviewed_scripts() -> list[str]:
    """scripts/*.py modified since the newest Codex review report."""
    reviews = list((REPO / ".codex-review").glob("*.md"))
    last = max((p.stat().st_mtime for p in reviews), default=0)
    return sorted(
        p.name for p in (REPO / "scripts").glob("*.py") if p.stat().st_mtime > last
    )


def check_db() -> tuple[bool, str]:
    try:
        con = sqlite3.connect(DB, timeout=5)
        n = con.execute("select count(*) from sqlite_master").fetchone()[0]
        con.close()
        return True, f"olive.db (CRM + deals + trading database): healthy, {n} tables readable"
    except Exception as e:
        return False, f"olive.db (CRM + deals + trading database): CAN'T OPEN — {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true")
    args = ap.parse_args()

    checks: list[tuple[bool, str]] = []
    checks.extend(check_launchd())
    checks.append(check_trading_log())
    checks.append(check_daily_scan())
    checks.append(check_morning_brief())
    checks.append(check_db())

    today = datetime.now()
    print(f"OLIVE AIOS HEARTBEAT — {today:%a %b %d %H:%M}")
    print("  (GREEN = healthy, RED = needs your attention)\n")
    for ok, msg in checks:
        print(f"  {'GREEN' if ok else 'RED  '}  {msg}")

    reds = [msg for ok, msg in checks if not ok]

    # Auxiliary sections must never kill the monitor itself.
    new_deals = []
    try:
        new_deals = [c for c in find_candidates() if c["path"] not in intake_seen()]
        if new_deals:
            print(f"\n  DEALS: {len(new_deals)} new doc drop(s) in ~/Downloads — run: python3 scripts/deal_intake.py")
    except Exception as e:
        print(f"\n  DEALS: intake scan failed ({e})")

    stale = []
    try:
        stale = unreviewed_scripts()
        if stale:
            print(f"\n  CODE REVIEW: {len(stale)} script(s) edited since last Codex review — run: scripts/codex_review.sh")
    except Exception as e:
        print(f"\n  CODE REVIEW: check failed ({e})")

    try:
        ends = harvest()[:3]
        if ends:
            print("\n  TOP LOOSE ENDS:")
            for d, src, line in ends:
                print(f"    [{d}] {line}")
    except Exception as e:
        print(f"\n  LOOSE ENDS: harvest failed ({e})")

    # Cadence nudges
    if today.weekday() == 0:
        print("\n  MONDAY: War Room digest is in your inbox — run /lets-get-to-work for the decision half.")
    if today.weekday() == 4:
        print("\n  FRIDAY: run /q3-scoreboard.")

    n_ok = len(checks) - len(reds)
    summary = (f"All {n_ok} systems green" if not reds
               else f"{len(reds)} RED — " + "; ".join(r.split(":")[0] for r in reds))
    if new_deals:
        summary += f" · {len(new_deals)} new deal folder(s)"
    if stale:
        summary += f" · {len(stale)} unreviewed script(s)"
    print(f"\n  SUMMARY: {summary}")

    if args.notify:
        try:
            subprocess.run(["/bin/sh", str(REPO / "scripts" / "notify.sh"), "Heartbeat", summary], timeout=30)
        except Exception as e:
            print(f"  notify failed: {e}")


if __name__ == "__main__":
    main()
