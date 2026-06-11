---
name: market-research
description: Deal-triggered market research for multifamily acquisitions. Takes a city, submarket, or zip code — scores it on 7 criteria (go/no-go), outputs a one-page scorecard with composite score, and packages key numbers for the Underwriting Skill. Trigger on "market research [city]", "/market-research [city]", "research this market", "is [city] a good market for multifamily", or "should I buy in [city]".
---

## What this skill does

Runs a rigorous market intelligence pull on a target city, submarket, or zip code. Scores it against 7 multifamily acquisition criteria using primary data sources. Outputs a one-page go/no-go scorecard with a composite score, verdict, and data block for the Underwriting Skill.

**One run = one scorecard + one verdict + underwriting-ready data block.**

This is **Phase 1 of 2** in the deal evaluation pipeline:
- Phase 1 (this skill) → Market Research → go/no-go on the *market*
- Phase 2 (Underwriting Skill) → Deal Underwriting → go/no-go on the *specific deal*

Only pursue Phase 2 if Phase 1 returns PURSUE or INVESTIGATE.

Source framework: *"Multifamily Market Research — Top 100 MSAs (Growth + Path of Progress)"* — saved at `references/market-research-prompt.docx`.
**Buy Box:** `references/buy-box.md` — 9 active markets with zip codes, strategies, price/unit targets, and vintage ranges. **Read this before running.** If the deal's zip is not in the buy box, flag it to Brian before proceeding.
**Knowledge Base:** `references/knowledge-base-metrics.md` — Market-level filters, deal thresholds, and underwriting metrics. The market-level thresholds in this skill (pop growth, job growth, rent growth, MHI) are sourced from the knowledge base — if there's ever a conflict, knowledge base is authoritative.

---

## When to run

Run this before opening the OM or touching any deal financials. A bad market kills a deal faster than bad numbers.

**Triggers:** "market research [city/zip]", "/market-research [city]", "research this market", "is [city] a good multifamily market", "should I buy in [city]"

**Position in deal pipeline:**
1. Broker sends a listing → run `/market-research [city]` first
2. PURSUE or INVESTIGATE → pull the OM, run Underwriting Skill
3. PASS → reply to broker, move on (fast no = time saved)

---

## Inputs

| Source | What it reads |
|---|---|
| User input | City, submarket, zip code, MSA, or address |
| `references/buy-box.md` | Active markets, zip codes, strategies, price/unit targets, vintage ranges |
| Web search | Primary: Census ACS/PEP, BLS CES/LAUS, BEA, City General Plans, MPO plans |
| Web search | Secondary: CBRE/JLL/Cushman market reports, CoStar or Yardi Matrix public briefs |
| Web search | Path of Progress: DOT, transit agencies, economic development orgs, bond measures |
| `context/priorities.md` | Brian's Q3 goals |

**Citation rule:** Every metric must cite source + data year inline (e.g., "ACS 1-yr 2023," "BLS CES metro 2022–2024"). If data is unavailable from primary sources, label as "estimated" and show method. Never fabricate a number.

**Time windows:**
- **History:** Last 3 years (most recent fully available annual data)
- **Forward:** 3–5 year projections (use credible sources; if unavailable, build a defensible CAGR extrapolation and state method)

---

## Brian's target profile

| Factor | Target |
|---|---|
| Property type | 15–50 unit value-add multifamily |
| Geography | Georgia + Southeast primary; open to other metros |
| Hold period | 4–6 years |
| Return target | 18.21% annual ROI, 2.09x equity multiple |
| Strategy | Value-add: force appreciation through renovation + rent increases |
| Deal type | 15–50 doors — small enough for direct GP control, large enough for institutional-grade operations |

---

## The 7 scoring criteria

Score each: 🟢 Green (go) / 🟡 Yellow (investigate) / 🔴 Red (pass)

### 1. Population Growth (3-year CAGR)

| Signal | Score |
|---|---|
| ≥ 1.0% CAGR (3yr avg) | 🟢 Green |
| 0.8–0.99% CAGR ("borderline") | 🟡 Yellow |
| < 0.8% or declining | 🔴 Red |

**Why it matters:** Declining population = shrinking renter pool. Value-add needs demand to absorb rent increases after renovation.

**Primary sources:** U.S. Census ACS 1-yr or 5-yr estimates; Census Population Estimates Program (PEP). Search: `site:census.gov [city/county] population 2022 2023 2024`

**Anomaly check:** Flag one-time population spikes (disaster displacement, college/base opening/closing). Note if structural vs. temporary.

---

### 2. Job Growth (3-year CAGR)

| Signal | Score |
|---|---|
| ≥ 2.0% CAGR + diverse employer base | 🟢 Green |
| ≥ 1.0% CAGR OR single dominant employer | 🟡 Yellow |
| < 1.0% CAGR, declining, or single-employer town | 🔴 Red |

**Why it matters:** Jobs drive renters. Single-employer towns are fragile — one plant closure or base realignment can gut vacancy overnight.

**Primary sources:** BLS CES (metro area employment series); LAUS (local unemployment). Search: `BLS CES [MSA name] employment 2022 2023 2024`, `[city] largest employers 2025`, `[city] major employer news 2025`.

**Employer diversity check:** Name the top 3–5 employers and their industry. Flag concentration risk if one employer is >15% of local jobs.

---

### 3. Vacancy Rate (current)

| Signal | Score |
|---|---|
| < 8% | 🟢 Green |
| 8–12% | 🟡 Yellow |
| > 12% | 🔴 Red |

**Why it matters:** High vacancy = soft demand. Forces concessions post-acquisition, kills NOI. The value-add model requires ability to hold rents through renovation downtime.

**Primary sources:** Yardi Matrix market reports; CoStar market summaries (public summaries); Apartments.com market research; local property management firms. Search: `[city] multifamily vacancy rate 2025`, `[MSA] apartment vacancy CoStar 2025`.

**Submarket note:** Metro vacancy can mask tight submarkets. If metro is yellow/red but the specific submarket (by zip or neighborhood) is green, note the divergence and use submarket data.

---

### 4. Rent Growth (YoY)

| Signal | Score |
|---|---|
| ≥ 3% YoY | 🟢 Green |
| 1–3% YoY | 🟡 Yellow |
| Flat or declining | 🔴 Red |

**Why it matters:** The value-add model depends on raising rents after renovation. Flat rent environments compress exit cap rates and crush the equity multiple. Target rent increases of 15–25% post-reno need a rising floor to land on.

**Primary sources:** Zillow Observed Rent Index (ZORI); Apartments.com Rent Trends; Yardi Matrix blog. Search: `[city] average rent growth 2025`, `[MSA] multifamily rent trends 2024 2025`.

---

### 5. Median Household Income (current + trend)

| Signal | Score |
|---|---|
| $65,000+ current; OR $55K–$64,999 and rising ≥ 4% YoY | 🟢 Green |
| $45K–$64,999, flat or slow growth | 🟡 Yellow |
| < $45K (affordability ceiling hits fast) | 🔴 Red |

**Why it matters:** Renters typically spend 30% of income on rent. If MHI is too low, there's no ceiling to grow into — even after renovation. Directly caps achievable rents and limits the buyer pool at exit.

**Affordability check formula:** `Target rent ÷ (MHI ÷ 12) × 100` — should be ≤ 35% for healthy absorption. Run this with post-reno target rents.

**Primary sources:** Census ACS Median Household Income; BEA Personal Income data. Search: `site:census.gov [city/county] median household income 2023`, `[city] median income ACS 2024`.

---

### 6. Supply Pipeline (new construction as % of existing stock)

| Signal | Score |
|---|---|
| < 2% of existing stock under construction | 🟢 Green |
| 2–4% of existing stock | 🟡 Yellow |
| > 4% of existing stock (supply wave incoming) | 🔴 Red |

**Why it matters:** New supply absorbs renter demand and forces price/concession competition. Kills rent growth assumptions during hold period. Especially dangerous in years 2–4 of a value-add hold when you're trying to absorb rent increases.

**Primary sources:** Local business journals; CoStar market reports; Census Building Permits Survey. Search: `[city] apartment construction pipeline 2025`, `[MSA] multifamily permits 2024 2025`, `[city] new apartment units under construction`.

---

### 7. Path of Progress

| Signal | Score |
|---|---|
| Named, funded capital projects driving growth to the target area (transit, highways, employer clusters, hospital/university expansion, Opportunity Zones) | 🟢 Green |
| Some development signals but unclear timeline or unfunded | 🟡 Yellow |
| No meaningful infrastructure or employer investment identified | 🔴 Red |

**Why it matters:** Path of Progress is the highest-alpha signal in value-add investing. Buying in front of funded infrastructure creates appreciation beyond what rent growth alone delivers. A 4–6 year hold needs a growth catalyst to deliver the 2.09x equity multiple target.

**What to look for:**
- Transit lines, interchange improvements, airport/port expansion
- Named capital projects with committed (not proposed) funding — cite bond measures, CIP line items
- New employer anchors (tech/biotech cluster, distribution center, medical campus, university expansion)
- Zoning upzones, Opportunity Zone designations, TIF districts
- MPO long-range transportation plan growth corridors
- Note: City/County General Plans (search `[city] general plan growth corridors 2025`) and MPO plans are primary documents — quote section/page if cited

**Sources:** City/County General Plans; MPO long-range plans; DOT project lists; local economic development org; local business journal.

---

## Composite Score

After scoring, calculate the composite score (0–100):

```
Composite = (Pop CAGR % ÷ 4 × 40) + (Jobs CAGR % ÷ 4 × 40) + (MHI CAGR % ÷ 6 × 20)
Cap each component at its max (40, 40, 20).
Add up to +5 bonus points for strong, funded Path of Progress projects (explain the bonus).
```

Example: Pop CAGR 1.8%, Jobs CAGR 2.1%, MHI CAGR 3.5%, strong PoP → (18 + 21 + 11.7 + 4) = **54.7 / 100**

Include composite score in the scorecard. Context:
- 60+ = strong market fundamentals
- 40–59 = moderate, need Path of Progress or deal-specific edge
- < 40 = weak — requires exceptional deal terms to justify

---

## Scoring logic — Verdict

**PURSUE** — 5–7 Green, 0–1 Yellow, 0 Red, composite ≥ 50
Pull the OM. Move to underwriting.

**INVESTIGATE** — 3–4 Green, 2–3 Yellow, 0–1 Red (Red must not be on criteria 1, 2, or 3)
Market has merit but specific risks to verify. Note exactly which criteria need more digging before committing to underwriting. Name the 1–2 things that would move it to PURSUE.

**PASS** — Any Red on criteria 1, 2, or 3 (population, jobs, vacancy) OR 2+ Reds anywhere
Market fundamentals don't support a value-add hold. Reply to broker, move on.

**Override clause:** If vacancy or supply is Red but all other criteria are Green AND the specific submarket diverges sharply from the metro average (common in secondary cities with one tight neighborhood), state the override reason explicitly. Use submarket data, not metro.

---

## Execution

### Step 1 — Parse the input and check the buy box

Extract the market:
- City + state: "Lebanon, TN" → use Wilson County metro area
- Zip code: "37087" → look up city and MSA
- Address: extract city/submarket
- MSA name: "Nashville-Davidson MSA"

**Buy box check (do this before any research):**
Read `references/buy-box.md`. Check if the zip code or city matches an active market.

- **Match found:** Note the market's strategy, vintage target, and price/unit range from the buy box. Use these to calibrate scoring thresholds — e.g., a Smyrna deal should be evaluated as "stabilized with upside," not pure value-add.
- **No match:** Flag it: *"[City/zip] is not in the current buy box. Want me to run research anyway or check if Brian wants to add it?"* Don't proceed without confirmation.

If from a deal alert (broker email, Crexi listing), also capture:
- Property name, unit count, listed price (if known)
- Cross-check unit count against buy box (15–50 units universal filter) — flag if outside range

### Step 2 — Run targeted web searches

Run 6–8 searches. Use primary sources first. Prioritize 2024–2025 data.

**Recommended sequence:**
```
1. "[city] [county] population growth 2022 2023 2024 census"
2. "BLS CES [MSA] total nonfarm employment 2022 2023 2024"
3. "[city] largest employers 2025 economic development"
4. "[city] multifamily vacancy rate rent growth 2025"
5. "[city] apartment construction pipeline permits 2025"
6. "[city] median household income census 2023 2024"
7. "[city] general plan growth corridors capital improvement 2025"
8. "[city] economic development infrastructure projects 2025" (catch-all for PoP)
```

**For each metric found:** note the value, source name, and data year before scoring. If a primary source contradicts a secondary source, prefer primary and note the discrepancy.

### Step 3 — Score all 7 criteria

Apply thresholds. For each criterion:
1. State the metric value (e.g., "Vacancy: 9.1%")
2. State the source and data year (e.g., "CoStar Q4 2025")
3. Assign the color

If a metric is unavailable from any source: assign 🟡 Yellow, note "data unavailable — verify before underwriting." Do not estimate or fabricate.

### Step 4 — Calculate composite score and verdict

Apply formula. Assign bonus (0–5) for Path of Progress with explicit justification. Apply verdict logic.

### Step 5 — Output scorecard

---

## Output format

```
# Market Research — [Market Name]
**For:** [Deal name / property / "Proactive scan"]
**Date:** [today]
**Composite Score:** [X / 100]

---

## Scorecard

| Criterion | Score | Grade | Data Point | Source & Year |
|---|---|---|---|---|
| Population Growth (3yr CAGR) | 🟢/🟡/🔴 | A–F | +X.X%/yr | [source, year] |
| Job Growth (3yr CAGR) | 🟢/🟡/🔴 | A–F | +X.X%/yr | [source, year] |
| Vacancy Rate | 🟢/🟡/🔴 | A–F | X.X% | [source, year] |
| Rent Growth (YoY) | 🟢/🟡/🔴 | A–F | +X.X% | [source, year] |
| Median HHI | 🟢/🟡/🔴 | A–F | $XX,XXX | [source, year] |
| Supply Pipeline | 🟢/🟡/🔴 | A–F | X.X% of stock | [source, year] |
| Path of Progress | 🟢/🟡/🔴 | A–F | [1-line summary] | [source] |

**Letter grade scales:**

| Criterion | A+ | A | A- | B+ | B | B- | C | D | F |
|---|---|---|---|---|---|---|---|---|---|
| Pop CAGR | ≥5% | 3–4.9% | 2–2.9% | 1.5–1.9% | 1.0–1.4% | 0.8–0.99% | 0.5–0.79% | 0.1–0.49% | Declining |
| Job CAGR | ≥4% | 3–3.9% | 2.5–2.9% | 2.0–2.4% | 1.5–1.9% | 1.0–1.4% | 0.5–0.99% | <0.5% | Declining |
| Vacancy | ≤3% | 3–5% | 5–6% | 6–7% | 7–8% | 8–9% | 9–12% | 12–15% | >15% |
| Rent Growth | ≥7% | 5–6.9% | 4–4.9% | 3.5–3.9% | 3.0–3.4% | 2.0–2.9% | 1.0–1.9% | 0–0.9% | Declining |
| MHI | ≥$100K | $85–99K | $75–84K | $65–74K | $60–64K | $55–59K | $45–54K | <$45K | — |
| Supply | <0.5% | 0.5–1% | 1–1.5% | 1.5–2% | 2–2.5% | 2.5–3% | 3–4% | 4–5% | >5% |
| Path of Progress | Multiple funded transformative projects | Major funded project + corridor plan adopted | Named funded project, active planning | Funded planning, no single anchor | Some signals, mostly planned | Unclear timeline | Nothing meaningful | Anti-growth signals | — |

**Composite Score:** [formula breakdown] = [total] / 100
**Path of Progress Bonus:** +[0–5] — [justification]

---

## Verdict: [PURSUE / INVESTIGATE / PASS]

[2–3 sentences. Direct. Lead with the strongest signal. Name the specific risk if INVESTIGATE or PASS.]

## Key Signals
- [Biggest positive — specific, with number]
- [Biggest risk — specific, with number]
- [Path of Progress note — named project or "none identified"]

---

## vs. [MSA Name] MSA

Compare the submarket/city against the broader MSA on every scored metric. Flag where the submarket diverges — outperformance is a buy signal; underperformance narrows the thesis.

| Metric | [City/Zip] | [MSA Name] | vs. MSA |
|---|---|---|---|
| Pop growth (3yr CAGR) | X% | X% | ± X pts |
| Job growth (3yr CAGR) | X% | X% | ± X pts |
| Vacancy rate | X% | X% | ± X pts |
| Rent growth (YoY) | X% | X% | ± X pts |
| Avg rent | $X | $X | ± $X |
| Median HHI | $X | $X | ± $X |

**Read:** [1–2 sentences on what the divergence means for the deal thesis. Is the submarket beating or lagging the metro? Does this strengthen or weaken the value-add case?]

---

## Why Is [City] Growing?

2–4 bullets. Specific, sourced. Name the drivers — employers, infrastructure, migration patterns, affordability relative to a larger neighbor. No generic real estate narrative.

- [Driver 1 — specific employer, project, or demographic trend with number]
- [Driver 2]
- [Driver 3]
- [Risk to growth thesis — what could slow or reverse it]

---

## Underwriting Handoff
*Pass to Underwriting Skill when pulling the deal.*

Market: [city, state / MSA]
Zip: [zip code]
Buy box match: [market name from buy-box.md, or "not in buy box"]
Buy box strategy: [value-add / stabilized w/ upside / long-term hold]
Buy box price/unit target: [$X–$Y/unit]
Buy box vintage target: [years, or "open"]
Composite score: [X/100]
Vacancy (market): [X%]
Rent growth (YoY): [X%]
Median HHI: [$X]
Pop CAGR (3yr): [X%]
Job CAGR (3yr): [X%]
Supply pressure: [low / moderate / high]
Market class: [A/B/C]
Path of Progress: [named project + timeline, or "none"]
Prevailing cap rate: [X% for the asset class/vintage — mark "verified [source/date]" or "ESTIMATE — confirm in DD"]
Property-tax reassessment: [post-sale assessed basis & millage — "verified" or "ESTIMATE"]
Insurance: [indicative $/unit — "verified" or "ESTIMATE — confirm in DD"]
Data gaps: [anything that was unavailable — verify before underwriting]
```

> The three inputs most likely to break a deal are **cap rate, tax reassessment, and
> insurance**. Confirm each with a local broker/assessor where possible and stamp it
> "verified [source/date]"; otherwise flag "ESTIMATE — confirm in DD" so underwriting knows.

---

## Output contract

Every run produces:
1. **One scorecard** — fits one screen
2. **One composite score** — 0–100
3. **One verdict** — PURSUE, INVESTIGATE, or PASS
4. **One underwriting handoff block** — structured, ready for the Underwriting Skill
5. **No files written** — ephemeral by default

**Optional save:** After printing, offer: *"Save to `research/market-[city]-[date].md`?"* Saved reports build a market intelligence library and let you compare markets over time.

---

## Critical rules

1. **Never fabricate metrics.** "Data unavailable" is correct; a made-up number is dangerous. A wrong MHI or vacancy drives a bad LOI.
2. **Cite every metric.** Source + data year, every row. Brian needs to know if he's looking at 2019 data vs. 2025.
3. **Submarket > metro average.** A zip code in a weak metro can be a tight submarket. Flag divergence explicitly. Use submarket data when available.
4. **PASS is a win.** A clean, fast PASS saves hours of underwriting time. Say it clearly.
5. **One verdict only.** Don't hedge. Pick PURSUE, INVESTIGATE, or PASS and own it.
6. **Validate anomalies.** One-off job spikes (construction cycle, stadium build) ≠ structural growth. Note if a metric is distorted by a temporary event.
7. **Speed.** Target under 5 minutes. If searches are slow, prioritize criteria 1–3 (population, jobs, vacancy) — those are the hard deal-killers.

---

## Expansion hooks

| Connection | Enhancement |
|---|---|
| CoStar API (if added) | Pull live vacancy, rent, and supply data — replaces web search for criteria 3, 4, 6 |
| Yardi Matrix API | Same — institutional-grade comps |
| Google Sheets LP Tracker | Auto-log PURSUE verdicts to a market watchlist tab |
| GoHighLevel CRM | Tag broker contacts with active market interest (e.g., "Watching — Lebanon TN") |
