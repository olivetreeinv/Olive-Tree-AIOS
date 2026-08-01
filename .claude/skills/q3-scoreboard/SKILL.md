---
name: q3-scoreboard
description: Friday scorecard measuring the week against the three Q3 2026 goals — deal under contract, $400K soft LP commitments, 3+ broker-sourced deals. Trigger on "/q3-scoreboard", "how am I tracking", "q3 scorecard", "weekly scorecard", "am I on track this quarter".
---

## What this skill does

Scores the week against the three Q3 goals, in numbers, every Friday. Its job
is to catch drift early — the pattern where build-projects (trading desk, land,
govcon) quietly eat the week while the multifamily goals stall.

## The three goals (from CLAUDE.md)

1. One 15–50 door apartment **under contract**
2. **$400K+** in soft LP commitments
3. **3+ apartments** actively coming in from broker relationships

## How to build the scorecard

Gather (run in parallel where possible):

1. **Goal 1 — deal pipeline:**
   - LOIs out / countered / accepted → scan `decisions/log.md` entries this
     quarter for "LOI Submitted" + any responses; cross-check the LOI tracking
     sheet (`/loi-archive` sheet) if needed.
   - Deals worked up this week → `python3 scripts/deal_intake.py --all` +
     this week's decisions-log entries.
2. **Goal 2 — capital:** `python3 scripts/capital_raise.py track` → running
   soft-commit total vs $400K. If GHL is unreachable, say so — don't guess.
3. **Goal 3 — broker flow:** count inbound deals from brokers this week
   (`python3 scripts/deal_inbox.py` scan or Gmail deal bucket) and active
   broker conversations (Brokers List sheet, status ≠ dormant).
4. **Loose ends:** `python3 scripts/loose_ends.py --top 3`.

## Output format

```
Q3 SCOREBOARD — week of <date>   (X weeks left in Q3)

GOAL                         TARGET      NOW        THIS WEEK
Deal under contract          1           0          LOIs out: N (+n) · workups: n
Soft LP commitments          $400K       $XXX,XXX   +$XX,XXX
Broker deal flow             3+ active   N          new inbound: n

VERDICT: <one sentence — on track / behind, and the single constraint>
#1 ACTION NEXT WEEK: <the one move that most advances the weakest goal>
LOOSE ENDS: <top 3, one line each>
```

Close with a straight time-allocation note if the week's work visibly skewed
away from the goals (e.g. "4 sessions on trading desk, 0 on capital raise —
flip that next week"). Direct, no hedging — that's the point of the scorecard.

## Cadence

Fridays. The morning `/heartbeat` nudges it. If a Friday is missed, run it
Monday before `/lets-get-to-work`.
