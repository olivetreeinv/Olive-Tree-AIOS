# Olive Tree — Deal Metrics & Thresholds
**Source:** Extracted from `knowledge-base.md` (2026-05-29). Full pipeline → `knowledge-base-process.md`.

*This file contains what deal skills need on every run: thresholds, filters, deal structure, fees, and glossary. Read this by default. Read `knowledge-base-process.md` only for DD checklists, stage-by-stage guidance, or capital raise playbooks.*

---

## Quick Reference — Key Numbers

**Deal thresholds (acquisition screening floors — minimums, not targets):**
- Cash-on-cash: ≥6% by year 3–4 | Property IRR: ≥16% | DSCR: ≥1.25 | Equity multiple: ≥1.8x | LP IRR: ≥14%
- *Targets remain higher: 18.21% ROI, 2.09x EM. Floors are the auto-reject line.*
- 75% Rule: all-in cost < 75% of stabilized value
- 10x NOI Rule: purchase price ≤ 10× NOI

**Deal structure (standard):** 6% pref → 70/30 LP/GP. Target: 18.21% annual ROI, 2.09× equity multiple.

**Buy box:** 15–50 units preferred (analysis floor 5+), $1M–$3M. Active markets → `references/buy-box.md`.

**Stage 4 cadence:** Underwrite 3–5 deals/week → submit 1–3 LOIs/week. Funnel: 150 reviewed → 15 deep-dives → 5 LOIs → 1 deal.

**Market filters:** Pop growth ≥1%/yr | Job growth ≥2%/yr | Rent growth ≥3%/yr | MHI ≥$56K.

**CapEx rule:** $1k reno → $200–$300/mo rent increase to pencil. Bridge loan: non-recourse, 36-mo I/O, 1% lender fee.

---

## Financial Underwriting Metrics

### Market-level filters (before underwriting the deal):
| Metric | Minimum |
|---|---|
| Population growth | 1%+ per year |
| Job growth | 2%+ per year (diverse providers) |
| Rent growth | 3%+ per year |
| Median household income | $56,000+ |
| Employer base | Diverse — no single-employer towns |

### Deal-level filters:
| Metric | Threshold | Notes |
|---|---|---|
| Cash-on-cash return | ≥6% by year 3–4 | Screening floor (after reno + stabilized); target higher |
| Property IRR | ≥16% | Levered, 5–6 yr hold |
| Equity multiple | ≥1.8x | Screening floor; target 2.09x |
| LP IRR | ≥14% | Needs LP waterfall (6% pref → 70/30) — not yet modeled |
| 75% Rule | All-in cost < 75% of stabilized value | Hard filter |
| 1% Rule | Avg monthly rent/unit > 1% of purchase price/unit | Quick sanity check |
| 10x NOI Rule | Purchase price ≤ 10x NOI | Implies ≥10% cap rate on purchase |
| DSCR | ≥1.25 | Debt service coverage ratio |

**20:1 NOI ratio:** For every $1 in NOI = $20 in value (assumes 5% cap rate). Use to estimate value.

**CapEx return rule:** For every $1 spent on renovations, target $200–$300/mo in rent increase. At a 5% cap rate, $1k in reno should produce $200–$300/mo rent increase to justify.

### Deal structure — Olive Tree standard:
| Type | Pref Return | Split | GP Equity | LP Equity |
|---|---|---|---|---|
| Value-add | 6% | 70/30 (LP/GP) | 10% | 90% |
| Stabilized acquisition | 6% | 70/30 (LP/GP) | 10% | 90% |
| Ground-up development | 3–6% | 50/50 | 10% | 90% |
| Higher-upside value-add | 8% | 70/30 (LP/GP) | 10% | 90% |

Post-hurdle: 15% IRR hurdle → then 50/50 split.

### Fee schedule:
| Fee | Amount |
|---|---|
| Property management | 3–5% of gross revenue |
| Asset management | 1–2% of gross income |
| Acquisition fee | 1–3% of purchase price |
| Capital raise fee | 3% |
| Construction/reno management | 5–8% of hard costs |
| Lender fee | 1% |
| Loan broker fee | 0.5% |
| Total closing costs (typical) | 3–4% of purchase price |
| Working capital reserve | 1–2 months gross revenue |

### CapEx sequencing:
1. Deferred maintenance first
2. Cosmetic upgrades second
3. Vacant units first for renovations
4. Then set calendar for unit turns

### Debt financing (value-add):
**Bridge loan (preferred):** Acquire → renovate → stabilize → refinance within 3–4 years into agency debt.
Typical terms: Non-recourse, 36-month I/O, 1% lender fee, 0.5% broker fee, 6-month extension option at 0.5%.

---

## Glossary — Key Terms

| Term | Definition |
|---|---|
| **Cap Rate** | NOI ÷ Property Value — unlevered % return. Lower = more expensive. |
| **Cash-on-Cash Return** | Annual pre-tax cash flow ÷ total cash invested |
| **DSCR** | Debt Service Coverage Ratio = NOI ÷ Annual Debt Service. Must be >1.20 |
| **Equity Multiple** | (Total net profit + equity invested) ÷ equity invested. Target: 2.09x |
| **GPR** | Gross Potential Rent — total rent at 100% occupancy at market rates |
| **IRR** | Internal Rate of Return. Target: 15–20%+ |
| **Loss to Lease** | Difference between market rent and actual contract rent |
| **NOI** | Net Operating Income = Gross Revenue − Operating Expenses (before debt service) |
| **Preferred Return** | LP investors get this % before any GP profit share |
| **RUBS** | Ratio Utility Billing System — billing tenants for shared utilities |
| **T-12** | Trailing 12 months of income/expense history |
| **Value-Add** | Buying underperforming asset, renovating, raising rents, refinancing/selling |
| **Bridge Loan** | Short-term financing (2–3 years) used during value-add renovation |
| **Agency Debt** | Long-term permanent financing from Fannie Mae or Freddie Mac |
| **Basis Points** | 1/100th of a percentage point. 100 bps = 1% |

---

## How Skills Should Use This Doc

| Skill | What to reference |
|---|---|
| `/market-research` | Market-level filters (pop growth, job growth, rent growth, MHI) |
| `/deal-analysis` | Deal-level thresholds, fee schedule, deal structure, CapEx return rule |
| `/daily-brief` | Stage 4 cadence (3–5 underwrites/week, 1–3 LOIs/week) |
| LOI / DD skills | Read `knowledge-base-process.md` for stage checklists |
