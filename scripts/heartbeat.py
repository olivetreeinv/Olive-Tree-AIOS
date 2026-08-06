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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO / ".env")

import requests

from scripts.deal_intake import find_candidates, _seen as intake_seen
from scripts.loose_ends import harvest

# Logs live in the repo (launchd/*.plist.tmpl writes them to __REPO__/logs/), so they
# travel with the project. Falls back to the old ~/Library/Logs path for older installs.
TRADING_LOG = next(
    (p for p in (REPO / "logs" / "trading-desk.log",
                 Path.home() / "Library/Logs/trading-desk.log") if p.exists()),
    REPO / "logs" / "trading-desk.log",
)
DB = REPO / "data" / "olive.db"
AUTOCOMMIT_LOG = REPO / "logs" / "auto-commit.log"

# KeepAlive jobs must show a PID; calendar jobs must be loaded with exit 0.
# (label, kind, plain-language name)
EXPECTED_JOBS = {
    "com.olivetree.trading-desk": ("keepalive", "Trading desk (paper-trading loop)"),
    "com.olivetree.aios-autocommit": ("calendar", "AIOS auto-commit (hourly git backup)"),
    "com.olivetree.heartbeat": ("calendar", "Heartbeat (this 7:45am check)"),
    "com.olivetree.usage-audit": ("calendar", "Monthly usage audit (1st of month)"),
    "com.olivetree.morning-deal-scan": ("calendar", "Morning deal scan (Crexi buy-box + broker replies, 8am)"),
    "com.olivetree.goal-watch": ("calendar", "Goal Watch (12:30pm judge)"),
    "com.olivetree.drip": ("calendar", "Drip worker (9am)"),
    "com.olivetree.remote-control": ("keepalive", "Remote Control (phone session)"),
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


# NYSE full-close days, observed dates. The desk itself asks Alpaca's clock
# (holiday-aware); this list only keeps the silence math honest. Extend each
# December — check_holiday_calendar() REDs when it runs dry.
MARKET_HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def _minutes_since_market() -> float:
    """Minutes since an equities/extended session (Mon–Fri 9:30am–8pm ET,
    excluding NYSE holidays) was last active; 0 while one is on. The desk logs
    hourly in-session but only once per idle stretch, so a closed market means
    legitimate silence."""
    now = datetime.now(ZoneInfo("America/New_York"))
    for d in range(8):
        day = now - timedelta(days=d)
        if day.weekday() >= 5 or f"{day:%Y-%m-%d}" in MARKET_HOLIDAYS:
            continue
        if d == 0 and now < day.replace(hour=9, minute=30, second=0, microsecond=0):
            continue  # today's session hasn't opened yet — keep walking back
        close = day.replace(hour=20, minute=0, second=0, microsecond=0)
        if now <= close:
            return 0.0
        return (now - close).total_seconds() / 60
    return 0.0


def check_holiday_calendar() -> tuple[bool, str] | None:
    """None (silent) while MARKET_HOLIDAYS covers the current year; RED once it
    runs dry so the list gets extended instead of quietly reverting to
    one-false-alarm-per-holiday."""
    last = max(MARKET_HOLIDAYS)
    if f"{datetime.now():%Y}" > last[:4]:
        return False, (f"Market-holiday calendar: EXPIRED (last entry {last}) — "
                       f"extend MARKET_HOLIDAYS in scripts/heartbeat.py with next year's NYSE closures")
    return None


def check_trading_log() -> tuple[bool, str]:
    age = _age_minutes(TRADING_LOG)
    if age is None:
        return False, "Trading desk activity: no log file — the desk has never written anything; is it installed?"
    # v3 desk wakes hourly (--interval 3600) and logs one line per wake while a
    # session is active; a weekend/overnight of silence is normal (bit us
    # 2026-08-03: Monday-7:45am check called a healthy idle desk WEDGED).
    ok = age < _minutes_since_market() + 75
    if not ok:
        return False, f"Trading desk activity: WEDGED — silent for {age:.0f} min of open market (expects one log write every ~60); restart the desk"
    return True, (f"Trading desk activity: alive, last log write {age:.0f} min ago" if age < 75
                  else f"Trading desk activity: quiet since the market closed — last write {age/60:.0f}h ago, normal for an idle desk")


def check_desk_code_fresh() -> tuple[bool, str]:
    """RED when any trading script was edited AFTER the desk process started —
    the loop imports modules once, so it's running stale code from memory until
    kickstarted. Bit us 2026-07-27: guard fix landed on disk, the running loop
    kept the old guard and false-halted all day."""
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=15).stdout
        pid = next((l.split("\t")[0] for l in out.splitlines()
                    if l.endswith("com.olivetree.trading-desk")), "-")
        if pid in ("-", ""):
            return True, "Trading desk code: desk not running (freshness n/a — see the launchd check)"
        ps = subprocess.run(["ps", "-o", "lstart=", "-p", pid],
                            capture_output=True, text=True, timeout=15).stdout
        started = datetime.strptime(" ".join(ps.split()), "%a %b %d %H:%M:%S %Y").timestamp()
        newest = max(f.stat().st_mtime for f in (REPO / "scripts").glob("trading_*.py"))
        if newest > started:
            return False, ("Trading desk code: STALE — a trading script changed after the desk "
                           "started; it's running old code from memory. Restart: "
                           "launchctl kickstart -k gui/501/com.olivetree.trading-desk")
        return True, "Trading desk code: process is newer than every trading script"
    except Exception as e:
        # fail closed, not open — a swallowed error here is the same false-green
        # bug that hid the check_morning_brief outage; don't repeat it.
        return False, f"Trading desk code: freshness check FAILED ({e}) — treat as unknown, not healthy"


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


def _brief_subject(dt: datetime) -> str:
    """Exact subject the cloud routine sends: `date '+%A Morning Brief — %b %d'`."""
    return dt.strftime("%A Morning Brief — %b %d")


# ponytail: cheap format-drift guard — real example confirmed in Gmail 2026-07-27
assert _brief_subject(datetime(2026, 7, 27)) == "Monday Morning Brief — Jul 27"


def check_morning_brief() -> tuple[bool, str]:
    if datetime.now().weekday() >= 5:
        return True, "Morning Brief email: weekend — no brief expected today"
    try:
        tok = _google_token()
        # Match today's exact subject, not a fuzzy "morning brief" + newer_than:1d —
        # Gmail's newer_than: buckets by calendar day and was still matching a
        # 2-3 day old brief, masking two real back-to-back outages (7/28, 7/29).
        subject = _brief_subject(datetime.now())
        r = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            # in:anywhere — Brian reads the brief on his phone and swipe-deletes it,
            # and a bare query skips Trash, so a read brief looked like a failed send.
            params={"q": f'subject:"{subject}" in:anywhere', "maxResults": 1},
            headers={"Authorization": f"Bearer {tok}"}, timeout=15,
        ).json()
        ok = bool(r.get("messages"))
        return ok, ("Morning Brief email: today's brief was delivered" if ok
                    else "Morning Brief email: NOT delivered yet — the cloud routine may have failed; check claude.ai/code")
    except Exception as e:
        return False, f"Morning Brief email: couldn't check Gmail ({e})"


def unreviewed_scripts() -> list[str]:
    """scripts/*.py modified since the newest Codex review report."""
    reviews = list((REPO / ".codex-review").glob("*.md"))
    last = max((p.stat().st_mtime for p in reviews), default=0)
    return sorted(
        p.name for p in (REPO / "scripts").glob("*.py") if p.stat().st_mtime > last
    )


def check_backup_fresh() -> tuple[bool, str]:
    """RED when the hourly autosave hasn't reached GitHub. The job exits 0
    whether or not its push lands, so the launchd check above calls it clean
    either way. Bit us 2026-08-05: the mini cutover left the machine with no
    GitHub credentials, every push failed silently, and the off-machine backup
    sat 23h stale behind a GREEN light. Judge the outcome instead — the job
    logs one line per run, and a push that landed leaves the branch level with
    its remote."""
    age = _age_minutes(AUTOCOMMIT_LOG)
    if age is None:
        return False, ("Git backup: no auto-commit log — the hourly job has never run here; "
                       "check `launchctl list | grep autocommit`")
    if age > 130:  # hourly job; allow two misses before complaining
        return False, (f"Git backup: job silent for {age/60:.0f}h — expected a log line every hour; "
                       "check logs/auto-commit.log")

    def _git(*a) -> str:
        return subprocess.run(["git", "-C", str(REPO), *a],
                              capture_output=True, text=True, timeout=15).stdout.strip()

    try:
        local = _git("rev-parse", "-q", "--verify", "refs/heads/autosave")
        if not local:
            return True, "Git backup: job running, no autosave branch yet (nothing changed since install)"
        remote = _git("rev-parse", "-q", "--verify", "refs/remotes/origin/autosave")
        if local != remote:
            n = _git("rev-list", "--count", f"{remote}..{local}") if remote else "?"
            return False, (f"Git backup: {n} autosave commit(s) NOT on GitHub — pushes are failing, so the "
                           "off-machine backup is stale; check `gh auth status`, then `git push origin autosave`")
        return True, f"Git backup: on GitHub, last autosave {_git('log', '-1', '--format=%cr', 'refs/heads/autosave')}"
    except Exception as e:
        # Same fail-closed rule as check_desk_code_fresh: an unguarded git call
        # that hangs or errors would abort every check after this one, and the
        # point of this check is that a backup problem must not read as healthy.
        return False, f"Git backup: check FAILED ({e}) — treat as unknown, not healthy"


def check_db() -> tuple[bool, str]:
    try:
        con = sqlite3.connect(DB, timeout=5)
        try:
            n = con.execute("select count(*) from sqlite_master").fetchone()[0]
        finally:
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
    if (stale_cal := check_holiday_calendar()):
        checks.append(stale_cal)
    checks.append(check_desk_code_fresh())
    checks.append(check_morning_brief())
    checks.append(check_backup_fresh())
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

    # Cadence nudges. Long form prints to the report; short form rides on the
    # ntfy push — the nudge is worthless if it only ever lands in a log file.
    nudge = ""
    if today.weekday() == 0:
        nudge = "MONDAY: run /lets-get-to-work"
        print("\n  MONDAY: War Room digest is in your inbox — run /lets-get-to-work for the decision half.")
    elif today.weekday() == 4:
        nudge = "FRIDAY: run /q3-scoreboard"
        print("\n  FRIDAY: run /q3-scoreboard.")

    n_ok = len(checks) - len(reds)
    summary = (f"All {n_ok} systems green" if not reds
               else f"{len(reds)} RED — " + "; ".join(r.split(":")[0] for r in reds))
    if new_deals:
        summary += f" · {len(new_deals)} new deal folder(s)"
    if stale:
        summary += f" · {len(stale)} unreviewed script(s)"
    if nudge:
        summary += f" · {nudge}"
    print(f"\n  SUMMARY: {summary}")

    if args.notify:
        try:
            subprocess.run(["/bin/sh", str(REPO / "scripts" / "notify.sh"), "Heartbeat", summary], timeout=30)
        except Exception as e:
            print(f"  notify failed: {e}")


if __name__ == "__main__":
    main()
