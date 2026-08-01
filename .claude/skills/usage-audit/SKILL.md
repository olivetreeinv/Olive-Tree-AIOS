---
name: usage-audit
description: Monthly retro on how Brian actually uses the AIOS — session mining (what's right/wrong vs the quarter's goals), a first-principles pass on the system itself (question the plan, not just execution against it), a scan of Claude's latest releases for features worth adopting, and a scope check on any new automation it recommends. Trigger on "/usage-audit", "usage audit", "monthly audit", "how am I using this", "what am I not using", "what should I automate next". Replaces the retired /audit and /level-up skills; runs automatically on the 1st of each month.
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

### Step 2.5 — first-principles pass on the system itself

Step 2 measures the system against its own plan. This step questions the plan.
Reason from fundamentals, not by analogy ("we've always run it this way" /
"other operators do X" are not reasons):

1. **Name the fundamentals.** What is actually true and non-negotiable this
   quarter? (The goals in `CLAUDE.md`, Brian's hours, dollars, and the binding
   constraint — currently deal sourcing + underwriting.) Everything else is
   an inherited decision, not a truth.
2. **Surface the assumption under each system.** Every skill, cadence, launchd
   job, subscription, and channel exists because of a past decision. For the
   3–5 biggest time/money consumers this month, state the assumption they rest
   on (e.g. "weekly broker digest → assumes broker flow is the bottleneck").
   Ask: is that still true, or did the constraint move?
3. **Zero-base rebuild.** If the AIOS were rebuilt from nothing today, knowing
   only the fundamentals from (1), what would get built first — and what that
   exists now wouldn't make the cut? Anything that wouldn't be rebuilt is a
   candidate to archive; anything the rebuild wants that doesn't exist is a
   candidate for TOP 3 CHANGES.
4. **Cost from raw parts.** For the priciest workflow, estimate what the
   outcome fundamentally requires (API calls, minutes, $) vs. what it
   currently costs. A big gap = redesign candidate, not a tuning candidate.

Cap the output: max 2 findings from this step feed the report. If nothing
fails the pass, say so in one line — don't invent churn.

### Step 2.6 — scope check any new automation

Before a new automation makes TOP 3 CHANGES, it must pass all four filters:

1. **Eliminate first.** *"What happens if Brian just stops doing this?"*
   If nothing breaks, recommend killing the task, not automating it — don't
   automate waste. Delegate to a person only if it's judgment-heavy.
2. **Lowest autonomy that works.** Suggest → draft → supervised → autonomous.
   Default the lowest; push back on autonomous until lower levels ran clean.
3. **Ship boring.** Prompt template → deterministic script → AI-assisted
   skill → sub-agent, in that order. Default the highest non-AI option.
4. **Must move a number.** One bucket (more customers / more value per
   customer / less cost) plus a metric. Can't name both → drop the rec.

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

Email it — the GOOGLE_* vars in `.env` are EMPTY placeholders locally; pull
creds from the gws keyring first (verified working 2026-07-06):
```bash
# write report to /tmp/usage_audit.txt, then:
creds=$(gws auth export --unmasked | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['client_id'], d['client_secret'], d['refresh_token'])")
read -r cid csec crt <<< "$creds"
GOOGLE_CLIENT_ID="$cid" GOOGLE_CLIENT_SECRET="$csec" GOOGLE_REFRESH_TOKEN="$crt" \
  python3 scripts/daily_brief_cloud.py send --to brian@olivetreeinv.io \
  --subject "Monthly Usage Audit — $(date '+%b %Y')" --body-file /tmp/usage_audit.txt
```
Then ntfy: `sh scripts/notify.sh "Usage Audit" "Monthly audit emailed — <verdict one-liner>"`

## Cadence

Scheduled for the 1st of every month at 9am ET (local cron). Manual any time
with `/usage-audit`. If the scheduled run lands while the laptop is off, run it
manually — heartbeat's loose-ends will not track this, so the email itself is
the receipt.
