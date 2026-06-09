---
type: skill
name: pitch-deck
trigger: /pitch-deck
status: active
---

## What it does
Builds a deal-specific LP pitch deck in Canva. Copies the master Olive Tree template, outputs a slide-by-slide content brief, and exports PDF on demand.

## Trigger phrases
- `/pitch-deck [deal name]`
- "pitch deck"
- "create a pitch deck"
- "build a pitch deck"
- "investor deck"
- "LP deck"

## Canva template
| Item | Value |
|---|---|
| Template design ID | `DAHHfpHE2Es` |
| Reference deck (641 Powder Springs) | `DAHIppfBwgs` |
| Dimensions | 1920×1080 (16:9) |
| Pages | 60 |

## What it reads
| File | Why |
|---|---|
| `references/canva-api.md` | Canva Connect API endpoints |
| `references/buy-box.md` | Market context for slides |
| `references/knowledge-base-metrics.md` | Deal metrics for financial slides |
| `scripts/canva_api.py` | API helper |
| `.env` | `CANVA_ACCESS_TOKEN` |

## Output
- New Canva design named for the deal (copy of master template)
- Canva edit URL
- Slide-by-slide content brief (paste-ready)
- Optional PDF export

## Notes
- Run after [[skills/market-research]] returns PURSUE, or when deal reaches Stage 3 (Initial Underwriting).
- Phase 2 (Canva brand template autofill API) not yet implemented — current output is content brief for manual slide population.
- OAuth tokens in `.env`. See `scripts/canva_oauth_setup.py` for token refresh.
