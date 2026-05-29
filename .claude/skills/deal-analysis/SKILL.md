# Deal Analysis Skill — Olive Tree Investments
**Trigger:** `/deal-analysis`, "analyze this deal", "run the numbers on", "underwrite this", "does this deal work"

---

## What this skill does

Reads available deal documents (OM, T-12, Rent Roll) — from email attachments, Drive links, or inline data Brian provides — extracts key inputs, calculates the hard underwriting metrics, and compares them against Olive Tree's thresholds. Outputs a go/no-go recommendation with a full metric breakdown.

Designed to be called by `/lets-get-to-work` or run standalone when Brian sends a deal for evaluation.

**Output:** `PURSUE LOI` / `MORE INFO NEEDED` / `PASS` — with every number shown.

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

### Step 1: Buy Box Check

Before touching any numbers, verify the zip is in the active buy box (`references/buy-box.md`).

- Zip IN buy box → proceed
- Zip NOT in buy box → output: "⚠️ [zip] is outside the active buy box. Closest match: [nearest market]. Continue anyway? (y/n)"

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

**Deal Analyzer mapping** (file ID `14bpvhKEuG4UipIDWIZC2Hud9D0JiV2X6`, INPUTS sheet):

| Row | Field |
|---|---|
| Row 4 | Asking Price / Offer Price |
| Row 6 | Units |
| Row 8 | Repair Budget |
| Row 10 | Entry Cap Rate |
| Row 11 | Exit Cap Rate |
| Row 12 | Building Vintage / LTV |
| Rows 20–34 | Unit mix (type, count, current rent, market rent) |
| Rows 50–54 | Output metrics (Cash/Cash, Avg COC, Equity Multiple, IRR) |

### Step 4: Calculate the numbers

```
# Income
GPR (Gross Potential Rent) = sum of all units × market rent/unit
EGI (Effective Gross Income) = GPR × (1 − vacancy%) + ancillary income
  - Use actual vacancy from rent roll; default to 7% if unknown

# Expenses
NOI (Current) = Actual T-12 Revenue − Actual T-12 Expenses
NOI (Stabilized) = EGI (market rents, 93% occ) − Normalized OpEx
  - Property management: 4% of gross revenue
  - Asset management: 1.5% of gross income
  - Total OpEx benchmark: 40–50% of EGI for value-add assets

# Debt (bridge loan, value-add standard)
Loan Amount = Asking Price × 0.75 (75% LTV)
  or: use 70% for heavy value-add
Annual Debt Service = Loan × rate (use current bridge rate from references/news-research.md)
DSCR = NOI ÷ Annual Debt Service

# Returns
Equity Invested = Asking Price × 0.25 + Repair Budget + Closing Costs (3.5%)
Cash-on-Cash (Year 1) = (NOI − Debt Service) ÷ Equity Invested
Cash-on-Cash (Year 3) = Stabilized NOI estimate − Debt Service) ÷ Equity Invested

# Exit (Year 5)
Stabilized Value = Stabilized NOI ÷ Exit Cap Rate
  - Exit cap = Entry cap + 0.25–0.50% (cap rate expansion buffer)
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

| Metric | Threshold | Source |
|---|---|---|
| Cash-on-cash return | 8%+ by Year 3–4 | knowledge-base-metrics.md |
| Project IRR | 15–20%+ | knowledge-base-metrics.md |
| Equity Multiple | 2.09x+ | buy-box.md |
| 75% Rule | All-in ≤ 75% stabilized value | knowledge-base-metrics.md |
| 1% Rule | Monthly rent > 1% price/unit | knowledge-base-metrics.md |
| DSCR | > 1.20 | knowledge-base-metrics.md |
| Price/unit | Within market range in buy-box.md | buy-box.md |

**Recommendation logic:**
- All thresholds pass → **PURSUE LOI**
- 1–2 misses within 10% of threshold with a clear upside story → **MORE INFO NEEDED** + specific questions
- Multiple hard misses or no value-add story → **PASS**

### Step 6: Output the analysis

```
## Deal Analysis — [Property Name]
[Address] | [Market] ([zip]) | [platform/source]
**Asking:** $[price] | **Units:** [n] | **Price/Unit:** $[n] | **Vintage:** [year]
**Docs:** T-12 [✅/❌] | Rent Roll [✅/❌] | OM [✅/❌]

---
### Financials

| Metric | Current | Stabilized | Threshold | Status |
|---|---|---|---|---|
| NOI | $[n] | $[n] | — | — |
| Entry Cap | [n]% | — | — | — |
| Exit Cap (est.) | — | [n]% | — | — |
| DSCR | [n] | — | > 1.20 | ✅/❌ |
| Cash-on-Cash (Yr 1) | [n]% | — | — | — |
| Cash-on-Cash (Yr 3) | — | [n]% | 8%+ | ✅/❌ |
| IRR (est., 5yr) | — | [n]% | 15–20%+ | ✅/❌ |
| Equity Multiple | — | [n]x | 2.09x | ✅/❌ |
| 75% Rule | [all-in $n] | $[stabilized] | < 75% | ✅/❌ |
| 1% Rule | $[rent/unit] | — | > 1% of PPU | ✅/❌ |
| Price/Unit | $[n] | — | $[range] for [mkt] | ✅/❌ |

### Value-Add Story
[Summary: rent gap vs. market, deferred maintenance scope, expected rent bumps post-reno, timeline to stabilization]

### Assumptions Used
[List any estimated values — flag low-confidence inputs]

### Missing Info (if any)
[Specific docs or data points that would change the recommendation]

---
## Recommendation: [PURSUE LOI / MORE INFO NEEDED / PASS]
**Rationale:** [2–3 sentences — the key reason for the recommendation]

[PURSUE LOI]:  "Draft LOI ready to build. Reply 'draft LOI' or continue in /lets-get-to-work."
[MORE INFO]:   "Draft email requesting [specific docs] is below — approve to send."
[PASS]:        "Log as Pass in Deal Sourcing? (y/n) | Want to send a polite pass note? (y/n)"
```

### Step 7: Log to Deal Sourcing sheet

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

### Step 8: Populate Deal Analyzer (on PURSUE or MORE INFO)

Download the deal analyzer, write inputs to INPUTS sheet, upload as a new versioned copy:

```bash
python3 scripts/deal_analysis.py --populate-analyzer \
  --property "[name]" \
  --asking [price] --units [n] --repair [budget] \
  --entry-cap [n] --exit-cap [n] --vintage [year] \
  --unit-mix '[{"type":"1BR","count":10,"current_rent":800,"market_rent":950}, ...]'
```

Saves to Drive as: `[Property Name] — Deal Analyzer — [YYYY-MM-DD].xlsx`
Returns the Drive file ID for Brian to open and review.

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
