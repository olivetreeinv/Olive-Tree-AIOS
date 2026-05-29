---
name: pitch-deck
description: Build a deal-specific LP pitch deck using Olive Tree's Canva template. Collects deal data, creates a new Canva design, outputs a slide-by-slide content brief, and exports PDF on demand.
triggers:
  - /pitch-deck
  - pitch deck
  - create a pitch deck
  - build a pitch deck
  - investor deck
  - LP deck
outputs:
  - Canva design edit URL (new design named for the deal)
  - Slide-by-slide content brief ready to paste into Canva
  - Optional PDF export via Canva API
dependencies:
  - references/canva-api.md
  - references/buy-box.md
  - references/knowledge-base.md
  - scripts/canva_api.py
  - .env (CANVA_ACCESS_TOKEN)
---

# /pitch-deck Skill

Builds a deal-specific LP pitch deck in Canva. Phase 1 creates a named copy of the master template and outputs a content brief. Phase 2 (when ready) will automate slide population via Canva's brand template autofill API.

**When to run:** After `/market-research` returns a PURSUE verdict, or when a deal reaches Stage 3 (Initial Underwriting) in the pipeline.

---

## Template

**OLIVE TREE TEMPLATE PITCH DECK**
- Design ID: `DAHHfpHE2Es`
- Pages: 60
- Dimensions: 1920×1080 (16:9 widescreen)
- Reference completed deck: `DAHIppfBwgs` (641 Powder Springs St)

---

## Inputs

| Source | What | When |
|---|---|---|
| User / market-research handoff | Deal data (name, address, unit count, price) | Required — Step 1 |
| `references/buy-box.md` | Confirm market match | Required — Step 1 |
| `references/knowledge-base.md` | Return targets, fee schedule, deal structure | Required — Step 3 |
| `references/voice.md` | Tone for any written slide content | Optional |
| `references/canva-api.md` | API endpoints and token refresh | Step 2 |

---

## Execution

### Step 1 — Collect deal data

If invoked directly (not from `/market-research` handoff), ask Brian:

```
What deal are we building this deck for? I need:
1. Deal name (e.g., "The Reserve at Lebanon")
2. Property address
3. Market (city, state)
4. Unit count
5. Asking price (total and/or per unit)
6. Property type (vintage, class)
7. Rehab strategy — light, medium, heavy?
8. Any returns data you've started (CoC, IRR, equity multiple, pref)?
9. Investment minimum and target raise amount?
```

If invoked from `/market-research` handoff block, parse data from the Underwriting Handoff block (deal name, market, price/unit, strategy).

**Buy box check:** Confirm the market is in `references/buy-box.md`. If not, flag it: "⚠ [Market] is not in your active buy box — confirm before building investor materials."

---

### Step 2 — Create the Canva design

Run via `scripts/canva_api.py`:

```bash
source .env
python3 scripts/canva_api.py verify
```

If token is valid:
```bash
python3 scripts/canva_api.py copy DAHHfpHE2Es "Olive Tree - [Deal Name] - [Market]"
```

Example:
```bash
python3 scripts/canva_api.py copy DAHHfpHE2Es "Olive Tree - The Reserve at Lebanon - Lebanon TN"
```

The script outputs:
- New design ID
- Edit URL (share with Brian to open in Canva)

If token is expired, run first:
```bash
python3 scripts/canva_api.py refresh && source .env
```

**Output to Brian:**
```
✓ Canva design created: Olive Tree - [Deal Name]
  Edit: https://www.canva.com/design/[NEW_ID]/edit
  Open this link to see the 60-slide template — ready for your content.
```

---

### Step 3 — Build the content brief

Generate the full slide-by-slide content brief. Brian pastes or types this into the deck. Use data collected in Step 1 + standard return targets from `references/knowledge-base.md`.

**Standard return targets** (from knowledge-base.md, use unless Brian provides deal-specific figures):
- Preferred return: 6%
- LP/GP split: 70/30
- Target IRR: 15–20% (avg. 18.21%)
- Target equity multiple: 2.0–2.2x (avg. 2.09x)
- Hold period: 4–6 years

**Fee schedule** (use unless overridden):
- Acquisition fee: 1–3%
- Asset management: 1–2% of collected rents
- Capital raise fee: 3%
- Property management: 3–5% of collected rents

---

#### Content Brief Template

Format the brief as a numbered section list matching the deck structure. Brackets indicate fill-ins Brian provides.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PITCH DECK CONTENT BRIEF
Olive Tree — [Deal Name]
[Date]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — COVER
Title:        Olive Tree - [Deal Name]
Subtitle:     A [X]-Unit Multifamily Investment Opportunity
Location:     [City, State]
Date:         [Month Year]

SECTION 2 — EXECUTIVE SUMMARY
• [X] units | [Year Built] | [Class] | [Strategy]
• [City, State] — [1-sentence market hook from market-research]
• [Total raise amount] investment opportunity
• [Minimum investment] minimum investment

SECTION 3 — THE OPPORTUNITY
Property address: [Full address]
Property type:    [Multifamily — garden style / townhome / etc.]
Acquisition price: $[Total] ($[per unit]/unit)
Renovation budget: $[X] ($[per unit]/unit) — [light/medium/heavy] value-add
Business plan:    [1–2 sentences: buy, renovate X units, raise rents from $Y to $Z, exit in N years]

SECTION 4 — MARKET OVERVIEW
Market:       [City, State MSA]
Population:   [X] — growing at [X%] CAGR
Job growth:   [X%] — top employers: [1-2 names if known]
Vacancy rate: [X%] (market avg.)
Avg. asking rent: $[X]/mo — up [X%] YoY
Why here:     [1–2 sentences: why this market now, from market-research]

SECTION 5 — THE PROPERTY
• Current occupancy: [X%]
• Current avg. rent: $[X]/mo
• Pro forma avg. rent: $[X]/mo (after renovations)
• Renovation plan: [describe scope — kitchens, baths, exterior, etc.]
• Management: [self-managed / third-party PM]

SECTION 6 — FINANCIAL PROJECTIONS
Purchase price:           $[X]
Total project cost:       $[X] (acquisition + renovations + reserves)
Target raise:             $[X] from LPs
Loan-to-value (LTV):      [X%]
Debt service:             $[X]/mo (DSCR [X])

                 Year 1    Year 3    Year 5
CoC Return:      [X%]      [X%]      [X%]
Cumulative:      [X%]      [X%]      [X%]
Equity Multiple: —         —         [X]x

Preferred Return:   6% annual, paid quarterly
LP/GP Split:        70/30 after preferred
Target IRR:         [X%] (avg. hold [X] years)
Equity Multiple:    [X]x

SECTION 7 — DEAL STRUCTURE
Investment minimum:   $[X]
Total LP raise:       $[X]
Offering type:        [Reg D 506(b) / 506(c)]
Hold period:          [X] years
Distributions:        Quarterly (starting Q[X] Year [X])
Exit strategy:        Sale at cap rate compression / refi and hold

SECTION 8 — THE TEAM
Brian Norton — CEO, Olive Tree Investments
[X] years experience | [X] deals | [X] units managed
[Any co-GP or operator partner name + 1-liner]

SECTION 9 — WHY OLIVE TREE
• [Differentiator 1 — e.g., boots on the ground in Georgia/Southeast]
• [Differentiator 2 — e.g., conservative underwriting, no exotic debt]
• [Differentiator 3 — e.g., aligned incentives — GP co-invests]
• Track record: [X deals / X units / avg. returns if available]

SECTION 10 — RISKS & MITIGATIONS
Risk:               Mitigation:
Rising rates        Fixed-rate debt / rate cap purchased
Rehab overruns      10% contingency built into budget
Occupancy drop      Conservative 90% stabilized assumption
Market softening    5+ year hold, Southeast fundamentals remain strong

SECTION 11 — HOW TO INVEST
1. Complete Investor Questionnaire → link: [investor portal or Typeform]
2. Review PPM + Operating Agreement
3. Sign subscription docs
4. Wire funds by [date]
Contact: brian@olivetreeinv.io | [phone if sharing]

SECTION 12 — APPENDIX (if needed)
• Detailed rent roll
• Full pro forma (Year 1–5)
• Comparable sales
• Market data sources
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**After printing the brief, tell Brian:**
> "Template copy is in Canva — open the edit link above. Paste each section's content into the corresponding slides. When you're done, say 'export PDF' and I'll pull it as a PDF via the API."

---

### Step 4 — Export PDF (on demand)

When Brian says "export PDF" or "ready to export":

```bash
source .env
python3 scripts/canva_api.py export [DESIGN_ID]
```

The script polls the Canva export job and returns a download URL (valid ~24 hours).

Print the URL so Brian can download it or forward to investors.

**Optional — attach to Gmail draft:**
If Brian wants to send to LPs immediately, offer:
> "Want me to create a Gmail draft with this PDF attached for your LP list?"
→ Use Gmail MCP or `gws gmail` to compose draft with the PDF URL in body (Canva export URLs are direct download links — they can paste into email or attach after downloading)

---

## Output contract

Every `/pitch-deck` run produces:
1. **Buy box confirmation** — market is/isn't in active buy box
2. **Canva design link** — new design named for the deal, ready to edit
3. **Content brief** — full slide-by-slide content, formatted for paste-in
4. **PDF export** — on demand when Brian signals ready

No files written locally (deck lives in Canva). Brief is ephemeral in chat unless Brian asks to save it.

---

## Phase 2 — Autofill (future upgrade)

When the master template is converted to a **Canva Brand Template**:
- POST `/autofills` with deal data → auto-populates text fields
- Eliminates manual paste-in
- Requires converting `DAHHfpHE2Es` to a brand template in Canva's template manager

Until then: Phase 1 workflow above is the standard.

---

## Token management

Access tokens expire every 4 hours.

Auto-refresh is built into `scripts/canva_api.py` — it detects 401 responses and calls refresh automatically within a script run.

For interactive sessions (when Claude is calling the script):
```bash
python3 scripts/canva_api.py refresh && source .env
```

Manual rotation (if needed): Re-run `scripts/canva_oauth_setup.py`.

---

## Critical rules

1. **Check buy box first.** Never build investor materials for a market not in `references/buy-box.md` without flagging it.
2. **Never fabricate returns.** If Brian hasn't provided financial projections, use the standard targets from `knowledge-base.md` with clear bracket notation — never invent deal-specific numbers.
3. **Phase 1 is honest about manual work.** The deck is a template copy — Brian still pastes the content. Say that clearly; don't oversell automation that isn't there yet.
4. **Match voice.** Any written slide content (narrative sections, "why this market") should match `references/voice.md` — direct, numbers-first, no corporate filler.
5. **One deck per deal.** Don't create multiple copies. If Brian says "redo it," update the existing design via the edit URL.
