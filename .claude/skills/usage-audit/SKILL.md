---
name: usage-audit
description: Monthly retro on how Brian actually uses the AIOS — session mining (what's right/wrong vs the quarter's goals) plus a scan of Claude's latest releases for features worth adopting. Trigger on "/usage-audit", "usage audit", "monthly audit", "how am I using this", "what am I not using". Replaces the retired /audit skill; runs automatically on the 1st of each month.
---

## What this skill does

The monthly version of the 2026-07-06 session-history review that produced the
ops-cadence layer and the Sonnet 5 upgrades. Two halves:

1. **Usage retro** — mine the past month's sessions: where did the time go,
   which skills ran vs. sat idle, did the cadence rituals happen, are
   status-check questions creeping back?
2. **Platform scan** — what did Anthropic ship in the past month that this
   setup isn't using?

Output: one email to Brian with a verdict and max 3 recommended changes.

## How to run

### Step 1 — mine the month
```bash
python3 scripts/usage_audit.py --days 31 --sessions
python3 scripts/loose_ends.py --top 5
```
Read the decisions-log entries from the past month for what shipped.

### Step 2 — judge against the quarter's goals
Read the current quarter's goals in `CLAUDE.md`. Answer plainly:
- Is the topic mix pointed at the goals, or at side books? Name the skew.
- Cadence check: did /lets-get-to-work run ~weekly? /q3-scoreboard on Fridays?
  Is heartbeat still green (status-question count should stay near zero)?
- Which skills got zero use this month? Candidates to archive (move to
  `archives/skills/`, never delete).
- What manual pattern appeared 3+ times that deserves a new skill/automation?

### Step 3 — scan Claude updates (past month)
- `claude --version` vs latest; WebFetch
  `https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md`
  for the last month's entries.
- WebSearch "Anthropic Claude Code new features <month> <year>".
- Map each relevant new capability to a concrete spot in this setup (cloud
  routines, hooks, agents, scripts calling the API). Ignore features with no
  landing spot. Flag costs per the cost-transparency rule.

### Step 4 — deliver
Compose the report (Brian's voice, numbers up front, ≤1 page):
`VERDICT` → `TIME MIX` vs goals → `CADENCE` → `NOT USING` (new features mapped
to setup) → `TOP 3 CHANGES` for next month, each sized (5-min / 1-session / big).

Email it:
```bash
# write report to /tmp/usage_audit.txt, then send via Gmail (gws keyring auth)
python3 scripts/daily_brief_cloud.py send --to brian@olivetreeinv.io \
  --subject "Monthly Usage Audit — $(date '+%b %Y')" --body-file /tmp/usage_audit.txt
```
(Local runs can fall back to `_google_token()`-style gws auth if GOOGLE_* env
vars are empty — see `scripts/heartbeat.py`.)
Then ntfy: `sh scripts/notify.sh "Usage Audit" "Monthly audit emailed — <verdict one-liner>"`

## Cadence

Scheduled for the 1st of every month at 9am ET (local cron). Manual any time
with `/usage-audit`. If the scheduled run lands while the laptop is off, run it
manually — heartbeat's loose-ends will not track this, so the email itself is
the receipt.
