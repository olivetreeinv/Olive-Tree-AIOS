```markdown
---
type: market
name: Top 100 U.S. MSAs — Multifamily Growth & Path of Progress Research Framework
zip: "—"
state: US
in_buy_box: false
composite_score: —
last_updated: 2026-06-09
---

## Scorecard
| Criteria | Score (1-10) | Notes |
|---|---|---|
| Population growth | — | Filter threshold: ≥1.0% CAGR (3y); 0.8–0.99% flagged borderline |
| Job growth | — | Filter threshold: ≥2.0% CAGR ideal; ≥1.0% acceptable (3y) |
| Rent growth (YoY) | — | Not specified in source document |
| Vacancy rate | — | Not specified in source document |
| Cap rate trend | — | Not specified in source document |
| Supply pipeline | — | Units under construction/planned per credible public data where available |
| Investor demand | — | Not specified in source document |

**Composite: — / 10 — GO / NO-GO**

---

## Research Methodology (from Source Document)

### Composite Scoring Formula
```
Composite Score (0–100) =
  40% × Pop CAGR (3y, capped at 4%)
+ 40% × Jobs CAGR (3y, capped at 4%)
+ 20% × MHI CAGR (3y, capped at 6%)
+ up to +5 bonus for strong, funded path-of-progress projects
```

### Core Filter Thresholds
| Filter | Threshold | Edge Case Rule |
|---|---|---|
| Population CAGR (3y) | ≥1.0% | 0.8–0.99% = "borderline" |
| Job CAGR (3y) | ≥2.0% ideal / ≥1.0% acceptable | — |
| Median HH Income | ≥$65,000 current | $55k–$64,999 rising ≥4% YoY = "improving" |

### Scope
- Universe: Top 100 U.S. MSAs
- Submarket radius: Within 25 miles of each MSA boundary
- Time horizon (historical): Last 3 years (most recent fully available annual data)
- Time horizon (forward): 3–5 year projections

---

## Primary Data Sources Specified

| Data Type | Source |
|---|---|
| Population | U.S. Census ACS (1-yr/5-yr), Census PEP |
| Jobs | BLS CES (metro area employment), LAUS (unemployment), BEA GDP growth |
| Income | ACS Median Household Income, BEA personal income |
| Development / Path of Progress | City/County General Plans & CIPs, MPO long-range plans, DOT transit/roadway expansion, Opportunity Zones, TIF districts, HUD grants, port/airport expansions, utility capacity plans, major university/medical campus expansions |
| Supplementary | State economic development agencies, EDA, CBRE, JLL, Cushman & Wakefield, CoStar, Yardi Matrix (public briefs only) |

---

## Path of Progress — Evaluation Framework

For each qualifying MSA/submarket, the following must be documented:

1. **Named capital projects** — transit lines, interchanges, airports/ports, water/wastewater, stadiums, university/medical expansions (include dates and dollar amounts where available)
2. **Target growth corridors** — per General Plan, with page/section citations
3. **Zoning changes** — upzones, ADU/lot-split policies, industrial/logistics corridors, tech/biotech clusters
4. **Public spend & timing** — next 5–10 years; bond measures, committed vs. proposed funding distinction
5. **Private pipeline** — multifamily units under construction/planned (credible public data only)

---

## Master Table — Required Output Columns

| Column | Description |
|---|---|
| MSA | Metro Statistical Area name |
| Submarket / within-25mi area | Named submarket or county/census-place proxy |
| Pop CAGR (3y) | 3-year population CAGR |
| Jobs CAGR (3y) | 3-year nonfarm employment CAGR |
| MHI Current | Current median household income |
| MHI CAGR (3y) | 3-year MHI CAGR |
| Meets Filters? | Y / Borderline / N |
| 3–5y Pop Projection | Level + CAGR |
| 3–5y Jobs Projection | Level + CAGR |
| 3–5y MHI Projection | Level + CAGR |
| Key Path-of-Progress Projects | 2–5 bullets with dates/$ |
| General Plan Focus Areas | Page/section reference |
| Major Employers / Sectors | — |
| Housing Supply Signals | Units UC/planned if available |
| Notes / Risks | Anomaly flags, insurance risk, tax reassessment risk |
| Primary Sources | Links with data year |

> **Note:** MSAs failing filters but with exceptional path-of-progress signals are included as `Meets Filters? = N (watchlist)`.

---

## Key Numbers
- Avg asking cap rate: —
- Avg rent/unit: —
- Vacancy rate: —
- YoY rent growth: —

---

## Olive Tree Buy Box Overlap

Markets within the buy box that would appear in a qualifying Top 100 MSA scan:

| Buy Box Market | MSA Parent | ZIP | State |
|---|---|---|---|
| [[markets/chamblee-30341]] | Atlanta-Sandy Springs-Alpharetta MSA | 30341 | GA |
| [[markets/smyrna-30080]] | Atlanta-Sandy Springs-Alpharetta MSA | 30080 | GA |
| [[markets/alpharetta-30005]] | Atlanta-Sandy Springs-Alpharetta MSA | 30005 | GA |
| [[markets/north-nashville-37207]] | Nashville-Davidson-Murfreesboro MSA | 37207 | TN |
| [[markets/madison-tn-37115]] | Nashville-Davidson-Murfreesboro MSA | 37115 | TN |
| [[markets/chattanooga-southside-37408]] | Chattanooga MSA | 37408 | TN |
| [[markets/huntsville-core-35801]] | Huntsville MSA | 35801 | AL |
| [[markets/huntsville-growth-35806]] | Huntsville MSA | 35806 | AL |
| [[markets/birmingham-urban-35205]] | Birmingham-Hoover MSA | 35205 | AL |
| [[markets/lebanon-tn-37087]] | Nashville-Davidson-Murfreesboro MSA | 37087 | TN |

---

## Recommended Follow-Up Prompts (from Source)

1. Re-rank with MHI weight = 35%, Pop = 35%, Jobs = 30%
2. Add multifamily units delivered (last 3 years) and under construction columns
3. Create heat map of within-25-mile submarkets meeting all filters around each MSA
4. Flag MSAs with insurance premium spikes (last 2 years) or property-tax reassessment risk

---

## Active Deals
- —

## Active Brokers
- —

## Sources
- `raw/claude-prompt-multifamily-market-research-top-100-msas.md` — ingested 2026-06-09

## Notes
- This page documents the **research framework and prompt methodology** for scanning Top 100 MSAs; it is not a single-market underwriting page.
- No actual numeric outputs (CAGR figures, MHI values, composite scores) are present in the source document — this prompt is a template to generate that analysis, not the analysis itself.
- Run this prompt in Claude with web browsing enabled to populate the master table and per-MSA charts.
- Data vintage target: ACS 1-yr 2023, BLS CES through 2024, projections to 2028–2030.
- All projections generated by this method should be labeled `modelled` with formula shown per QA rules.
```