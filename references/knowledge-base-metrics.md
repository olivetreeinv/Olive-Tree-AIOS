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

**Market filters:** Pop growth ≥1%/yr | Job growth ≥2%/yr | Rent growth ≥3%/yr | MHI ≥$56K | Diverse employers — no single-employer towns | Fortune 500 presence = strong signal.

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

**CapEx return rule:** For every $1 spent on renovations, target $200–$300/mo in rent increase. At a 5% cap rate, $1k in reno should produce $200–$300/mo rent increase to justify. More precise benchmark: $1.20–$1.30 in annual rent increase per dollar of CapEx spend (20–30% rent lift per dollar invested).

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

**DSCR below 1.0x at acquisition:** Value-add deals often have sub-1.0x DSCR going in. This requires an I/O period to survive until stabilization — never assume lender approval without it; model it explicitly.

**Exit cap sensitivity:** Always run a sensitivity table. A 50bps expansion at exit materially compresses equity returns. Stress-test exit at going-in cap + 0.50% minimum.

**Property tax reassessment risk:** In reassessment states, taxes can increase 50–90%+ after a sale (based on new purchase price). Model reassessment at full acquisition price in Year 3 — not at the seller's current tax bill. This is one of the most common value-add underwriting traps.

**Return on Cost (ROC):** NOI ÷ total project cost (purchase price + CapEx). Measures yield on every dollar deployed. Target: ROC spread of 150bps+ over your exit cap rate to justify the execution risk.

**1% Rule timing:** Apply to current rents, not pro forma. If current rents don't get to 0.8%+ on your offer price, the rent-growth assumption is carrying too much weight.

---

## MFS Expense Benchmarks — fallbacks when the T-12/OM is missing a line

**Source precedence: T-12 actuals → OM figures → MFS benchmarks.** The T-12 is actual operating history and always wins; OM numbers are the broker's marketing case and fill in only where the T-12 is silent. When a line item has no source in either, underwrite with these Multifamily Schooled (MFS) numbers — **proforma column only**, every defaulted cell tagged as an estimate. `deal_analysis.py` applies these automatically.

**Total operating-expense ratio by vintage (% of Effective Gross Income):**

| Vintage | MFS band | Backfill midpoint |
|---|---|---|
| Pre-1980 (or unknown) | 45–50% | 47.5% |
| 1980–2010 | 35–45% | 40% |
| 2010+ | 30–40% | 35% |

Stabilized target is 49–50% even for 1960s product; 60%+ signals operational problems. Small self-managed 5–10 unit deals can run low-30s — not applicable to Olive Tree (third-party PM always).

**Per-line-item defaults:**

| Line | Default | Notes |
|---|---|---|
| Repairs & Maintenance | $750/unit/yr | MFS: $700–800 typical; $600–800 pre-1980. Never accept a seller number far below this |
| Turnover | $450/unit/yr | $1,500 per turned unit × ~30% annual turnover. R&M + Turnover combined should benchmark ~$1,000/unit/yr — flag if far above |
| Property management | 7–8% of EGI blended (incl. leasing) | Never owner-quoted 5%. Analyzer template auto-calcs 8% |
| Replacement reserves | $250/unit/yr | Analyzer template auto-calc |
| Vacancy / economic loss | 10% of gross rent minimum | 10–12% for 1950–1980 vintage, even at 93% physical occupancy |
| Payroll | $0 at ≤50 units | Offsite third-party management only; payroll lives inside the PM fee |
| Water/sewer RUBS recovery | 60–65% of utility cost recovered | Remainder stays a landlord expense — never model 100% recovery |
| Insurance | No MFS default — quote it | Vendor quotes take 2–3 days; seller master-policy rates aren't transferable. KB floor $1,500/unit until quoted |
| Utilities / Gen-Admin / Contract Serv / Marketing | No MFS default — backfill | Plug the gap between known proforma opex and the vintage-band midpoint (deal_analysis.py splits the plug 60/15/15/10) |

Sources: `wiki/mfs-videos` coaching notes — 11-11-25 mentorship (vintage bands, R&M $800, turnover math), 11-25-25 mentorship (four critical lines, RUBS 60–65%), 02-19-26 (R&M $700–800, 10% vacancy), 05-07-26 (pre-1980 R&M, insurance quotes, 10–12% economic vacancy), 05-14-26 (49–50% stabilized target, 60% RUBS recovery), 05-22-25 (40–50% when seller lacks docs), 04-30-26 (no onsite payroll ≤20 units), 04-22-25 (PM 7–8% blended).

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
| **Absorption Rate** | Speed at which available units are leased in a market — used to gauge supply/demand balance |
| **Concession** | Discount offered to attract tenants (free month's rent, waived fees). Burns off over time; must model burn in underwriting |
| **EGI** | Effective Gross Income = GPR − vacancy − concessions − bad debt − loss to lease |
| **Expense Ratio** | Total operating expenses ÷ EGI. Value-add deals typically run 45–55% at acquisition; compression to 40–45% is the value-creation thesis |
| **Fair Market Rent (FMR)** | HUD-published rent ceiling for Section 8 vouchers by bedroom count and metro. Sets the cap on Section 8 income |
| **HAP Contract** | Housing Assistance Payments contract — ties Section 8 subsidy to a specific property; must be assumed (or terminated) at closing |
| **LIHTC / Section 42** | Low Income Housing Tax Credit — federal tax incentive for affordable housing; rarely relevant for market-rate value-add |
| **Loss-Run History** | 5-year insurance claims record from seller; used to underwrite new insurance and identify recurring physical problems |
| **Mezzanine Debt** | Subordinate debt sitting between senior debt and equity — higher cost, higher leverage; fills capital stack gap on large deals |
| **Return on Cost** | NOI ÷ total project cost (purchase + CapEx). Measures yield on all dollars deployed |
| **Section 8** | HUD rental assistance; tenant-based (voucher travels with tenant) vs. place-based (HAP contract tied to property) |
| **Special Assessment** | One-time charge from municipality or HOA for infrastructure; not on P&L but a real cash drain — must check for pending assessments |
| **LOMA** | Letter of Map Amendment — FEMA document formally removing a property from flood zone; affects flood insurance cost |

---

## How Skills Should Use This Doc

| Skill | What to reference |
|---|---|
| `/market-research` | Market-level filters (pop growth, job growth, rent growth, MHI) |
| `/deal-analysis` | Deal-level thresholds, fee schedule, deal structure, CapEx return rule |
| `/daily-brief` | Stage 4 cadence (3–5 underwrites/week, 1–3 LOIs/week) |
| LOI / DD skills | Read `knowledge-base-process.md` for stage checklists |
