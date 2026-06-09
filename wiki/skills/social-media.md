---
type: skill
name: social-media
trigger: /social-media
status: active
---

## What it does
Daily Instagram content engine. Generates 2 posts per day (multifamily + single family), each in two formats (carousel + video post). Full pipeline: ideation → Canva design → Instagram publish.

## Trigger phrases
- `/social-media`
- "social media ideas"
- "create instagram posts"
- "daily posts"
- "what should I post today"
- "create social content"

## Post structure
| Post | Audience | Formats |
|---|---|---|
| Post 1 | Multifamily investors + operators | Carousel + Video/Reel |
| Post 2 | Single family / retail homebuyers | Carousel + Video/Reel |

## What it reads
| File | Why |
|---|---|
| `references/social-media-examples.md` | **Read first.** Brian's real hook formulas, voice patterns, topic pillars from 12 published newsletters |
| `references/news-research.md` | Source stack, rate tables, macro event framework |
| `references/voice.md` | Brian's tone |
| `references/higgsfield-cli.md` | Higgsfield CLI for AI video/image generation |
| `references/canva-api.md` | Canva Connect API |
| `references/meta-api.md` | Meta Graph API (Instagram publishing) |
| `references/gohighlevel-api.md` | GHL Social Planner (scheduling) |
| `context/about-me.md` | Brian's identity |
| `context/about-business.md` | Olive Tree structure and markets |

## Output
- 2 post briefs (carousel + video for each)
- Canva designs (via `scripts/canva_api.py`)
- Scheduled or drafted in GHL Social Planner (or Meta Graph API as fallback)

## Notes
- Higgsfield: authenticated as brian@olivetreeinv.io. Binary: `higgsfield`. Free plan — `nano_banana_2` = 2 credits/image.
- GHL draft API working; send not yet available — 3 test drafts require manual GHL cleanup.
- Read `references/social-media-examples.md` first, every time — hooks and voice patterns must match Brian's published content.
