---
type: skill
name: govcon
trigger: /govcon
status: active
---

## What it does
Full government contracting workflow. Checks the live bid pipeline, surfaces next actions per bid, drafts subcontractor outreach scripts and emails, and guides each bid from discovery to submission.

## Trigger phrases
- `/govcon`
- "check my bids"
- "where am I on govcon"
- "next steps on bids"
- "help me contact subs"
- "govcon pipeline"
- "what do I do next on govcon"

## What it reads / connects to
| System | Mechanism |
|---|---|
| Google Sheets (bid pipeline) | GWS API |
| Google Drive (bid cache) | GWS API |
| SAM.gov | Direct API (`SAM_API_KEY`) — check cache first |
| USASpending.gov | Direct API |
| Claude Sonnet | Proposal generation |

## Key IDs (from `.env`)
- `SAM_API_KEY` — daily quota, resets midnight UTC
- `GOVCON_SHEET_ID` — bid pipeline spreadsheet
- `DRIVE_GOVCON_CACHE_FOLDER` / `DRIVE_BIDS_FOLDER` — Drive cache folders

## Target NAICS codes
`561730` Landscaping · `561720` Janitorial & Cleaning · `238320` Painting

## Output
- Next action list per bid (status-aware)
- Subcontractor outreach scripts + email drafts
- Proposal text (Claude-generated)
- Pricing rationale

## Notes
- Check `cache.db` (`olive-tree-govcon/cache.db`, `opportunity_store` table, 2877+ rows) before hitting SAM.gov API — avoids rate limits.
- App runs at `localhost:8000` (FastAPI). Start with `uvicorn main:app` from `olive-tree-govcon/`.
- Bid statuses: researching → sub_contacted → quoted → submitted → won/lost/skipped.
- Wiki sync: run `python scripts/wiki_govcon_sync.py` after updating bids to keep `govcon-bids/` pages current.
