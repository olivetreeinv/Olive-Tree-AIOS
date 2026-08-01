---
name: deal-intake
description: Scans ~/Downloads for new deal-document drops (OM, T-12, Rent Roll) and prints the ready-to-paste workup command for each. Trigger on "/deal-intake", "any new deals in downloads", "scan my downloads", "what deals came in".
---

## What this skill does

Every workup starts with Brian typing "Lets workup <address> — docs are in
~/Downloads/...". This skill removes that step: it finds folders in ~/Downloads
(modified in the last 21 days) containing OM/T-12/Rent-Roll-looking files and
prints the exact workup command for each. New candidates also surface in the
morning `/heartbeat`.

## How to run

```bash
python3 scripts/deal_intake.py           # new (unseen) candidates
python3 scripts/deal_intake.py --all     # include already-worked ones
python3 scripts/deal_intake.py --ack     # mark current candidates as seen
```

## Workflow

1. Run the scan, show candidates.
2. For each, offer to start the workup (the printed command feeds
   `/deal-analysis` / the workup routine — buy-box check first, as always).
3. After a workup starts, run `--ack` so the folder stops showing as new.

Seen-list lives in `data/deal_intake_seen.json`.
