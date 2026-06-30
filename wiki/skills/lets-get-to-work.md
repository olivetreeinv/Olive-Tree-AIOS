---
type: skill
name: lets-get-to-work
trigger: /lets-get-to-work
status: active
---

## What it does
Orchestrates Brian's full multifamily acquisition pipeline in one guided session. Calls sub-skills at each phase. Nothing sends without approval — every email, follow-up, and LOI is a draft shown first.

## Trigger phrases
- `/lets-get-to-work`
- "lets get to work"
- "run the pipeline"
- "deal sourcing session"
- "monday run"

## Pipeline phases
| Phase | What happens | Sub-skill |
|---|---|---|
| 0 | Morning brief (optional) | [[skills/daily-brief]] |
| 1 | Scan new listings from alert emails | [[skills/broker-search]] |
| 2 | Broker follow-ups (7-day cadence) | — |
| 3 | Inbound deal email triage | — |
| 4 | Document requests for incomplete deals | — |
| 5 | Deal analysis on ready deals | [[skills/deal-analysis]] |
| 6 | LOI draft for PURSUE verdicts | — |

## What it reads
| File | Why |
|---|---|
| `references/buy-box.md` | Filter every deal before spending time |
| `references/knowledge-base-metrics.md` | Deal thresholds, Stage 4 cadence |
| `references/knowledge-base-process.md` | 10-stage pipeline |
| `references/voice.md` | All drafted emails must match Brian's tone |
| `references/google-workspace-api.md` | Gmail + Sheets API |
| `templates/loi-fields.json` | LOI fields, defaults, formulas, Doc token map |
| `templates/loi-template.md` | LOI in-chat preview body |

## Output
- New listings filtered to buy box
- Broker follow-up drafts (awaiting approval)
- Deal analysis verdicts
- LOI drafts (awaiting approval)

## Notes
- Cadence: every Monday morning. Standard scan covers prior 7 days.
- Nothing sends without Brian's approval.
- Gmail MCP must be connected.
