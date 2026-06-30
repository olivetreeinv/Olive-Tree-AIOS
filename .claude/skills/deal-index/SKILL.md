---
name: deal-index
description: Rebuilds the master deal index spreadsheet — one row per property with links to OM, T-12, Rent Roll, Deal Analyzer, Analysis Summary, LOI, and Pitch Deck. Trigger on "/deal-index", "rebuild deal index", "update deal docs index", "show me all deal docs".
---

## What this skill does

Scans every deal folder under **Olive Tree Investments - Deals**, classifies each
file by name keywords, and rebuilds the **Olive Tree Investments - Deal Index**
spreadsheet with one row per property. Each row links to every key document type
found in that deal's folder.

Re-run is idempotent — it overwrites the sheet each time so it's always current.
Folders named `TEST` or `Land Wholesale` are skipped.

## When to run

- **Any time you want a current view of all deal docs** — "/deal-index".
- Runs automatically every Friday 7pm ET via the "Deal Docs — Weekly" cloud routine.

## How it works

`scripts/deal_index.py` (stdlib-only). Per deal folder:

1. **List** — reads every subfolder under the Deals folder.
2. **Classify** — matches file names to doc types using keywords:
   - OM → "offering memorandum", "om"
   - T-12 → "t-12", "t12", "trailing"
   - Rent Roll → "rent roll"
   - Deal Analyzer → "deal analyzer", "proforma"
   - Analysis Summary → "analysis summary"
   - LOI → "loi", "letter of intent"
   - Pitch Deck → "pitch deck"
3. **Write** — clears the master sheet and writes header + one row per deal.

## Commands

```bash
python3 scripts/deal_index.py            # rebuild master index
python3 scripts/deal_index.py --dry-run  # print classification, no sheet write
```

## Key IDs

| Resource | ID |
|---|---|
| Master index sheet | `1mvqgkSw8kMWhWHEVZ4a2Q8IiRihusCwL1zxNwXgj3ao` |
| Deals parent folder | `1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p` |

## Auth

Google only. Needs `GOOGLE_*` env vars (or `gws auth export` locally).

## Cloud note

Runs as part of the "Deal Docs — Weekly" routine every Friday 7pm ET, after
`loi_sync.py`. No wiki writes — just sheet updates.

Run `/code-review` after editing `scripts/deal_index.py`.
