---
type: skill
name: audit
trigger: /audit
status: active
---

## What it does
Scores the AIOS against the [removed framework] framework (Context, Connections, Capabilities, Cadence) — 25 points each, 100 total. Surfaces the top 3 leverage-weighted gaps with concrete fix commands.

## Trigger phrases
- `/audit`
- "is my AIOS working"
- "audit my setup"
- "find gaps in my AIOS"
- "score my setup against the [removed framework]"

## What it reads
- `CLAUDE.md` — operating manual
- `MEMORY.md` + `memory/` folder
- `.claude/skills/*/SKILL.md` — all skill frontmatter
- `.claude/agents/*.md`
- `.mcp.json` / `settings.json` — connection registry
- `connections.md`
- `context/`, `references/`, `decisions/log.md`

## Output
- [removed framework] scoreboard (0–100)
- Strengths called out
- Top 3 gaps ranked by leverage with exact fix commands

## Notes
- **Scope is structural** — "is the AIOS built right?" Not a capability planner (that's [[skills/level-up]]).
- First run = baseline. Re-run weekly to watch score climb.
- Run `/audit` before `/level-up` if the structure looks messy.
- Cadence: Day 7, then weekly.
