# Deal Analysis Skill — Olive Tree Investments
**Trigger:** `/deal-analysis`, "analyze this deal", "run the numbers on", "underwrite this", "does this deal work"

---

## What this skill does

Reads available deal documents (OM, T-12, Rent Roll) — from email attachments, Drive links, or inline data Brian provides — extracts key inputs, calculates the hard underwriting metrics, and compares them against Olive Tree's thresholds. Outputs a go/no-go recommendation with a full metric breakdown.

Designed to be called by `/lets-get-to-work` or run standalone when Brian sends a deal for evaluation.

**Output:** `PURSUE LOI` / `MORE INFO NEEDED` / `PASS` — agent-style format: Quick Verdict traffic lights → financials → letter-grade Scorecard → Callouts → Photos. Every number shown.

---

## References (read before every run)

| File | Why |
|---|---|
| `references/buy-box.md` | Price/unit targets per market, universal criteria, hold period |
| `references/knowledge-base-metrics.md` | Hard thresholds (IRR, CoC, DSCR, 75% rule, 1% rule, fee schedule) |
| `references/google-workspace-api.md` | Drive API for document retrieval |

---

## Inputs — what you need

### Minimum (preliminary analysis):
- Asking price
- Number of units
- Current rents (or rough rent range)
- Zip code / market

### Full analysis requires:
- **T-12** (trailing 12-month P&L) — actual NOI
- **Rent Roll** — current occupancy, unit mix, current vs. market rents
- **OM** (Offering Memorandum) — capex history, renovation scope, photos

If any documents are missing, output a **draft email requesting them** and stop. Brian approves before anything sends.

---

## Execution

### Step 0: Three-Metric Fast Screen (triage before any doc pull)

If even rough numbers exist (price, units, rents), run this 30-second gate first.
ALL THREE must clear or the deal stops here — these are floors, not 2-of-3:

  • IRR (5-yr)            ≥ 14–20%
  • Cash-on-Cash (yr 1)  ≥ 6–10%
  • Equity Multiple       ≥ 1.8x

Output: "Fast-screen: PASS all 3 → proceed to full underwriting" or
        "Fast-screen: FAILS [metric(s)] at [value] → recommend PASS unless price moves to $X."
Any miss = move on or re-price. Don't pull docs on a deal that can't clear this.

**Step 0 add-ons — run alongside the three metrics:**
- **Return on Cost ≥ 18%** — leading indicator; if it clears, IRR/CoC/EM usually follow.
  `Return on Cost = Stabilized NOI ÷ (Purchase Price + Renovation Capex)`
- **Price ≤ replacement cost** — knockout if above. Paying more than it costs to build new kills the value-add thesis.
- **Cap-rate sanity check** — `market cap rate × asking price → implied NOI`. If implied NOI << claimed NOI, seller is overpriced → re-price or PASS.
- **Value-add spread rule** — forced cap should beat exit cap by ≥ 2 pts (e.g., buy at 5 cap → force to 7 cap → exit at 5 cap). If the spread isn't there, the plan won't hit return targets.

### Step 1: Buy Box Check

Before touching any numbers, verify the zip is in the active buy box (`references/buy-box.md`).

- Zip IN buy box → proceed
- Zip NOT in buy box → output: "⚠️ [zip] is outside the active buy box. Closest match: [nearest market]. Continue anyway? (y/n)"

**Aerial / location knockout check** (do alongside the zip check):
- Adjacent to freeway/major arterial, rail, or industrial → flag **economic obsolescence** (≈30% buyer-pool / price haircut). Note in Callouts.
- Distinguish **economic** (immutable — discount) vs **functional** (fixable in reno) obsolescence.
- **Drive-time knockout:** >30–40 min from the primary metro/job center → flag recession risk in Callouts. >40 min = knockout unless the thesis explicitly justifies it (e.g., established suburban submarket with independent demand).

### Step 2: Market Rent Check (Rentometer)

Before or alongside document retrieval, collect inputs for a Rentometer pull. Ask:

```
To pull market rent comps, I need 4 things:
  1. Full property address (include zip)
  2. OM asking rent per unit ($/mo)
  3. Bedrooms (dominant unit type: 1, 2, 3, or 4)
  4. Baths (1 or 1.5+) — optional, skip if unknown
```

Then run:

```bash
python3 scripts/rentometer.py \
  --address "[full address with zip]" \
  --beds [n] \
  --baths "[1|1.5+]" \
  --om-rent [om_rent_per_unit]
```

**Output interpretation:**
- Use Rentometer **median** as the market rent assumption in Step 4.
- If OM rent is above 75th percentile → flag as **aggressive assumption** in the analysis.
- If OM rent is below median → note as conservative (positive signal).

When running `deal_analysis.py --analyze`, pass `--beds` and `--om-rent` and the script auto-pulls Rentometer and sets `market_gpr` from the median. Only call the standalone script above when running a quick comp check outside of full analysis.

---

### Step 3: Retrieve documents

**If Brian provides a local .xlsx path**, auto-convert to CSV before extraction:
```bash
python3 -c "
import pandas as pd, sys, pathlib
src = pathlib.Path(sys.argv[1])
sheets = pd.ExcelFile(src).sheet_names
print('Sheets found:', sheets)
# Use first sheet unless a T-12/P&L sheet is identifiable by name
sheet = next((s for s in sheets if any(k in s.lower() for k in ['t-12','t12','p&l','income','profit'])), sheets[0])
df = pd.read_excel(src, sheet_name=sheet)
out = src.with_suffix('.csv')
df.to_csv(out, index=False)
print('Converted:', out)
" /path/to/file.xlsx
```
Then proceed with the output CSV path.

**From Gmail attachment (most common):**
```bash
python3 scripts/deal_analysis.py --fetch-docs --property "[property name]"
```

**From Google Drive link:**
```bash
python3 scripts/deal_analysis.py --fetch-docs --drive-id [file_id]
```

**Brian pastes data inline:** skip to Step 3 and extract from what's provided.

### Step 3: Extract inputs

Parse documents and extract:

| Input | Primary Source | Fallback |
|---|---|---|
| Asking price | OM cover / email | Brian-provided |
| Units | OM / rent roll header | Brian-provided |
| Current gross rents | Rent roll (sum of current rent column) | T-12 revenue line |
| Market rents | OM rent comp section | Buy box market rate estimate |
| Occupancy | Rent roll (occupied ÷ total) | OM summary |
| Operating expenses | T-12 expense total | 45% of EGI estimate |
| Repair budget / capex | OM capex section | Brian-provided |
| Building vintage | OM / county records | Estimate from description |
| Unit mix | Rent roll (1BR/2BR/3BR counts) | OM floor plan section |

**Deal Analyzer templates** — selected automatically by door count (`scripts/deal_analysis.py`):

| Units | Template | Sheet | ID |
|---|---|---|---|
| ≤ 50 | MF Schooled Deal Analyzer 0-50 v10 | INPUTS | `1smas_-1rTtqZSIvfqxF_NzRFyMe_ID-M17z1BQ7qQQU` |
| > 50 | MF Schooled 50+ Unit Proforma | Inputs | `1_vfRIk8lcj-bGLxj3pf46p8OYwjeiI3o7g7AgjwHZQk` |

0-50 INPUTS mapping: Row 4 asking/offer · Row 6 units · Row 8 repair budget · Row 12 vintage · Rows 21–34 unit mix · F14 rate · C39/F39 vacancy · R35–R38 hold/exit.
50+ Inputs mapping: D4 name · D6 price · D8 vacancy · D9 vintage · D10 address · D15 T-12 GPR · L5:P20 unit mix (type/count/market/proforma/sqft) · T13–T17 debt · T37 capex · T54/T56 exit cap/hold.

### Step 4: Calculate the numbers

```
# Income
GPR (Gross Potential Rent) = sum of all units × market rent/unit
EGI (Effective Gross Income) = GPR × (1 − vacancy%) + ancillary income
  - Use actual vacancy from rent roll; default to 7% if unknown
  - Other income — don't miss it (frequently omitted → understated NOI):
    RUBS (standard at 50+ units), pet rent, admin/app fees, late fees,
    parking, tech package, valet trash. Add each line present in T-12 or OM;
    model conservatively if not yet implemented.

# Expenses
NOI (Current) = Actual T-12 Revenue − Actual T-12 Expenses
NOI (Stabilized) = EGI (market rents, 93% occ) − Normalized OpEx
  - Property management: 4% of gross revenue (use 6% for <30-unit deals — 3% stated is unrealistic for small props)
  - Asset management: 1.5% of gross income
  - Total OpEx benchmark: 40–50% of EGI for value-add assets

# Economic-loss & expense floors — OVERRIDE the OM (never accept the broker's loss line)
Brokers headline 4–5% vacancy; real economic loss runs 12–15%. Underwrite physical
vacancy to the bank's 5% floor, then LAYER economic losses on top:
  Physical vacancy   5% (bank floor)
  Lost-to-lease      1–2%
  Bad debt           2–3%
  Concessions        2–3%
  → Total economic loss 12–15% in non-coastal/secondary markets

Expense reasonableness floors (flag any OM line >15% below these as "aggressive"):
  Property tax    TN/GA/AL (all our buy-box states) reassess county-wide on a CYCLE, NOT on sale —
                  tax follows the county's APPRAISED value, never your purchase price. Do NOT scale
                  taxes to the offer. Pull the OM's reassessment data (county appraised value, mill
                  rates, current + proforma tax) and use the T-12 actual — but verify it against the
                  OM, since the T-12 line can predate a recent reappraisal (Lebanon: T-12 showed
                  $32,699 on the old roll; real 2026 tax was $40,436 post-reassessment). Proforma =
                  current actual × ~3% cycle drift. Effective rates ~0.7–1.3% of appraised value
                  (TN ~0.7–1.0%, GA ~1.0–1.4%, AL ~0.4–0.7%). Only the rare acquisition-value state
                  (e.g. CA/FL nuance) scales tax to the purchase price.
  Insurance       ~$1,500/unit (TX/Gulf higher) — get a live quote before removing contingencies
  Repairs/maint   $650–700/unit
  Management      6% for <30-unit deals
  Make-ready      if ≥10 vacant units, model ~$2K/unit make-ready credit (and request it in the LOI/PSA)
  Turnover        ~$1,000/turn (cleaning, paint, minor repairs between tenants) — sellers routinely omit
  Replacement reserves  ~$250–500/unit/yr OR 5% of EGI — use whichever is higher
Plug all lines in. If OM total expenses look 20%+ below these floors, flag the gap explicitly.

OpEx ratio benchmark: stabilized older assets run upper-30s to low-40s% of EGI. Running
higher = either operational upside (collections gap, rent below market) or a red flag. State
which in Callouts.

Back into the offer price: don't anchor to the seller's ask. Solve the purchase price from
target returns (CoC + IRR floors). Output "Pencils at $X vs. $Y ask — here's where you need
to buy it." Use the solved price as the LOI basis even when far below ask — it opens the broker
conversation and builds credibility.

# Debt (bridge loan, value-add standard)
Loan Amount = Asking Price × 0.75 (75% LTV)
  or: use 70% for heavy value-add
Annual Debt Service = Loan × rate (use current bridge rate from references/news-research.md)
DSCR = NOI ÷ Annual Debt Service

# DSCR gate & max-price solve — output a CEILING, not just a yes/no
Require DSCR ≥ 1.25x at the lender's quoted rate. Then sweep rates
(5.0 / 5.75 / 6.0 / 6.5%) and solve the purchase price that holds 1.25x:
  Rate    Max Price @ 1.25 DSCR
  5.75%   $[n]
  6.00%   $[n]
  6.50%   $[n]   ← if this is the likely rate, this is the ceiling
Recommendation line: "Max defensible offer = $X at [rate]. Seller ask $Y is $Z above
the DSCR ceiling." Numbers set the offer, not the seller's anchor.

# Returns
Equity Invested = Asking Price × 0.25 + Repair Budget + Closing Costs (3.5%)
Cash-on-Cash (Year 1) = (NOI − Debt Service) ÷ Equity Invested
Cash-on-Cash (Year 3) = Stabilized NOI estimate − Debt Service) ÷ Equity Invested

# Exit (Year 5)
Stabilized Value = Stabilized NOI ÷ Exit Cap Rate
  - Exit cap ≥ Entry cap + 50–100 bps (conservative expansion buffer)
  - NEVER underwrite cap compression as the value driver. If the deal only works
    on a lower exit cap, flag in Callouts as "exit-dependent — high risk."
Equity at Exit = Stabilized Value − Remaining Loan Balance
Equity Multiple = (Total Cash Flow + Equity at Exit) ÷ Equity Invested
IRR ≈ Estimate from equity multiple over 5-year hold:
  - 2.0x / 5yr ≈ 15% IRR
  - 2.5x / 5yr ≈ 20% IRR
  - 1.8x / 5yr ≈ 12% IRR

# Quick filters
75% Rule: (Asking Price + Repair Budget) ÷ Stabilized Value < 0.75
1% Rule: Avg market rent/unit > 1% of (Asking Price ÷ Units)
10x NOI: Asking Price ≤ 10 × Current NOI
```

### Step 5: Compare against thresholds

| Metric | Screening floor | Source |
|---|---|---|
| Cash-on-cash return | ≥6% by Year 3–4 | knowledge-base-metrics.md |
| Property IRR | ≥16% | knowledge-base-metrics.md |
| Equity Multiple | ≥1.8x (target 2.09x) | knowledge-base-metrics.md |
| DSCR | ≥1.25 | knowledge-base-metrics.md |
| 75% Rule | All-in < 75% stabilized value | knowledge-base-metrics.md |
| 1% Rule | Monthly rent > 1% price/unit | knowledge-base-metrics.md |
| Unit count | 5+ to analyze (15–50 preferred) | buy-box.md |
| Price/unit | Within market range | buy-box.md |

*Floors are the auto-reject line, not the goal — targets stay higher (18.21% ROI, 2.09x EM). LP IRR ≥14% is a tracked target, not yet computed (needs the LP waterfall).*

**Unit-mix screen:** Target ≥ 55% two-bedrooms — the value-add rent delta is larger on 2BRs than 1BRs. Note actual mix in Callouts.

**Sensitivity rule:** For deals ≥ 20 units, run a stress case alongside base: rent −5%, vacancy +3%, exit cap +50 bps. Don't present a single-scenario model as the conclusion.

**Recommendation logic:**
- All thresholds pass → **PURSUE LOI**
- 1–2 misses within 10% of threshold with a clear upside story → **MORE INFO NEEDED** + specific questions
- Multiple hard misses or no value-add story → **PASS**

### Step 5b: Trust-but-verify reconciliation (run before finalizing price)

Never underwrite seller numbers at face value. Before the offer price is set:

- **Rent Roll → actual leases:** Verify collected rents vs. OM market rents. A gap of $9K/mo or more on a single deal is not unusual — every uncollected dollar is real NOI.
- **T-12 expenses → receipts/invoices:** OM says $25K maintenance? Ask for invoices. $60K is not uncommon.
- **Occupancy → estoppels:** Signed estoppels confirm occupancy and lease terms before LOI.

Flag every discrepancy in the Callouts section. Post-close it's buyer-beware.

> *Bank statements, delinquency list, and eviction filings are DD-phase requests — only after an accepted LOI. See the collections verification note in Step 3.*

### Step 6: Output the analysis

```
## Deal Analysis — [Property Name]
[Address] | [Market] ([zip]) | [platform/source]
**Asking:** $[price] | **Units:** [n] | **Price/Unit:** $[n] | **Vintage:** [year]
**Docs:** T-12 [✅/❌] | Rent Roll [✅/❌] | OM [✅/❌]

### Quick Verdict
🟢/🟡/🔴 Basis · 🟢/🟡/🔴 Returns · 🟢/🟡/🔴 This Deal

---
### Financials

| Metric | Current | Stabilized | Threshold | Status |
|---|---|---|---|---|
| NOI | $[n] | $[n] | — | — |
| Entry Cap | [n]% | — | — | — |
| Exit Cap (est.) | — | [n]% | — | — |
| DSCR | [n] | — | ≥ 1.25 | ✅/❌ |
| Cash-on-Cash (Yr 1) | [n]% | — | — | — |
| Cash-on-Cash (Yr 3) | — | [n]% | ≥ 6% | ✅/❌ |
| IRR (est.) | — | [n]% | ≥ 16% | ✅/❌ |
| Equity Multiple | — | [n]x | ≥ 1.8x | ✅/❌ |
| 75% Rule | [all-in $n] | $[stabilized] | < 75% | ✅/❌ |
| 1% Rule | $[rent/unit] | — | > 1% of PPU | ✅/❌ |
| Price/Unit | $[n] | — | $[range] for [mkt] | ✅/❌ |

### Scorecard
| Category | Grade | Note |
|---|---|---|
| Deal Economics | A–F | IRR / EM |
| Basis (PPU) | A–F | $/unit vs band |
| Leverage / DSCR | A–F | DSCR |
| Value-Add Upside | A–F | rent lift current→proforma |
| Physical Risk | A–F | vintage |
| **OVERALL** | — | PURSUE / CONDITIONAL / PASS |

### Callouts
- [Auto-flagged: pre-1980 vintage, sub-15 units, DSCR below floor, 75% rule, rent upside, basis above band, economic obsolescence, exit-dependent]
- **Suppressed-rents flag:** if occupancy ≥ 98% AND in-place rents are below the Rentometer median → flag "suppressed rents / value-add upside." Estimate stabilized NOI at median rents and show the value delta (Value = ΔNOI ÷ cap rate).

### Photos
📸 Property (Google Maps link) · 🗺️ Area · 🏙️ Community — free Wikipedia images via `scripts/deal_photos.py`

### Value-Add Story
[Summary: rent gap vs. market, deferred maintenance scope, expected rent bumps post-reno, timeline to stabilization]

### Assumptions Used
[List any estimated values — flag low-confidence inputs]

### Missing Info (if any)
[Specific docs or data points that would change the recommendation]

---
## Recommendation: [PURSUE LOI / MORE INFO NEEDED / PASS]
**Rationale:** [2–3 sentences — the key reason for the recommendation]

[PURSUE LOI]:
Output the verdict, then immediately show this go block:

---
## GO — Ready to Offer
**Max defensible offer:** $[DSCR ceiling at likely rate] | **$[PPU]/unit** | **Broker:** [name, firm]
**IRR:** [n]% · **DSCR:** [n]x · **EM:** [n]x

Reply **`/loi`** to draft the Letter of Intent now — terms pre-loaded from this analysis.
---

Do not wait for Brian to ask. Surface the block immediately after every PURSUE LOI verdict.

[MORE INFO]:   "Draft email requesting [specific docs] is below — approve to send."
[PASS]:
- Show the GO price block (see below) — do NOT wait to be asked
- Then: "Draft pass note to broker below — approve to send."

---
## PASS — GO Price
**Binding constraint:** [metric] | **GO price:** $[n] (~$[n]/unit)
**At that price — DSCR:** [n]x · **CoC Yr3:** [n]% · **EM:** [n]x · **75% Rule:** [n]%
Monitor: re-run if ask drops below $[n+10%buffer].
---
```

> **Collections verification is a DUE-DILIGENCE ask — NOT part of the pre-LOI doc request.**
> Only request bank statements once the deal is GREEN on Market + OM + T-12 + Rent Roll
> AND we have an **accepted LOI**. At that point add to the DD request:
>   • 6+ months of bank deposit statements (tie deposits to rent roll)
>   • Current delinquency list
>   • Eviction-filing list
> Cross-match deposits ↔ rent roll ↔ delinquency to compute **economic** occupancy.
> Seller refusal to provide bank statements = red flag — note it and reassess.

### Step 7: Create Deal Folder + Upload All Docs

**One folder. Everything in it. Always — GO or PASS.**

`--populate-analyzer` (Step 9) creates the deal folder automatically and returns its Drive folder ID. Upload OM, T-12, and Rent Roll into that same folder via Drive API immediately after.

**Do NOT call `deal_archive.py`** — it creates a separate dated subfolder, which splits the deal docs across two locations.

```python
# Upload each received doc to the deal folder
import json, requests, sys
sys.path.insert(0, "scripts")
from gws_auth import get_token

token = get_token()
for path, name in [(om_path, "Offering Memorandum — [property].pdf"), ...]:
    with open(path, "rb") as f:
        content = f.read()
    r = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "metadata": (None, json.dumps({"name": name, "parents": [folder_id]}), "application/json"),
            "file": (name, content, "application/pdf"),
        },
        timeout=60,
    )
    r.raise_for_status()
```

Then write and upload Market Analysis Summary + (on PASS) Deal Summary — see Steps 7b and 7c.

### Step 7b: Market Analysis Summary

Write a structured doc covering:
- Buy box fit (strategy match, price/unit vs. band, unit count)
- Demographics (population, MHI, age, employment rate — from OM or KB)
- Location strengths (employment centers, transit, retail, schools)
- Market rent trend (in-place vs. recent leases vs. OM claim; Rentometer if available)
- Supply/demand (new construction risk, segment competition)
- Deal-specific conclusions (what the market supports, what it doesn't at ask price)
- GO price summary if PASS

Upload to the deal folder as a Google Doc via Drive API multipart upload. **Use HTML as the source format** — it preserves Arial font, bold headings, and borderless tables after conversion. Do NOT upload plain text or markdown (flattens all structure).

```python
# Use gws_auth.get_token() — no argument — to get bearer token
# POST https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart
# Part 1 — metadata JSON: {"name": "...", "mimeType": "application/vnd.google-apps.document", "parents": [folder_id]}
# Part 2 — file body: Content-Type: text/html; charset=UTF-8
#
# HTML structure to use:
#   <body style="font-family: Arial, sans-serif; font-size: 11pt;">
#   <h1 style="font-family: Arial; font-weight: bold; border-bottom: 1pt solid #ccc;">Section Heading</h1>
#   <table style="border-collapse: collapse; width: 100%;">
#     <tr><td style="border: none; font-weight: bold;">Label</td><td style="border: none;">Value</td></tr>
#   </table>
```

Reference the 641 Powder Springs Market Analysis doc (`1ipaHSvUKzkDK3xVOTJlqtXez9sCrG-jGGTx-36pC75Q`) as the gold-standard template for structure and formatting.

### Step 7c: Deal Summary (PASS only)

On a PASS verdict, write a short Google Doc — "Deal Summary — [property]" — and upload to the deal folder. Contents:

```
# Deal Summary — [Property]
Date: [date] | Verdict: PASS | Analyst: Olive Tree Investments

## Why We Passed
[2–3 sentence rationale — which thresholds failed and why]

## Key Metrics vs. Thresholds
| Metric | Result | Threshold | Status |
...

## GO Price
Binding constraint: [metric]
Purchase price needed to clear all thresholds: $[n] (~$[n]/unit)
Re-run if ask drops below $[n].

## Broker
[Name, firm, email, phone]
```

This is NOT a full analysis recap — just the decision rationale and GO price, in one place, for future reference.

### Step 8: Log to Deal Sourcing sheet

Regardless of recommendation, log the deal:

```bash
python3 scripts/deal_analysis.py --log-deal \
  --property "[name]" --address "[addr]" --market "[market]" \
  --zip "[zip]" --units [n] --asking [price] \
  --stage "[Analyzing/Pass/LOI Sent]" \
  --broker-name "[name]" --broker-email "[email]" \
  --platform "[Crexi/LoopNet/Email]" \
  --notes "[recommendation + key number]"
```

### Step 9: Populate Deal Analyzer (ALL verdicts)

Download the right template (auto-selected by door count — see the templates table in Step 3), write the inputs, upload as a live Google Sheet:

```bash
python3 scripts/deal_analysis.py --populate-analyzer \
  --property "[name]" --address "[addr]" \
  --asking [price] --offer [go_price] --units [n] --repair [budget] \
  --entry-cap [n] --exit-cap [n] --vintage [year] \
  --unit-mix '[{"type":"1BR","count":10,"current_rent":800,"market_rent":950}, ...]'
```

**PASS deals:** set `--offer` to the GO price calculated in Step 6, NOT the asking price. The analyzer shows Brian what the deal looks like at the number that actually works.

**GO/MORE INFO deals:** set `--offer` to the DSCR max-defensible price.

Saves as `[Property] — Deal Analyzer 0-50 — [date]` (or `— 50+ Proforma —`) **inside the property's deal folder**: `Olive Tree Investments - Deals / [address]/`. Always pass `--address` — it names the folder.

---

## Scripts

```bash
# Full analysis (with docs on Drive)
python3 scripts/deal_analysis.py --analyze \
  --property "[name]" --asking [price] --units [n] --zip [zip] \
  --drive-id [file_id]

# Log deal to sheet only
python3 scripts/deal_analysis.py --log-deal [flags above]

# Populate deal analyzer with inputs
python3 scripts/deal_analysis.py --populate-analyzer [flags above]

# Dry run — print analysis, no writes
python3 scripts/deal_analysis.py --analyze --dry-run [flags]
```

---

## When called by /lets-get-to-work

The orchestrator passes:
- `property`, `address`, `asking`, `units`, `market`, `zip`
- `drive_ids` — list of Drive file IDs for attached docs
- `gmail_message_id` — optional, if docs came via email

This skill returns:
- `recommendation` — one of: `PURSUE_LOI`, `MORE_INFO`, `PASS`
- `metrics` — dict of all calculated values
- `draft_email` — if MORE_INFO, the doc-request draft (shown to Brian for approval)
- `deal_row` — the logged row ID in the Deal Sourcing sheet

---

## Notes

- **Never send emails.** This skill drafts. `/lets-get-to-work` handles the send approval.
- **Always log.** Even a clear Pass gets logged — it's useful for broker relationship tracking.
- **Flag low-confidence assumptions.** If you're estimating expenses or market rents without docs, say so clearly.
- **Deal Analyzer is authoritative.** Once docs are available, populate the Excel model. The manual calculations in Step 4 are for speed — Brian uses the full model for final decisions.
- **Photos auto-resolve.** `deal_analysis.py` calls `scripts/deal_photos.py` for the 3-photo block (area + community = free Wikipedia images, property = Google Maps link). No API key. Listing portals (apartments.com/Crexi) 403 our sandbox, so we don't scrape them.
- **Floors vs. grades.** Pass/fail thresholds are KB-sourced; the Scorecard's A–F grade *scales* are code defaults, not yet KB-grounded (tracked follow-up).
- **Physical DD standard:** Walk every unit (HappyCo + photo/checklist) — no sampling. Segregate deferred maintenance (roof, HVAC, plumbing, foundation — no rent upside; capitalize or seek seller credit) from value-add capex. Check water systems per building: shutoffs, angle stops, piping type (copper vs. galvanized). Water is the top catastrophic-loss risk.
- **GP economics on syndicated deals:** Model net, not gross. Acquisition fee ~2%, disposition ~1%, asset management ~2%, LP preferred return first, then GP promote ~25% over pref. Note GP true capital at risk after acquisition fee offset. Always show LP IRR separately from property IRR.
