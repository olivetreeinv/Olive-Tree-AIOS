---
type: skill
name: deal-analysis
trigger: /deal-analysis
status: active
---

## What it does
Reads deal documents (OM, T-12, Rent Roll), extracts key inputs, calculates hard underwriting metrics, and compares against Olive Tree's thresholds. Outputs a traffic-light verdict with full financials, a letter-grade scorecard, callouts, and area photos.

## Trigger phrases
- `/deal-analysis`
- "analyze this deal"
- "run the numbers on"
- "underwrite this"
- "does this deal work"

## What it reads
| File | Why |
|---|---|
| `references/buy-box.md` | Price/unit targets, hold period |
| `references/knowledge-base-metrics.md` | Hard thresholds: IRR, CoC, DSCR, 75% rule, 1% rule |
| `references/google-workspace-api.md` | Drive API for doc retrieval |

## Inputs required
**Minimum:** asking price, units, current rents, zip code.
**Full analysis:** T-12, Rent Roll, OM.

## Output format
1. Quick Verdict — `PURSUE LOI` / `MORE INFO NEEDED` / `PASS`
2. Full financials table (NOI, cap rate, IRR, CoC, DSCR, equity multiple)
3. Letter-grade Scorecard (A–F per metric)
4. Callouts (risks, assumptions)
5. Area + community photos (via `scripts/deal_photos.py` — Wikipedia, no API key)

## Notes
- If documents are missing, outputs a draft email requesting them and stops. Brian approves before anything sends.
- Uses `scripts/deal_analysis.py` + `scripts/deal_photos.py`.
- Called by [[skills/lets-get-to-work]] Phase 4.
- Run [[skills/market-research]] first — a bad market kills a deal faster than bad numbers.
