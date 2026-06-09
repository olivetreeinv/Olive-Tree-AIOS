---
type: mfs-video-synthesis
title: Skill Upgrade Proposals from Justin Brennan Mentorship Videos
generated: 2026-06-09
source_videos: 22
candidates_considered: 42
status: AWAITING BRIAN'S APPROVAL — no skills modified
---

# Skill Upgrade Proposal — Brian Norton AIOS (Justin Brennan Mentorship Mining)

**Status:** PROPOSAL — nothing applied until Brian approves. Ranked by leverage against Brian's two biggest drags: (a) sourcing too much from Crexi/LoopNet listings, (b) underwriting that anchors to seller numbers instead of bank-grade assumptions.

---

## TIER 1 — Highest Leverage (approve first)

### 1. `broker-search` — Reframe Crexi/LoopNet as broker-DISCOVERY, not deal-discovery
**Why it matters:** Brian is fishing in the 20–30% of inventory that hits portals; the off-market 70–80% only flows through broker relationships. This is the single biggest sourcing-drag fix.

**Paste-ready (new section after "Broker add rules"):**
```markdown
## Why we scan listings — the flip

We do NOT scan Crexi/LoopNet to find deals. We scan them to find BROKERS.
~70–80% of multifamily in a submarket sells off-market and never appears on a
portal. The portal listing is the entry point to the broker who controls that
pocket of inventory.

When a qualifying broker is logged, the goal is not the listed deal — it's to
get on their pre-market / "pocket listing" list. A broker with 2+ active
listings = a broker actively transacting in our buy box = priority outreach.

Set broker outreach goal field on add:
- **Outreach Goal = "Get on pre-market list"** (default for all new brokers)
```
**Confidence:** High · **Sources:** yr_j9NKuFjo, Fb4en-eg04w, GC31FAVq0R4, _EtW1KzYe2k

---

### 2. `broker-search` — Add tour-request + buy-box cold-call script for off-market access
**Why it matters:** Logging a broker does nothing without a contact motion. A defined tour-request script converts a portal listing into a relationship + pre-market flow within ~3 weeks.

**Paste-ready (new section):**
```markdown
## Broker contact script (draft for approval — never auto-sends)

When a broker qualifies (2+ listings), draft outreach using this template.
The on-market listing is the *excuse to call* — the ask is the relationship.

> Hi [Broker], saw your [unit count]-unit on [street] — you've had it ~[days] days,
> any movement? We're an active buyer in [market]: **10–50 units, $[X]–$[Y]M,
> [vintage range]**. Planning to be in-market [next 2 weeks] — I'd love to tour it
> and a couple others so we can learn your inventory firsthand. Also, who are the
> property managers and local agency/bridge lenders you'd trust here?

Rules:
- State the buy box explicitly (units, price, vintage) every time.
- Always close by asking for (a) a tour and (b) PM + lender referrals.
- Goal of the tour is rapport + pre-market access, NOT the listed deal
  (assume ~95% of on-market deals are overpriced).
```
**Confidence:** High · **Sources:** aar3qZ5W3UI, GC31FAVq0R4, _EtW1KzYe2k, x26MoK1vWEA

---

### 3. `deal-analysis` — Bank-grade economic loss default (5% vacancy + 2% other = 7%)
**Why it matters:** Brian's underwriting can't pass a lender's desk if vacancy is modeled optimistically. Banks underwrite to 5%; matching them up front kills false positives.

**Paste-ready (new line in Step 4 assumptions / metrics block):**
```markdown
### Economic loss (mandatory default)
- Vacancy loss: **5%** (banks underwrite to 5 — we match so our NOI survives lender review)
- Other losses (concessions + bad debt): **2%**
- **Total economic loss = 7% of GPR** applied before NOI.
Override only with a documented reason (e.g., true T-12 occupancy materially better/worse).
```
**Confidence:** High · **Source:** d61DVAoqqIM

---

### 4. `deal-analysis` — DCR ≥ 1.25 gate + interest-rate sensitivity → max offer price
**Why it matters:** Stops Brian anchoring to the ask. The numbers set the price; rising rates must auto-reduce max offer to hold DCR.

**Paste-ready (new Step):**
```markdown
### Step 5: Solve for Max Offer (don't anchor to ask)

1. Require **DCR ≥ 1.25x** at the lender's stress rate.
2. Run a rate sensitivity grid: **5.0% / 5.75% / 6.0% / 6.5%**.
3. For each rate, solve the purchase price that holds DCR = 1.25.
4. Report the **max supportable price at the realistic rate**, not the ask.

Output line:
> "At 6.0%, max price holding 1.25 DCR = $[X]. Ask is $[Y]. Gap = $[Z]."

Framing for Brian: "It's not opinion — the numbers make sense or they don't."
```
**Confidence:** High · **Sources:** d61DVAoqqIM, ZuIKwQ071Uo

---

### 5. `deal-analysis` — Lever-adjustment sequence to test deal viability
**Why it matters:** Replaces arbitrary tweaking with a disciplined order, so Brian quickly sees whether a deal is salvageable and exactly which lever does it.

**Paste-ready (append to Step 5):**
```markdown
When a deal misses thresholds, adjust levers in THIS order and report the effect
of each before moving on:
  1. Interest rate (to realistic, not best-case)
  2. Down payment / LTC (note: ↑ equity helps DCR but hurts CoC — show both)
  3. Rent assumptions ($/unit/mo, capped at Rentometer median unless justified)
  4. Purchase price (last resort — solve to make metrics align)

If the deal only works by cutting price >15% below ask → PASS unless broker
signals flexibility.
```
**Confidence:** High · **Source:** x26MoK1vWEA

---

## TIER 2 — Strong adds

### 6. `deal-analysis` — Three-metric return screen (add equity multiple ≥ 1.8x)
**Why it matters:** Confirms a hard pre-screen. DSCR/IRR/CoC are already in the metrics file; **equity multiple ≥1.8x is likely net-new** and is Justin's third mandatory filter.

**Paste-ready (Scorecard / thresholds):**
```markdown
### Mandatory return screen (all three must pass to PURSUE)
- IRR: **14–20%+**
- Cash-on-Cash: **6–10%+**
- Equity Multiple: **≥ 1.8x**  ← add if not already in knowledge-base-metrics.md
If any fails → MORE INFO NEEDED or PASS. Do not advance to LOI on a 2-of-3.
```
**Confidence:** Med (verify against current `knowledge-base-metrics.md` before applying) · **Sources:** GC31FAVq0R4, x26MoK1vWEA

---

### 7. `deal-analysis` — Verify property-tax reassessment + bind-able insurance quote pre-LOI
**Why it matters:** Tax reassessment-on-sale and current insurance are the two expense lines that silently break a model — both are large and both change at closing.

**Paste-ready (new check in Step 3 / expense build):**
```markdown
### Expense reality checks (flag if unverified)
- **Property tax:** Do NOT use seller's current tax. Model reassessment at
  sale price × local mill rate. Flag: "Taxes shown are seller's basis —
  reassessment likely raises this materially."
- **Insurance:** Get a live quote from a local insurance broker before LOI;
  do not trust the T-12 line in hardening markets.
Both should be confirmed with local broker/assessor (use PM/lender referrals
from broker-search outreach).
```
**Confidence:** High · **Source:** d61DVAoqqIM

---

### 8. `deal-analysis` — Require explicit, conservative EXIT cap-rate assumption
**Why it matters:** Models that assume cap compression flatter the IRR. Force an explicit exit cap and default conservative.

**Paste-ready:**
```markdown
### Exit cap assumption (must be explicit)
- Default exit cap = **entry cap + 0.5%** (conservative).
- If the model assumes compression (exit < entry), FLAG it as an aggressive
  assumption and show IRR both ways.
- Note: Justin teaches buying ~6 / selling 4–5 captures spread — treat that as
  upside case, not the base case.
```
**Confidence:** Med (reframed from candidate's aggressive 2% spread to a conservative default — confirm with Brian) · **Source:** d61DVAoqqIM

---

### 9. `lets-get-to-work` — Call broker to validate positioning BEFORE submitting LOI
**Why it matters:** Brian shouldn't submit blind. A 5-minute call confirms competitiveness and offer count, raising win rate without raising price.

**Paste-ready (insert in LOI phase, before draft is finalized):**
```markdown
**Pre-LOI broker check (draft a call note, surface to Brian):**
Before finalizing the LOI, prompt Brian to call the broker:
> "Here's roughly where we're landing — where are you seeing things trend?
> How many offers are on the table right now?"
Capture answers, then confirm/adjust the LOI number. Do not assume where
competing offers sit.
```
**Confidence:** Med-High · **Source:** ZuIKwQ071Uo

---

### 10. `deal-analysis` — Loan-assumption vs. new-loan full 5-yr cash-flow comparison
**Why it matters:** Rate alone misleads. A higher-rate interest-only assumable can beat a lower-rate amortizing new loan on actual cash flow.

**Paste-ready:**
```markdown
### Financing comparison (when an assumable loan exists)
Compare assumption vs. new loan on **full 5-year cash flow**, not rate alone:
- Show annual debt service + cumulative cash flow for each option.
- Interest-only assumable can win on cash flow even at a higher headline rate.
Output a 2-column table; recommend the higher cumulative-cash-flow option.
```
**Confidence:** Med-High · **Source:** ZuIKwQ071Uo

---

## TIER 3 — Useful, lower urgency

### 11. `deal-analysis` — Free cost-seg pre-report to quantify bonus depreciation upside
**Why it matters:** Adds an investor-facing upside line (Year-1 bonus depreciation) at zero cost, strengthening LP appeal.
**Paste-ready:**
```markdown
### Tax upside (optional add-on for shortlisted deals)
For PURSUE deals, request a FREE cost-seg pre-report from a 3rd-party vendor
(pre-engagement). Capture: est. Year-1 bonus depreciation $ and Yr 2–5 schedule.
Add as "Tax Upside" callout — do not include in base IRR.
```
**Confidence:** Med · **Source:** aar3qZ5W3UI

### 12. `broker-search` — Log local team referrals (PM / lender / insurance) per market
**Why it matters:** Feeds the tax/insurance verification step (#7) and builds the team Justin says must exist before a contract.
**Paste-ready:**
```markdown
On each broker call, capture referred PMs, local lenders, and insurance brokers.
Log to a "Local Team" tab keyed by market. These are the contacts deal-analysis
uses to verify insurance + tax assumptions.
```
**Confidence:** Med · **Sources:** aar3qZ5W3UI, x26MoK1vWEA

### 13. `deal-analysis` — Conservative near-term rents, then market-based growth bump
**Why it matters:** Prevents flat-lining rents across the hold; apply growth where market fundamentals support it.
**Paste-ready:**
```markdown
### Rent growth schedule
Hold near-term rents conservative/flat (Yr 1–2), then apply market-supported
growth in out-years (e.g., 5–6% where fundamentals justify). Cite the source
for any growth >3%. Never project flat across the full hold.
```
**Confidence:** Med (market-specific — tie growth % to market-research output) · **Source:** ZuIKwQ071Uo

### 14. `market-research` — Track bridge-debt maturity waves as a distressed-sourcing signal
**Why it matters:** 70–80% of value-add deals used 2–3
