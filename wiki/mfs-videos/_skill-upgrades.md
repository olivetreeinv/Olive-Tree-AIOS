---
type: mfs-video-synthesis
title: Skill Upgrade Proposals from Justin Brennan Mentorship Videos
generated: 2026-06-09
source_videos: 60
candidates_considered: 150
status: APPLIED 2026-06-09 — items 1-12 live (item 4 modified to DD-gated per Brian); deferred 4 + dropped capital-raise/asset-mgmt scoped into new skills
---

# Proposal: Skill Upgrades from Brennan Mentorship Mining
**Status: DRAFT — Brian approves before any change is applied.**

De-duplicated, ranked by leverage to the sourcing/underwriting drag. The single biggest dup across the corpus (three-metric screen) and the biggest accuracy gap (broker-understated expenses) lead.

---

## 1. `deal-analysis` — Add a Three-Metric Fast-Screen Gate (Step 0, before document pulls)
**Why it matters:** ~20 videos teach the same triage; running full underwriting on deals that can't clear it is the core time-sink. A 30-second gate kills no-go deals before any doc retrieval.

**Paste-ready (insert as new Step 0, ahead of Buy Box Check):**
```
### Step 0: Three-Metric Fast Screen (triage before any doc pull)

If even rough numbers exist (price, units, rents), run the quick screen first.
ALL THREE must clear or the deal stops here:

  • IRR (5-yr)            ≥ 14–20%
  • Cash-on-Cash (yr 1)  ≥ 6–10%
  • Equity Multiple       ≥ 1.8x

Output: "Fast-screen: PASS all 3 → proceed to full underwriting" or
        "Fast-screen: FAILS [metric(s)] at [value] → recommend PASS unless price moves to $X."
These are floors, not 2-of-3. Any miss = move on or re-price.
```
**Confidence:** High
**Sources:** cWo8yXJCfC0, jj5i-Eg7dmY, TUA6SDB5Fvg, 3503IlEMVec, GC31FAVq0R4, VMK9h1aJO2g, SgpOGYGXB84, -ArOzEKpz_Y, lPjLGRaW2pA, YlPdtLkshAg, _D8FZeV58bo, s-ym5Lze-3Y, vgqBCHKnMcU, jMXNiPwoLbM, WV57IOrDBcM, neG5DujMGfg

---

## 2. `deal-analysis` — Replace Broker Loss/Expense Assumptions with Underwriting Floors
**Why it matters:** Brokers headline 4–5% vacancy; real economic loss runs 12–15% and expense lines are routinely understated — this is the #1 source of bad NOI and wasted underwriting.

**Paste-ready (insert in Step 4 / expense modeling):**
```
### Expense & Economic-Loss Floors (override the OM)

Never accept the broker's loss line. Underwrite physical vacancy to the
bank's 5% floor, then LAYER economic losses on top:

  Physical vacancy   5% (bank floor)
  Lost-to-lease      1–2%
  Bad debt           2–3%
  Concessions        2–3%
  → Total economic loss 12–15% in non-coastal/secondary markets

Expense reasonableness checks (flag if OM is below):
  Property tax    2–2.5% of likely REASSESSED value (not seller's basis)
  Insurance       ~$1,500/unit (TX/Gulf higher) — get a live quote pre-close
  Repairs/maint   $650–700/unit
  Management      6% for <30-unit deals (3% stated is unrealistic small-prop)

Flag every line where OM differs >15% from these floors as "aggressive."
```
**Confidence:** High
**Sources:** cWo8yXJCfC0, d61DVAoqqIM, lPjLGRaW2pA

---

## 3. `deal-analysis` — DSCR Gate + Interest-Rate Sensitivity → Max Offer Price
**Why it matters:** Turns underwriting from a yes/no into a **max-price output**, and prevents anchoring to the seller's ask — directly speeds LOI decisions.

**Paste-ready (insert as a sensitivity sub-step):**
```
### DSCR Gate & Max-Price Solve

Require DSCR ≥ 1.25x at the lender's quoted rate. Then run a rate sweep
(5.0 / 5.75 / 6.0 / 6.5%) and solve for the purchase price that holds 1.25x:

  Output table:
  Rate    Max Price @ 1.25 DSCR
  5.75%   $6.7M
  6.00%   $6.2M
  6.50%   $5.7M  ← if this is your likely rate, this is your ceiling

Recommendation line: "Max defensible offer = $X at [rate]. Seller ask $Y is
$Z above DSCR ceiling." Numbers decide, not opinion.
```
**Confidence:** High
**Sources:** d61DVAoqqIM, x26MoK1vWEA, ZuIKwQ071Uo

---

## 4. `deal-analysis` — Collections Verification in the "MORE INFO NEEDED" Doc Request
**Why it matters:** T-12s and rent rolls are routinely fudged; economic occupancy ≠ physical. Adds teeth to the doc-request email the skill already drafts.

**Paste-ready (add to the missing-docs request list):**
```
When financials are present but unverified, add to the doc-request draft:
  • 6+ months of bank deposit statements (tie deposits to rent roll)
  • Current delinquency list
  • Eviction-filing list
Cross-match deposits ↔ rent roll ↔ delinquency to compute ECONOMIC occupancy.
Seller refusal to provide bank statements = red flag, note in Callouts.
```
**Confidence:** High
**Sources:** GDkVIivKJ10

---

## 5. `broker-search` + `lets-get-to-work` — On-Market → Pre-Market Access Engine
**Why it matters:** 60–80% of deals trade pre-market; the Gmail scanner only sees the leftovers. This is the structural fix for sourcing drag.

**Paste-ready (add to `broker-search` Broker add rules):**
```
For every newly-added Tier-B broker, set a follow-up flag:
  Action = "Request pre-market list"
  Suggested ask (drafted in lets-get-to-work Phase 2):
  "We're active buyers, 10–30 units in [market]. Can we tour [their listing]
   and get on your pre-market/pocket-listing list?"
Goal of the tour is the RELATIONSHIP, not the listed deal (most are overpriced).
```
**Paste-ready (add to `lets-get-to-work` broker-followup phase):**
```
Tier-B/new brokers: prioritize a 3-property tour ask per target metro.
Track "Pre-market list: Y/N" as a broker field. Brokers on the pre-market
list move to Tier A.
```
**Confidence:** High
**Sources:** u_tBhtH5JhM, jj5i-Eg7dmY, TUA6SDB5Fvg, KJxtmxfFHl4, 3503IlEMVec, GC31FAVq0R4, x26MoK1vWEA, IoUKKt0_z_4, Fb4en-eg04w, Qr3f3NDdPF4, so0MrlNaUQU, YlPdtLkshAg, WV57IOrDBcM, yr_j9NKuFjo, neG5DujMGfg, vgqBCHKnMcU

---

## 6. `broker-search` — Broker Cold-Call Script with Buy-Box + Referral Asks
**Why it matters:** Standardizes outreach so each call also builds the local team (lender/PM/insurance) — compresses time-to-first-deal in a new metro.

**Paste-ready (add as a reference block / template):**
```
### Broker Call Script (paste into outreach draft)
"Hi [name] — calling on your [unit ct]-unit on [street], on market [N] days,
how's activity? We're buyers, 10–30 units, $50–150K/door in [metro].
Two quick asks: (1) anything coming pre-market? (2) who do you use locally
for lending, property management, and insurance?"
Close with: "Setting a tour trip [month] — can we walk it?"
```
**Confidence:** Med
**Sources:** aar3qZ5W3UI, WV57IOrDBcM, _EtW1KzYe2k

---

## 7. `deal-analysis` — Exit Cap Discipline
**Why it matters:** Optimistic exit caps inflate IRR; enforcing a conservative spread is a one-line guardrail against fantasy underwriting.

**Paste-ready (insert in return-assumptions):**
```
Exit cap assumption: set EXIT cap ≥ ENTRY cap + 50–100 bps (conservative).
Never underwrite cap compression as the value driver. If the deal only works
on a lower exit cap, flag in Callouts as "exit-dependent — high risk."
```
**Confidence:** Med-High
**Sources:** d61DVAoqqIM (note: Brennan models compression upside; we invert it as a *conservative floor* — intentional)

---

## 8. `deal-analysis` — Early Obsolescence Screen (in Step 1)
**Why it matters:** Economic obsolescence (busy road/freeway adjacency) is unfixable and cuts the buyer pool ~30%; catch it on the aerial before underwriting.

**Paste-ready (append to Step 1 Buy Box Check):**
```
Aerial/location knockout check:
  • Adjacent to freeway/major arterial, rail, industrial → flag economic
    obsolescence (≈30% buyer-pool / price haircut). Note in Callouts.
  • Distinguish economic (immutable, discount) vs functional (fixable, reno).
```
**Confidence:** Med
**Sources:** LGS0cZpMH0Q

---

## 9. `deal-analysis` — 100%-Occupancy / Reno-Upside Flag
**Why it matters:** Full occupancy at below-market rents signals suppressed rents = value-add upside (or mismanagement); the skill should surface it, not miss it.

**Paste-ready (add to Callouts logic):**
```
If occupancy ≥ 98% AND in-place rents are below Rentometer median →
flag "suppressed rents / value-add upside." Estimate stabilized NOI at median
rents and show the value delta (Value = ΔNOI / cap rate).
```
**Confidence:** Med
**Sources:** y0-uWDfkiGs, jMXNiPwoLbM, _D8FZeV58bo

---

## 10. `deal-analysis` — Rent-Ready Credit + Reassessment/Insurance in DD Asks
**Why it matters:** Standard broker PSAs omit make-ready credits and post-sale tax reassessment; baking these into underwriting/DD protects the entry basis.

**Paste-ready (add to underwriting checklist + doc request):**
```
  • Vacant units: if ≥10 vacant, model a make-ready credit (~$2K/unit) and
    request it in the LOI/PSA.
  • Reassessment: model property tax on likely post-sale assessed value.
  • Insurance: require a live broker quote before removing contingencies.
```
**Confidence:** Med
**Sources:** GDkVIivKJ10, d61DVAoqqIM

---

## 11. `lets-get-to-work` — Pre-LOI Broker Call to Gauge Competition
**Why it matters:** Submitting blind on price loses winnable deals; a 2-minute call calibrates the offer before the LOI draft.

**Paste-ready (add to LOI-draft phase):**
```
Before finalizing any LOI draft, prompt Brian:
"Call broker first? Confirm: how many offers in, where is pricing trending,
are we in range?" Capture answer; adjust LOI price/terms before sending.
```
**Confidence:** Med
**Sources:** ZuIKwQ071Uo

---

## 12. `market-research` — Add Local-Cap-Rate / Tax / Insurance Confirmation to the Data Block
**Why it matters:** The underwriting handoff currently lacks verified cap, tax, and insurance — the three inputs most likely to break a deal.

**Paste-ready (add to underwriting-ready data block):**
```
Before handoff, confirm with a local broker/assessor and stamp into the block:
  • Prevailing cap rate for the asset class/vintage
  • Post-sale property-tax reassessment basis & millage
  • Indicative insurance $/unit
Mark each "verified [source/date]" or "ESTIMATE — confirm in DD."
```
**Confidence:** Med
**Sources:** d61DVAoqqIM, GEmCY-ybTeI

---

## Lower-priority / optional (listed, not recommended for first pass)

| Skill | Change | Why deferred | Sources |
|---|---|---|---|
| deal-analysis | Acquisition-fee (2–3%) modeling to show true GP out-of-pocket | Affects GP economics, not deal go/no-go (Brian's drag is screening) | u_tBhtH5JhM, Qr3f3NDdPF4, YlPdtLkshAg, vgqBCHKnMcU |
| deal-analysis | Cost-seg pre-report for bonus depreciation | DD-stage, post-LOI; not screening-critical | aar3qZ5W3UI |
| deal-analysis | Loan-assumption vs refi full 5-yr cash-flow comparison | Edge case; only on assumable deals | ZuIKwQ071Uo |
| market-research | Bridge-debt maturity waves for distressed sourcing | Macro timing, hard to operationalize now | ZsQZ-I8oyuY |

## Dropped (out of scope / vague / no skill exists)
- All `capital-raise`, `asset-mgmt`, `mindset` candidates (GDkVIivKJ10, GC31FAVq0R4, Fb4en-eg04w, Qr3f3NDdPF4, y0-uWDfkiGs, y4zQ7XRg8OA, etc.) — **no such skill files exist.** If desired, these cluster into a credible *new* `capital-raise` skill (deal-first pitch deck, 506(b) pre-existing relationship via dinners, soft-commit CRM) and `asset-mgmt` skill (retention-weighted PM comp, 4-report ops dashboard, quarterly Loom updates). Flag separately if Brian wants them scoped.
- "5–10 hrs/week," "90-day plan," "two commission jobs," dual-income hustle, post-conference 2–3 takeaways — motivational, not skill-encodable.
- nPxHptaAFBg (all four "None identified") — dropped.
- Tokenization/NFT exit, revenue-share brokerage choice, EXP model — irrelevant to Brian's pipeline.

---

**Recommended first batch to apply:** Items **1–5** (highest leverage, all attack sourcing/underwriting drag directly). Items 6–12 in a second pass.
