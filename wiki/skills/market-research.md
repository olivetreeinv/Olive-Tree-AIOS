---
type: skill
name: market-research
trigger: /market-research
status: active
---

## What it does
Scores a city, submarket, or zip code on 7 criteria and outputs a one-page go/no-go scorecard with composite score. Phase 1 of 2 in the deal evaluation pipeline — always runs before opening an OM.

## Trigger phrases
- `/market-research [city]`
- "market research [city/zip]"
- "research this market"
- "is [city] a good market for multifamily"
- "should I buy in [city]"

## 7 scoring criteria
Population growth · Job growth · Rent growth (YoY) · Vacancy rate · Cap rate trend · Supply pipeline · Investor demand

## What it reads
| Source | What |
|---|---|
| `references/buy-box.md` | 9 active markets — check before any work |
| `references/knowledge-base-metrics.md` | Market-level thresholds (authoritative) |
| Web sources | Census, CoStar, BLS, Zillow, local market reports |

## Output
- 7-criteria scorecard (score + notes per criterion)
- Composite score (X/10)
- Verdict: `PURSUE` / `INVESTIGATE` / `PASS`
- Underwriting-ready data block (for [[skills/deal-analysis]])

## Notes
- **Run this before opening any OM.** A bad market kills a deal faster than bad numbers.
- If the zip/city isn't in the buy box, flag it to Brian before proceeding.
- Phase 2: [[skills/deal-analysis]] — only run if market returns PURSUE or INVESTIGATE.
- Source framework: `references/market-research-prompt.docx`.
