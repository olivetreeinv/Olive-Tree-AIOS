#!/usr/bin/env python3
"""
loose_ends.py — harvest every pending/blocked/deferred item from the decisions
log and memory into one list, so unfinished steps stop rotting silently.

Usage:
  python3 scripts/loose_ends.py               # full list, grouped by source
  python3 scripts/loose_ends.py --top 3       # N most recent, one line each
  python3 scripts/loose_ends.py --days 90     # widen the decisions-log window
  python3 scripts/loose_ends.py --done "GOOGLE_* env vars"   # suppress a resolved item
"""

import argparse
import re
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
DECISIONS = REPO / "decisions" / "log.md"
MEMORY_DIR = Path.home() / ".claude/projects/-Users-olivetree-Documents-Olive-AIOS/memory"
DONE_FILE = REPO / "data" / "loose_ends_done.txt"

PATTERN = re.compile(
    r"pending|todo|blocked|unblocked|remaining (manual )?step|open question"
    r"|open follow|deferred|one step left|still needs?|not yet|needs manual",
    re.IGNORECASE,
)
# Lines that match PATTERN but are prose about the past, not an open item.
NOISE = re.compile(r"^\*\*(why|alternatives|decision|owner)", re.IGNORECASE)


def _suppressed() -> list[str]:
    if not DONE_FILE.exists():
        return []
    return [l.strip().lower() for l in DONE_FILE.read_text().splitlines() if l.strip()]


def _is_done(line: str, done: list[str]) -> bool:
    low = line.lower()
    return any(d in low for d in done)


def harvest(days: int = 60) -> list[tuple[str, str, str]]:
    """Returns [(iso_date, source_label, line)] newest first."""
    done = _suppressed()
    items: list[tuple[str, str, str]] = []
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Decisions log: entries are "## YYYY-MM-DD — Title"
    if DECISIONS.exists():
        entry_date, entry_title = "", ""
        for line in DECISIONS.read_text().splitlines():
            m = re.match(r"^## (\d{4}-\d{2}-\d{2}) — (.+)", line)
            if m:
                entry_date, entry_title = m.group(1), m.group(2)
                continue
            if not entry_date or entry_date < cutoff:
                continue
            s = line.strip().lstrip("-* ").strip()
            if s and PATTERN.search(s) and not NOISE.match(line.strip()) and not _is_done(s, done):
                items.append((entry_date, f"decisions: {entry_title[:50]}", s[:160]))

    # Memory files: any matching line; dated by file mtime
    if MEMORY_DIR.exists():
        for f in sorted(MEMORY_DIR.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            mdate = date.fromtimestamp(f.stat().st_mtime).isoformat()
            for line in f.read_text().splitlines():
                s = line.strip().lstrip("-* ").strip()
                if s.startswith(("---", "name:", "description:", "metadata", "type:")):
                    continue
                if s and PATTERN.search(s) and not _is_done(s, done):
                    items.append((mdate, f"memory: {f.stem}", s[:160]))

    # Dedupe identical lines, newest first
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x[0], reverse=True):
        key = it[2].lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0, help="print only the N most recent")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--done", help="mark an item resolved (substring match, appended to data/loose_ends_done.txt)")
    args = ap.parse_args()

    if args.done:
        DONE_FILE.parent.mkdir(exist_ok=True)
        with DONE_FILE.open("a") as fh:
            fh.write(args.done.strip() + "\n")
        print(f"Suppressed: {args.done!r}")
        return

    items = harvest(days=args.days)
    if not items:
        print("No loose ends found. Clean.")
        return

    if args.top:
        for d, src, line in items[: args.top]:
            print(f"[{d}] ({src}) {line}")
        return

    print(f"LOOSE ENDS — {len(items)} open items (last {args.days} days)\n")
    cur = None
    for d, src, line in items:
        if src != cur:
            cur = src
            print(f"\n{src}  [{d}]")
        print(f"  - {line}")
    print('\nResolve one? python3 scripts/loose_ends.py --done "<substring>"')


if __name__ == "__main__":
    main()
