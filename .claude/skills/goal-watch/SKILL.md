---
name: goal-watch
description: Midday goal-aware monitor — judges whether each routine/skill is meeting its GOAL, not just running. Trigger on "/goal-watch", "are we on goal", "is everything on track", "how are my routines doing", "audit the skills".
---

## What this skill does

Heartbeat answers "is it running?". Goal Watch answers the harder question:
"is it doing what it's supposed to?" It reads a registry of goals
(`references/goal-registry.json`), gathers evidence for each target, mines
the last 24h of skill/command runs from session transcripts, and makes ONE
`claude -p` judge call to grade every target ON GOAL / OFF GOAL / NO DATA
with a one-line fix. Pushes to Brian's phone via ntfy only when something is
OFF GOAL. Runs weekdays at 12:30pm via launchd (`com.olivetree.goal-watch`).

## How to run

```bash
.venv/bin/python scripts/goal_watch.py                    # judge + print, no push (default)
.venv/bin/python scripts/goal_watch.py --dry               # print the judge prompt only, no claude call
.venv/bin/python scripts/goal_watch.py --target drip        # judge just one target
.venv/bin/python scripts/goal_watch.py --notify             # what the 12:30pm job runs
```

## What it judges

| Target | Kind | Goal (short) |
|---|---|---|
| trading-desk | launchd | Paper-trading loop alive and cycling |
| morning-deal-scan | launchd | Weekdays 8am buy-box scan + broker replies |
| heartbeat | launchd | Weekdays 7:45am ops report + ntfy push |
| aios-autocommit | launchd | Daily 9pm git backup commit |
| usage-audit | launchd | Monthly (1st, 9:05am) usage report email |
| drip | launchd | Daily 9am drip-campaign send |
| morning-brief | artifact | 8am cloud routine, Morning Brief email every weekday |
| weekly-cloud-sync | artifact | Friday cloud routines (loom-sync/pitch-deck-archive/deal-index) land wiki + commits |
| trading-desk-pace | pace | Covered-call premium ≥ $1,000/week pace, no halt flag |
| capital-raise-pace | pace | $400K soft LP commitments by end of Q3 2026 |
| drip-flow | pace | Drip worker sends due emails without errors |

Plus: every Skill/slash-command run in the last 24h (mined from session
transcripts), matched to its `SKILL.md` description, feeds the judge for the
IMPROVEMENTS section — up to 3 concrete suggestions, best first.

## Workflow when Brian runs it

1. Run `.venv/bin/python scripts/goal_watch.py`.
2. Show the verdict table — lead with any OFF GOAL rows and their fix.
3. Surface the top improvement suggestions.
4. Offer to implement any fix directly (edit the script, reload the launchd
   job, whatever the fix line names).

## Maintenance

- Add or disable a target by editing `references/goal-registry.json` — no
  code change needed for a new evidence-only target.
- launchd job: `com.olivetree.goal-watch`, weekdays 12:30pm. Log:
  `~/Library/Logs/goal-watch.log`. Reload:
  `launchctl unload ~/Library/LaunchAgents/com.olivetree.goal-watch.plist && launchctl load ~/Library/LaunchAgents/com.olivetree.goal-watch.plist`.
- Daily report: `output/goal-watch/YYYY-MM-DD.md`.
