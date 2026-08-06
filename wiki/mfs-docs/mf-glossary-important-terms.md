```markdown
---
type: mfs-doc
title: MF Glossary — Important Terms
topic: deal-analysis
instructor: —
source_file: mf-glossary-important-terms.pdf
date_added: 2026-06-09
---

## Summary
This document is a comprehensive multifamily real estate glossary covering core terminology across underwriting, capital structure, affordable housing programs, market analysis, and property operations. It defines approximately 40 terms spanning metrics like NOI, Cap Rate, DSCR, IRR, Equity Multiple, and Cash-on-Cash Return, as well as program-specific terminology (Section 8, LIHTC, Fair Market Rent) and market condition vocabulary. It serves as a foundational reference for anyone analyzing, underwriting, or operating multifamily assets.

## Key Takeaways
1. **NOI is the central underwriting metric** — it excludes debt service, depreciation, capex, and taxes. Every valuation, cap rate calculation, and DSCR analysis flows through NOI, so clean T12 normalization is critical before any analysis.
2. **Cap Rate has a dual function** — it measures current unlevered yield *and* can be used to back into property value when comparable cap rates are known. Entry and exit cap rate assumptions are the single biggest driver of IRR sensitivity in a value-add model.
3. **Equity Multiple ignores timing** — it is an intuitive return measure (total return / equity invested) but must always be read alongside IRR, which accounts for the time value of money and hold period. A high equity multiple on a 10-year hold may underperform a lower multiple on a 3-year hold.
4. **Loss to Lease quantifies embedded rent upside** — the gap between market rents and actual contract rents is a direct value-add signal. Wide Loss to Lease in a stable submarket = underwriting confidence for rent growth projections.
5. **Gross Potential Rent (GPR) is the ceiling** — all vacancy, concessions, loss to lease, and bad debt deductions flow down from GPR to arrive at Effective Gross Income (EGI). Understanding GPR keeps pro forma assumptions honest.
6. **DSCR is the lender's lens** — lenders underwrite to DSCR (NOI / debt service). A DSCR below 1.20 typically triggers agency loan rejections. Value-add acquisitions with in-place NOI must be stress-tested against acquisition debt before assuming stabilization.
7. **Absorption Rate and Occupancy Rate are distinct** — absorption measures leasing velocity of new supply; occupancy measures current fill rate of existing stock. Both matter for submarket supply/demand analysis in buy-box markets.
8. **Section 8 (tenant-based vs. place-based) and LIHTC are separate programs** with different compliance and operational implications. LIHTC (Section 42) ties max rents to AMI; Section 8 vouchers are portable with the tenant.
9. **Soft market conditions signal concession risk** — when supply exceeds demand, concessions erode effective rent. Underwriting should stress-test for concession burn in supply-heavy submarkets within the buy box (e.g., North Nashville pipeline).
10. **Basis Points precision matters in debt analysis** — a 30 bps rate movement on a $1.5M loan is material to DSCR. Always model rate sensitivity in the debt assumptions tab.

## Action Items
- **Add a "Loss to Lease" line to the Olive Tree underwriting template** — calculate the delta between market rent (per CoStar/RealPage) and in-place contract rents on every rent roll review.
- **Always run a dual IRR / Equity Multiple output** in the model — never report one without the other. Flag holds longer than 5 years where the equity multiple looks strong but IRR compresses.
- **Build a DSCR sensitivity table** into the deal model with ±50 bps interest rate scenarios to stress-test agency loan qualification at acquisition NOI.
- **Confirm GPR build-up methodology** on every OM received — verify whether the seller's GPR uses actual unit mix rents or blended averages, as this affects Loss to Lease and vacancy cost calculations.
- **Track Absorption Rate data by submarket** for the 10 buy-box markets — add as a row to the [[markets/]] scorecard template to flag oversupply risk before LOI.
- **When evaluating Section 8 or LIHTC properties**, flag immediately for legal/compliance review — rent restrictions, HAP contract expiration dates, and AMI caps must be modeled separately from market-rate pro formas.
- **Use Turnover Rate from T12 to stress-test CapEx** — high turnover (>60% annually) on a value-add deal means unit turn costs hit sooner and harder than a stabilized property. Factor into Year 1–2 cash flow.
- **Note any Special Assessments** disclosed in due diligence — these are off-P&L costs that reduce actual cash flow and must be added back to Total Operating Expenses in the underwriting model.

## Key Terms
| Term | Definition |
|---|---|
| Absorption Rate | Proportion of newly completed units leased over a given period (e.g., 3 months). |
| Absorptions | Net change in total apartment homes leased. |
| Assisted Housing | Privately owned rental property subsidized by government to house low-income residents; property-based or resident-based. |
| Basis Points | One-hundredth of a percentage point (0.01%). Used to express changes in interest rates. |
| Capitalization Rate (Cap Rate) | Ratio of NOI to property value; measures unlevered current yield and can be used to estimate value from comparable sales. |
| Capital Stack | All debt and equity sources combined used to fund a real estate investment. |
| Cash-on-Cash Return | Annual before-tax cash flow as a percentage of initial cash invested. |
| Concession | Economic incentive (e.g., free rent) offered by owner to encourage leasing or lease renewal. |
| Consumer Price Index (CPI) | BLS measure of average price change over time for a basket of urban consumer goods and services; a proxy for inflation. |
| Debt Service Coverage Ratio (DSCR) | Ratio of NOI to mortgage debt service. Lenders typically require ≥1.20. |
| Economic Base | Industries or businesses providing the foundation of a local economy. |
| Equity Multiple | (Total net profit + max equity invested) / max equity invested. Measures total return but does not account for timing. |
| Fair Market Rent (FMR) | HUD-calculated 40th percentile rent for a metro area; used to set Section 8 payment standards. |
| Garden-Style Apartment Buildings | Low-rise multifamily buildings (≤4 stories) with landscaped grounds, open breezeways, and no elevators. |
| Gross Domestic Product (GDP) | Total market value of all final goods and services produced in the U.S. in a year. |
| Gross Potential Rent (GPR) | Total rent collected if all units were occupied at market rent. The starting line of the income waterfall. |
| Inflation | General upward movement of prices across an economy over time. |
| Internal Rate of Return (IRR) | Discount rate that equates all future investment returns to the initial outlay; accounts for timing of cash flows. |
| Leverage | Use of borrowed funds to finance an investment, increasing potential return or purchasing power. |
| Liquidity | Ease with which an asset can be converted to cash. |
| Loss to Lease | Difference between market rents and actual in-place contract rents for leased units; signals rent upside. |
| Low Income Housing Tax Credit (LIHTC / Section 42) | Dollar-for-dollar federal tax credit incentivizing private equity investment in affordable housing; max rents tied to AMI. |
| Median Household Income | Household income at the 50th percentile for a given geographic area. |
| Mezzanine Debt | Subordinate financing secured by a lien junior to the senior mortgage; used to supplement capital stacks. |
| Mixed-Use Development | Development combining retail, office, residential, or industrial uses on a single parcel or group of parcels. |
| Mortgage Debt Service | Total of principal payments, interest payments, and any credit enhancement costs (e.g., FHA MIP) on a mortgage. |
| Net Operating Income (NOI) | Revenue minus all operating expenses, excluding debt service, depreciation, capex, and income taxes. |
| Occupancy Rate | Percentage of total apartment units currently occupied. |
| Return on Cost | NOI divided by total development or acquisition cost; used to evaluate project viability.