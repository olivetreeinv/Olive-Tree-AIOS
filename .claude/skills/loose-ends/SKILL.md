---
name: loose-ends
description: Harvests every pending, blocked, deferred, or "one step left" item from the decisions log and memory into one actionable list — so unfinished steps stop rotting silently. Trigger on "/loose-ends", "what's still pending", "what did we leave unfinished", "open items", "what's blocked".
---

## What this skill does

Scans `decisions/log.md` (last 60 days) and the memory directory for lines that
signal unfinished work — "remaining manual step", "pending", "next when
unblocked", "deferred", "one step left", "not yet" — dedupes them, and prints
them newest-first. The top 3 also appear in every morning `/heartbeat`.

## How to run

```bash
python3 scripts/loose_ends.py               # full list, grouped by source
python3 scripts/loose_ends.py --top 3       # the 3 most recent, one line each
python3 scripts/loose_ends.py --done "ReportAll quota"   # suppress a resolved item
```

## Workflow when Brian runs it

1. Run the script, show the list.
2. For each item, offer one of: **do it now** (if it's a 5-minute fix Claude can
   execute), **schedule it**, or **mark it done** (`--done "<substring>"`).
3. If an item has appeared 3+ weeks running, flag it: either it matters (do it
   today) or it doesn't (suppress it). No zombie items.

## Notes

- Suppressions live in `data/loose_ends_done.txt` (substring match, one per line).
- False positive that isn't resolvable? Suppress it the same way — the list is
  only useful if every line deserves action.
