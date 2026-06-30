---
type: skill
name: onboard
trigger: /onboard
status: active
---

## What it does
Single combined wizard: runs the 7-question intake interview AND scaffolds the Day-1 file set. Idempotent — safe to re-run any time after editing `aios-intake.md`.

## Trigger phrases
- `/onboard`
- "set me up"
- "onboard me"
- "let's get started"
- "fill in my AIOS"

## 7 intake questions
| # | Topic |
|---|---|
| Q1 | Who are you, what do you sell, who do you sell it to? |
| Q2 | Paste 1–2 things you've written recently (raw — no editing) |
| Q3 | What are your top 3 goals this quarter? |
| Q4 | What's your biggest pain / time drain right now? |
| Q5 | What tools do you use daily? |
| Q6 | Who do you communicate with most? |
| Q7 | What does success look like in 90 days? |

## What it reads / writes
- `aios-intake.md` — reads to check which questions are answered; writes each answer as it's given
- `context/about-me.md`, `context/about-business.md`, `context/priorities.md` — scaffolded at the end
- `references/voice.md` — built from Q2 voice samples
- `connections.md` — scaffolded from Q5

## Notes
- Q2 has a hard rule: voice samples must be **pasted raw**, not typed fresh mid-conversation. If user starts typing new prose, refuse and ask them to paste from a real sent email or post.
- Already run for Brian — re-run if `aios-intake.md` is updated.
- Wow moment: at the end, suggest *"Try this — ask me: what should I focus on this week?"*
