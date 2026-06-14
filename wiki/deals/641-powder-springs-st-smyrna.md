---
type: deal
name: 641 Powder Springs St
address: 641 Powder Springs Street SE, Smyrna, GA 30080
market: "[[markets/smyrna]]"
broker: "[[brokers/andy-lundsberg]]"
units: 14
asking_price: $1,500,000
basis_per_unit: $107,143
status: dead
last_updated: 2026-06-11
---

> **Training run (2026-06-11):** Full /underwriting session run clean-slate as an underwriter training exercise. Brian previously LOI'd this property in real life (April 2026) — this page records the training-session verdict, not the live deal history.

## Quick Verdict
PASS at the $1.5M ask — the offering memorandum models a full building, but the rent roll shows 8 of 14 units occupied (43% vacant). In the corrected Deal Analyzer (taxes reassessed at the verified Smyrna effective rate of 1.37%, $1,500/unit insurance, padded repairs), the 16% IRR floor clears at **~$940K** — the max defensible offer. Analyzer's offer cell is set there (16.37% IRR; $925K → 17.2%).

## Key Numbers (corrected Deal Analyzer, 2026-06-11)
| Metric | Current (in-place) | Pro Forma (stabilized) |
|---|---|---|
| NOI | negative yr 1 (full expense load on half-empty bldg) | ~$94K |
| Cap Rate | 6.0% entry (est.) | 6.5% exit (est.) |
| IRR | — | 16.4% at $940K · 17.2% at $925K (taxes @ verified 1.37%) |
| DSCR | <1.0x going in (bridge I/O carries it) | ~2.0x at $950K |
| Equity Multiple | — | 1.52x at $950K (sheet incl. yr-3 refi + GP fees) |

*Earlier screen-stage numbers (16.1% IRR at $1.0M) came from `deal_analysis.py` with lighter expenses; the populated Deal Analyzer is authoritative. The gap was template-default taxes ($45K) — fixed to reassessed-at-offer — and the script now writes tax/insurance on every future populate.*

## Assumptions
- Rent upside: classics $1,055–$1,075 → $1,300 renovated (in-building comps $1,265/$1,355; area 1BR median $1,412–$1,540)
- CapEx budget: $200K — $20K/unit × 10 unrenovated units (OM, unverified)
- Vacancy + economic loss: 12% stabilized; actual physical vacancy 43% at takeover
- Property tax: ~$18.6K reassessed at purchase price (OM showed seller's $12.6K) — ESTIMATE
- Insurance: $21K at $1,500/unit KB floor (OM showed $669/unit) — ESTIMATE
- Debt: bridge 6.75%, 70% LTV, 36-mo interest-only (no quote)
- Exit cap: 6.5% · Hold period: 5 years

## Risks
- 43% physical vacancy + 1 tenant 2.5 months delinquent (unit 7, $2,630) — economic occupancy 50%
- 1965 vintage: plumbing stack, electrical panels, roof, basement moisture all unverified
- OM expenses understate taxes (+$6K reassessment) and insurance (+$11.6K to floor) — ~$250K+ of phantom value at broker's cap
- Buy-box strategy mismatch: Smyrna profile wants "stabilized with operational upside"; this is heavy value-add with high vacancy (both listed Smyrna red flags)
- 14 units — below the 15-unit preference; every vacancy swings occupancy ~7%

## Artifacts
- Deal Analyzer: [641 Powder Springs — Deal Analyzer 0-50 — 2026-06-11](https://docs.google.com/spreadsheets/d/1XsoNan-cE85MV_sQMexnnL9N0pdet41kgr7z7TF0WDY/edit)
- Deal folder: [Drive](https://drive.google.com/drive/folders/1YhXnkUg3Jh6tVuaSEg3rE4Oqq350uW1g)
- Analysis Summary (this page as Google Doc): [open](https://docs.google.com/document/d/1VSo6WiODa6R0mgLp9eUjOR0bB0rP8wa2rV397DwmN5w/edit)
- Deal Sourcing row 13 (logged as Pass, training-run note)
- Docs received: OM ✅ · Rent Roll ✅ (3/10/26) · T-12 ❌
