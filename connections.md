# Connections

Registry of every system your AIOS can reach. Filled by `/onboard` from Q4-Q7 answers; expanded over time as you wire new tools. `/audit` checks this file for domain coverage and freshness.

| # | Domain | Tool | Mechanism | Auth | Last checked |
|---|---|---|---|---|---|
| 1 | Revenue / Financials | QuickBooks | not yet connected | — | — |
| 1 | Revenue / Financials | Bluevine (Business Banking) | not yet connected | — | — |
| 2 | Customer / Investor interactions | GoHighLevel CRM | api | Private Integration Token — .env GHL_API_KEY | 2026-05-27 |
| 3 | Calendar | Google Calendar (Google Workspace) | gws cli | OAuth — gws auth login | 2026-05-28 |
| 4 | Communication — Email | Gmail (Google Workspace) | gws cli | OAuth — gws auth login | 2026-05-28 |
| 4 | Communication — DMs | Apple Messages | not yet connected | — | — |
| 5 | Project / task tracking | Google Calendar | gws cli (see Domain 3) | OAuth — gws auth login | 2026-05-28 |
| 6 | Meeting intelligence / Notes | Fathom | script | API key — `FATHOM_API_KEY` in `.env`. `scripts/fathom_sync.py` pulls meetings → Meetings Sheet + `wiki/meetings/`. | 2026-06-10 |
| 7 | Knowledge / files | Google Drive + Sheets | gws cli | OAuth — gws auth login | 2026-05-28 |
| — | Community / Learning | Multifamily Schooled | not yet connected | — | — |
| — | Design / Content | Canva | key+ref | OAuth — tokens in `.env`, refresh via `scripts/canva_oauth_setup.py` | 2026-05-27 |
| — | Design / Content — AI Video | Higgsfield | cli | `hf auth login` (browser device flow) — run once, token stored locally | 2026-06-07 |
| — | Deal Sourcing — MLS Data | FMLS (Bridge Interactive API) | key+ref | Bearer token — `FMLS_API_TOKEN` + `FMLS_DATASET_ID` in `.env` — not yet obtained. Contact Data@FMLS.com to activate. `references/fmls-api.md` | — |
| — | Code Review | Codex CLI (via `openai.chatgpt` VS Code ext) | cli+ref | Device auth — `codex login --device-auth` (uses ChatGPT/Codex plan, no API key). Wrapper: `scripts/codex_review.sh`. `references/codex-review.md` | 2026-06-08 |
| — | Land Wholesaling — Parcel data | County GIS (ArcGIS Online) | script | None — public ArcGIS FeatureServers. `scripts/land_parcels.py` (Bartow + Forsyth GA wired). Only ArcGIS-Online-hosted county orgs reachable. | 2026-06-17 |
| — | Land Wholesaling — Data layer | Google Sheet "Olive Tree — Land Wholesaling" | gws cli | OAuth — `LAND_SHEET_ID` in `.env`. 4 tabs (Land Markets/Builders/Sellers/Deals). Bootstrap: `scripts/land_setup.py` | 2026-06-17 |
| — | Land Wholesaling — Skip trace (phones) | True People Search (free, manual) / Kind·BatchData (paid API) | not yet connected | Mailing addresses come free from county GIS; phone numbers need manual lookup or a paid skip-trace API. Deferred. | — |

**Mechanism options:** `mcp` (MCP server), `script` (Python/Bash hitting an API, in `scripts/`), `export` (CSV/JSON dump pipeline), `key+ref` (`.env` key + `references/{tool}-api.md` guide), `not yet connected`.

When you wire a new tool, also save `references/{tool}-api.md` capturing endpoints, auth flow, and common queries — researched-once-saved-forever.
