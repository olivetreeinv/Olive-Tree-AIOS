---
type: skill
name: daily-brief
trigger: /daily-brief
status: active
---

## What it does
Morning intelligence pull. Reads Gmail, Google Calendar, and Q3 priorities. Surfaces the day's schedule, deal and investor emails from the last 24 hours, a Q3 pulse, and one #1 action — then drafts the artifact that executes it, ready to review and send.

## Trigger phrases
- `/daily-brief`
- "daily brief"
- "morning brief"
- "what's on my plate"
- "what do I have today"
- "brief me"
- "run my brief"

## What it reads
| Source | What |
|---|---|
| Google Calendar MCP | Today's events |
| Gmail MCP | Unread + starred threads, last 24h |
| `context/priorities.md` | Q3 goals |
| `context/about-me.md` | Role, top pain |
| `connections.md` | Live vs. pending tools |
| `decisions/log.md` | Last 3 decisions |
| `references/voice.md` | Brian's voice for draft output |
| `logs/auto-commit.log` | Last AIOS auto-commit status |

## Output
- Today's calendar rundown
- Deal + investor email highlights
- Q3 priority pulse (on track / at risk)
- #1 action for the day
- One ready-to-send draft artifact (email, follow-up, etc.)

## Notes
- Best run 7–9 AM before any outreach or underwriting.
- Also runs as optional Phase 0 of [[skills/lets-get-to-work]].
- GoHighLevel CRM section auto-inserts when `scripts/ghl_pipeline.py` exists — skip silently until then.
- Gmail and Google Calendar MCPs must be connected.
