---
name: heartbeat
description: One-shot ops health check for every AIOS system — launchd jobs, trading desk, Morning Brief delivery, olive.db, new deal-doc drops, and top loose ends. Trigger on "/heartbeat", "is everything running", "is the trading desk running", "did the brief send", "status check", "are my systems up".
---

## What this skill does

Answers "is everything running?" in one command instead of Brian asking system
by system. Runs every weekday at 7:45am via launchd (`com.olivetree.heartbeat`)
and pushes the summary to Brian's phone via ntfy.

## How to run

```bash
.venv/bin/python scripts/heartbeat.py            # print full report
.venv/bin/python scripts/heartbeat.py --notify   # + ntfy push (what the 7:45am job does)
```

## What it checks

| System | Green means |
|---|---|
| launchd jobs (trading-desk, morning-deal-scan, aios-autocommit, heartbeat, usage-audit, goal-watch, drip) | loaded; KeepAlive jobs have a live PID |
| trading-desk log | written < 75 min ago (loop is cycling) |
| Morning Brief | email with subject "Morning Brief" arrived today (weekdays) |
| olive.db | opens and queries |

Plus: new deal-doc folders in ~/Downloads (via `deal_intake.py`), top 3 loose
ends (via `loose_ends.py`), and a Monday (`/lets-get-to-work`) or Friday
(`/q3-scoreboard`) cadence nudge.

## When Brian asks a status question

Any "is X running / did Y send / why no texts" question → run
`.venv/bin/python scripts/heartbeat.py` FIRST, then answer from its output. If something
is RED, diagnose that system specifically (trading desk → check
`~/Library/Logs/trading-desk.log` tail; brief missing → check the cloud routine).

## Maintenance

- New always-on system? Add its label to `EXPECTED_JOBS` in `scripts/heartbeat.py`.
- Log: `logs/heartbeat.log`. Reload job: `launchctl unload && launchctl load ~/Library/LaunchAgents/com.olivetree.heartbeat.plist`.
