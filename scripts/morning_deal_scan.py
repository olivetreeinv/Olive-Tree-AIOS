#!/usr/bin/env python3
"""
Olive Tree Investments — Morning Deal Scan (local, unattended)

Runs the deterministic slice of the broker/deal pipeline before Brian is at his
desk, then pushes one ntfy/banner summary. Local-only: Crexi + broker sites 403
cloud IPs, so this must run on the Mac (launchd), never as a cloud routine.

What it does (all deterministic — no LLM, no browser):
  1. crexi_live --deals (GA): full Crexi MF inventory screened vs buy box, with
     the analyzed-deals cross-check (skips deals already in the Drive folder).
  2. broker_replies (last 1 day): overnight broker email — deals / contact
     updates / replies needing Brian.
  3. broker_sites curl fetch: stages the server-rendered broker pages to
     output/broker-sites/<date>/ so the interactive @browser sweep is one step.

What it does NOT do: extract/screen the fetched broker-site HTML (that needs an
LLM pass) or the JS-app sites (need @browser). The summary flags those as a
ready-to-run interactive step.

Usage:
  python3 scripts/morning_deal_scan.py            # run + push notification
  python3 scripts/morning_deal_scan.py --no-notify # print only
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gws_auth import get_token

REPO = Path(__file__).parent.parent
STATE = "GA"


def scan_crexi_deals():
    from crexi_live import (load_payload, search_assets, screen_deals)
    from analyzed_deals import load_analyzed, match_analyzed
    assets = search_assets(load_payload(STATE), STATE)
    matches, near = screen_deals(assets)
    analyzed = load_analyzed(get_token())
    fresh = []
    for e in matches:
        hit, strength = match_analyzed(e["city_state"], e["name"], analyzed)
        if strength != "address":            # skip only exact already-analyzed
            fresh.append(e)
    return fresh, len(matches), len(near)


def scan_replies():
    from broker_replies import scan
    findings = scan(get_token(), days=1)
    deals = [f for f in findings if f["is_deal"]]
    contacts = [f for f in findings if f["new_phone"] or f["new_email"]]
    replies = [f for f in findings if not f["is_deal"] and not f["auto_reply"]
               and f not in contacts]
    return deals, contacts, replies


def stage_broker_sites():
    """Fetch server-rendered broker pages (curl) for the later @browser sweep."""
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "broker_sites.py"), "--curl-only"],
        capture_output=True, text=True, cwd=str(REPO), timeout=600)
    fetched = js = 0
    for line in r.stdout.splitlines():
        if "fetched →" in line:
            parts = line.split()
            fetched = int(parts[0]);
            if "JS-app skipped" in line:
                js = int(line.split("|")[-1].strip().split()[0])
    return fetched, js


def build_summary(crexi, replies, sites):
    fresh, n_match, n_near = crexi
    deals, contacts, reps = replies
    fetched, js = sites
    lines = ["🌅 Morning Deal Scan\n"]

    if fresh:
        lines.append(f"🎯 {len(fresh)} NEW buy-box match(es) on Crexi:")
        for e in fresh[:5]:
            p = f"${e['price']:,.0f}" if e["price"] else "unpriced"
            lines.append(f"  • {e['name']} — {e['market']} | {e['units'] or '?'}u | {p}")
    else:
        lines.append(f"Crexi: 0 new buy-box matches ({n_near} near-miss listings in-market).")

    if deals:
        lines.append(f"\n📦 {len(deals)} broker deal email(s) overnight:")
        for f in deals[:4]:
            lines.append(f"  • {f['broker']['name']}: \"{f['subject'][:50]}\"")
    if contacts:
        lines.append(f"\n📞 {len(contacts)} broker contact update(s) — run broker_replies --apply.")
    if reps:
        lines.append(f"💬 {len(reps)} broker repl(y/ies) to read.")

    lines.append(f"\n🖥️  {fetched} broker site(s) staged; {js} JS-app site(s) need the "
                 f"@browser sweep — open Claude Code + @browser and say "
                 f"'run the broker-site browser sweep'.")
    return "\n".join(lines)


def _safe(fn, fallback, label, errors):
    """Run a scan; on failure record the error and return a fallback so one
    broken sub-scan doesn't kill the whole unattended job (and its notification)."""
    try:
        return fn()
    except Exception as e:  # unattended: never crash before notifying
        errors.append(f"{label}: {type(e).__name__}: {str(e)[:80]}")
        return fallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args()

    errors = []
    crexi = _safe(scan_crexi_deals, ([], 0, 0), "crexi", errors)
    replies = _safe(scan_replies, ([], [], []), "replies", errors)
    sites = _safe(stage_broker_sites, (0, 0), "broker-sites", errors)
    summary = build_summary(crexi, replies, sites)
    if errors:
        summary += "\n\n⚠️ scan errors: " + "; ".join(errors)
    print(summary)

    if not args.no_notify:
        subprocess.run(["/bin/sh", str(REPO / "scripts" / "notify.sh"),
                        "Morning Deal Scan", summary], timeout=30)


if __name__ == "__main__":
    main()
