#!/usr/bin/env python3
"""
usage_audit.py — mine Claude Code session transcripts for the monthly usage
audit: what got worked on, what got asked repeatedly, where the friction is.

Data extraction only — /usage-audit (the skill) does the synthesis.

Usage:
  python3 scripts/usage_audit.py               # last 31 days, human-readable
  python3 scripts/usage_audit.py --days 62
  python3 scripts/usage_audit.py --sessions    # also list one line per session
"""

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

SESSIONS_DIR = Path.home() / ".claude/projects/-Users-olivetree-Documents-Olive-AIOS"
DECISIONS = Path(__file__).parent.parent / "decisions" / "log.md"

TOPICS = {
    "deal workup / underwriting": r"work ?up|lets get to work on|deal analysis|underwrit|\bloi\b",
    "capital raise / investors": r"capital raise|investor|soft commit|drip|enroll",
    "broker pipeline": r"broker",
    "trading desk": r"trad(er|ing) desk|alpaca|polygon|covered call",
    "land wholesale": r"\bland\b|parcel|builder|seller list|reportall",
    "govcon": r"govcon|sam\.gov|\bbids?\b",
    "social media / marketing": r"social media|instagram|carousel|metricool|newsletter|canva|marketing",
    "ops / routines / heartbeat": r"daily brief|routine|schedule|heartbeat|launchd|cron",
    "status-check questions": r"^(is|has|are|did|why did|why is|what is the status|whats the status|didn'?t)",
}


def mine(days: int):
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    sessions, msgs = [], []
    for f in SESSIONS_DIR.glob("*.jsonl"):
        first, count = None, 0
        try:
            with f.open() as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "user":
                        continue
                    c = d.get("message", {}).get("content")
                    if isinstance(c, str):
                        txt = c
                    elif isinstance(c, list):
                        txt = " ".join(x.get("text", "") for x in c
                                       if isinstance(x, dict) and x.get("type") == "text")
                    else:
                        continue
                    txt = txt.strip()
                    if not txt or txt.startswith(("<", "Caveat:", "[Request interrupted", "Base directory")):
                        continue
                    ts = d.get("timestamp", "")[:10]
                    if ts < cutoff:
                        continue
                    if first is None:
                        first = (ts, txt[:120])
                    count += 1
                    msgs.append((ts, txt))
        except OSError:
            continue
        if first:
            sessions.append((first[0], count, first[1]))

    topic_counts = Counter()
    for _, t in msgs:
        tl = t.lower()
        for name, pat in TOPICS.items():
            if re.search(pat, tl):
                topic_counts[name] += 1

    decision_count = 0
    if DECISIONS.exists():
        for line in DECISIONS.read_text().splitlines():
            m = re.match(r"^## (\d{4}-\d{2}-\d{2}) ", line)
            if m and m.group(1) >= cutoff:
                decision_count += 1

    return sorted(sessions), msgs, topic_counts, decision_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=31)
    ap.add_argument("--sessions", action="store_true", help="list one line per session")
    args = ap.parse_args()

    sessions, msgs, topics, decisions = mine(args.days)

    print(f"USAGE AUDIT DATA — last {args.days} days\n")
    print(f"  Sessions: {len(sessions)}   User messages: {len(msgs)}   Decisions logged: {decisions}")
    if sessions:
        per_week = len(sessions) / (args.days / 7)
        print(f"  Pace: {per_week:.1f} sessions/week")
    print("\n  TOPIC MIX (messages matching each theme):")
    for name, n in topics.most_common():
        print(f"    {n:4d}  {name}")
    if args.sessions:
        print("\n  SESSIONS (date, #msgs, first prompt):")
        for dt, n, first in sessions:
            print(f"    {dt} [{n:3d}] {first}")


if __name__ == "__main__":
    main()
