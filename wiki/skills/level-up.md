---
type: skill
name: level-up
trigger: /level-up
status: retired
---

## What it does
**RETIRED 2026-07-07** — absorbed into [[skills/usage-audit]]: the scope check (eliminate-first, lowest autonomy, ship boring, tie to a KPI) now runs inside the monthly audit's Step 2.5. Skill file archived at `archives/skills/level-up/`.

Was a weekly interview to find and ship one new automation. Retired; only the four scope-check filters survive, inside usage-audit.

## Trigger phrases
- `/level-up`
- "let's level up"
- "what should I automate next"
- "find me leverage this week"

## Three phases
| Phase | M | What happens |
|---|---|---|
| 1 | Mindset | Interview to surface the best automation candidate from the week's manual tasks |
| 2 | Method | Scope the chosen automation — inputs, outputs, constraints, effort |
| 3 | Machine | Build it — script, skill, or hook |

## What it reads
- `context/priorities.md` — what matters
- `context/about-me.md` — top pain, role
- `connections.md` — what's reachable
- `decisions/log.md` — what's already shipped
- `.claude/skills/*/SKILL.md` frontmatter — existing capabilities
- `audits/audit-{date}.md` — recent audit results

## Output
One shipped artifact: a new script, skill, hook, or automation.

## Notes
- **Not `/audit`** — audit is structural, level-up is functional. Run audit first if structure is messy.
- First run: Day 14 (after ≥1 MCP connected and audit run once).
- Cadence: weekly, Friday afternoon. Review the week, surface one automation, ship Monday.
