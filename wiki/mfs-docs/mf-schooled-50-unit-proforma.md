```markdown
---
type: mfs-doc
title: MF Schooled 50 Unit Proforma — Sycamore Creek Underwriting Model
topic: underwriting
instructor: —
source_file: mf-schooled-50-unit-proforma.csv
date_added: 2026-06-09
---

## Summary
This document is a detailed multifamily acquisition proforma for Sycamore Creek, a 152-unit (modeled as 200-unit capacity) value-add apartment community listed at $29,000,000. The spreadsheet walks through a full underwriting model including unit mix with market vs. pro forma rents, a trailing 12-month operating statement, stabilized Year 3 projections, senior debt and refinance assumptions, preferred equity structure, stabilization and exit assumptions, and key return metrics (cap rate, DSCR, IRR inputs). It serves as a practical template for how Multifamily Schooled structures a complete acquisition underwriting model from inputs to disposition.

## Key Takeaways
1. **Going-in cap rate is thin at 3.92% (T12) — value creation depends entirely on execution.** The stabilized Year 3 cap rate of 5.72% (return on cost) and exit cap of 7.58% confirm this is a heavy value-add bet requiring significant rent growth (5% annually) and expense normalization, not a stabilized buy.
2. **Rent upside is modeled at ~32.8% gross rent growth** from T12 GPR of $2.36M to stabilized pro forma of $3.13M — achieved via unit interior rehab (200 doors at $0/door interior budget as placeholder) plus market rent premiums across all unit types (e.g., 2BD/2BA market rent $1,381–$1,478 vs. in-place $1,040–$1,245).
3. **Property taxes are the largest underwriting risk line item.** T12 taxes of $277,864 ($1,389/unit) balloon to $525,000 ($2,625/unit) in Year 3 — a 89% increase — driven by a 2.50% property tax rate applied to a projected reassessed value of ~$32.1M. Always model reassessment at acquisition price or higher.
4. **DSCR is below 1.0x at acquisition (0.72x T12, 0.61x underwritten)** — the deal requires an interest-only period on the senior debt (3-year IO, 6.00% rate, 69% LTC) to survive until stabilization. Never assume a lender will approve sub-1.0x DSCR without IO; build IO into every value-add model.
5. **The proforma uses a two-tranche capital stack:** senior debt (69% LTC, 6% rate, 24-month term, 30-year am, 3-year IO) plus an optional preferred equity layer (15% LTV, 6.00% current / 3.00% accrual, 5-year IO). Modeling pref equity separately from common equity is essential for understanding true LP return dilution.
6. **Expense ratio compresses from 52.4% of EGI (T12) to 44.3% (stabilized)** — primarily from payroll normalization ($308K → $260K) and utilities reduction ($206K → $154K). Validate payroll cuts with a staffing plan; this is a common proforma manipulation point.
7. **Exit assumptions drive the return:** 4.80% terminal cap rate on Year 5 NOI with 1.5% commission/title/legal and 0.5% financing fees on refinance. A 50bps cap rate expansion at exit would materially compress equity returns — always run a cap rate sensitivity table.
8. **Annual rent growth of 5.0% and expense growth of 2.0%** are held constant through the hold period. In today's environment, stress-test with 2–3% rent growth and 3–4% expense growth to find the deal's floor.

## Action Items
- **Apply the tax reassessment model to all Olive Tree deals:** Use 2.50% (or local millage rate) × projected assessed value at/above acquisition price. Never carry forward T12 taxes without a reassessment haircut. Cross-check against [[markets/chattanooga-southside]], [[markets/north-nashville]], and all active buy-box markets.
- **Build a two-tranche debt tab** (senior + pref equity) into Olive Tree's standard underwriting template, matching the structure shown here. Flag any deal where going-in DSCR < 1.0x and confirm IO availability before sending LOI.
- **Add a cap rate sensitivity table** (exit cap ± 50bps, ± 100bps) as a standard output on every deal model. The spread between Year 3 return-on-cost (5.72%) and exit cap (7.58%) in this model illustrates meaningful compression risk.
- **Audit the payroll and utilities lines on every T12** received. This model shows payroll dropping 16% ($308K → $260K) and utilities dropping 25% ($206K → $154K) at stabilization — confirm with a management company whether these cuts are achievable before accepting them as underwriting inputs.
- **Use this model's unit mix / $/SF rent structure** as a formatting template for Olive Tree's rent roll analysis. Columns: Type, # Units, Market Rent, Pro Forma Rent, SF, $/SF — gives immediate visual on where rent upside lives by unit type.
- **Set a standard IO requirement:** For any value-add deal where T12 DSCR < 1.15x, require a minimum 2-year IO period in debt assumption and note lender feasibility in the deal page risks section.
- **Reconcile the "200 units to rehab" vs. 152 actual units** discrepancy in this model — likely a template artifact, but illustrates the importance of locking unit count before running returns. Always hardcode unit count in a single input cell.

## Key Terms
| Term | Definition |
|---|---|
| Gross Potential Rent (GPR) | Total rental income assuming 100% occupancy at scheduled market rents; the top-line revenue figure before any deductions. |
| Loss to Lease (LTL) | The difference between market rents and actual in-place (contracted) rents; represents uncaptured rent upside. Modeled here as -4.2% T12, -3.0% stabilized. |
| Effective Gross Income (EGI) | GPR plus ancillary income (RUBS, other income) minus vacancy loss, loss to lease, concessions, and bad debt. The true collected revenue figure. |
| RUBS (Ratio Utility Billing System) | A method of billing residents for a proportional share of property utility costs, converting a landlord expense into recoverable income. |
| Return on Cost (ROC) | Stabilized NOI ÷ total project cost (purchase price + CapEx). Measures yield on total invested dollars; here 5.72% in Year 3. |
| DSCR (Debt Service Coverage Ratio) | NOI ÷ annual debt service. Lenders typically require ≥ 1.20x–1.25x; this deal is 0.72x at T12, requiring IO to bridge to stabilization. |
| Interest-Only (IO) Period | Loan phase where only interest is paid — no principal amortization. Reduces near-term debt service, critical for value-add deals with sub-1.0x going-in DSCR. |
| Loan to Cost (LTC) | Senior loan amount ÷ total project cost. Used in value-add/bridge lending (vs. LTV which uses appraised value). Here 69.0%. |
| Loan to Value (LTV) | Loan amount ÷ appraised property value. Used for the refinance loan assumption; here 75% at refi. |
| Terminal Cap Rate | The cap rate applied to exit-year NOI to calculate the projected sale price. Here 4.80%; higher exit cap = lower sale price = compressed returns. |
| Preferred Equity | A hybrid capital instrument sitting between senior debt and common equity; receives a preferred return (here 6.00% current / 3.00% accrual) before common equity distributions. |
| Stabilization Period | The time required to execute the business plan and reach target occupancy and rents. Modeled here as 24 months. |
| Replacement Reserves | A per-unit annual budget set aside for capital expenditures (appliances, roofs, HVAC, etc.). Modeled