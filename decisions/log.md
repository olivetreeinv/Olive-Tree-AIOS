# Decisions Log

Append-only record of meaningful decisions and why they were made. `/level-up` Phase 2 (Method interview) writes scoped automation specs here. You can also append manually whenever you decide something worth remembering.

**Format per entry:**

```
## YYYY-MM-DD — Short title

**Decision:** what was decided.

**Why:** the reasoning, constraints, and what would change your mind.

**Alternatives considered:** what else was on the table.

**Owner:** who's accountable.
```

Keep it terse. Future-you will thank present-you for capturing the *why*, not just the *what*.

---

## 2026-07-03 — SE land-flip 12-zip pull: still quota-blocked; wired seller path + one-button scout

**Decision:** Ship the SE-expansion data pull as push-button, blocked only on vendor quota. Brian emailed Scott at ReportAll directly for a quota bump.

**State:** The `.env` key (`in09INjjWJ`) is the *same* trial key that hit its **1000-request all-time cap** on 2026-07-01 — still 429ing ("exceeded alltime quota limit of 1000 requests"). One verification call slipped through as the last request under the cap; all 12 candidate scouts then 429'd (0 logged). Not spending more until Scott bumps it or a new client id lands in `.env`.

**Shipped (free, ready for when quota clears):**
- `land_sellers.py` now takes `--source reportall --state XX --cap N` (was ArcGIS-only, 2 wired GA counties) — any unwired SE county builds a seller list by zip. Guard message if you forget `--source` on an unwired county. Skill doc updated.
- `scripts/scout_se_candidates.py` — one command runs all 12 ranked candidates (7 STRAT-A acreage + 5 STRAT-B small-lot), logs each to Land Markets, prints a verdict table. cap=500/zip (~12 requests).

**Next when unblocked:** swap the new key into `.env` → `python3 scripts/scout_se_candidates.py`.

**Owner:** Brian Norton

## 2026-05-28 — Added Lebanon TN (37087) to buy box

**Decision:** Lebanon, TN zip 37087 added as active market #10. Strategy: Value-add/Emerging.

**Why:** Market research scorecard returned 71/100 composite — 8.9%/yr city population growth (12th fastest in U.S.), 3.1–3.7% rent growth outpacing Nashville MSA, $72,848 MHI with healthy affordability headroom, TDOT $100M+ Hartsville Pike project funded. Nashville MSA apartment vacancy is 10.8% with declining rents from oversupply — Lebanon is absorbing overflow demand while supply response lags.

**Alternatives considered:** Skip Lebanon since The Reserve at Lebanon failed on price ($5.7M vs. $3M cap). Decided market quality warrants adding the zip even though that specific deal doesn't pencil.

**Owner:** Brian Norton

---

## 2026-05-29 — Automated doc-request drafting in deal_inbox.py

**Decision:** Added `--doc-request INDEX [--send]` to `deal_inbox.py`. Scans inbox, picks the deal at INDEX, generates a doc-request email (OM + T-12 + rent roll), prints draft, optionally sends.

**Why:** Doc requests are 100% deterministic — same 3 docs, same structure, every time. Manual drafting was pure copy-paste overhead on every no-attachment deal.

**Autonomy level:** L2 Drafted — Brian sees the draft, runs `--send` to approve.

**KPI:** Time from deal email received → doc request sent. Target: under 2 minutes.

**Owner:** Brian Norton

---

## 2026-05-29 — Tier-based email personalization in broker_followup.py

**Decision:** `draft_followup_email()` now branches on Tier (A/B/C) before generating a draft. Tier A = casual/no-intro, Tier B = standard, Tier C = formal with full signature.

**Why:** Every broker follow-up session required manual edits to adjust register for known contacts. Tier is already tracked in the sheet — using it eliminates the most common edit.

**Autonomy level:** L2 Drafted — same approval gate, better first draft.

**KPI:** Edit rate per draft — target <1 edit per 3 drafts vs. current ~1 per draft.

**Owner:** Brian Norton

---

## 2026-05-29 — Automated listing availability checks in broker_search.py

**Decision:** Added parallel availability checking to `broker_search.py`. Unavailable listings are filtered before any review, logging, or broker evaluation.

**Why:** Manual URL clicking to verify listings was a recurring tax on every pipeline run — and a stale deal slipped through once (The Flats at 1200). Automation eliminates the check entirely.

**Autonomy level:** L3 Supervised — script runs automatically, Brian sees pre-verified results.

**KPI:** Zero manual availability clicks per pipeline run. Secondary: no unavailable deals reach the review list.

**Owner:** Brian Norton

---

## 2026-05-29 — Pass deal archiver: Drive folder + auto-summary on PASS verdict

**Decision:** Built `scripts/deal_archive.py`. Creates `YYYY-MM-DD — {Address}` subfolder in "Deals" Drive folder, auto-generates a `Deal Summary — {Address}.txt` with key metrics, and uploads any provided docs (OM, T-12, Rent Roll, etc.). Integrated into `deal_analysis.py` via `--archive` flag — fires automatically when verdict = PASS.

**Why:** Passed deals have pattern-recognition value (market data, comp basis, why it didn't pencil). Folder-per-deal with a human-readable summary makes that reference instant vs. digging through email.

**Autonomy level:** L2 Drafted — Brian passes `--archive-files` to specify which docs to include; script creates folder + uploads without additional approval.

**KPI:** Time to archive a passed deal → under 60 seconds. Zero manual Drive folder creation.

**Owner:** Brian Norton

---

## 2026-05-28 — Broker dormant policy changed to manual-only

**Decision:** Removed automatic dormant transition after 3 follow-up attempts. Brokers stay active indefinitely until Brian manually sets Status = "Dormant" in the spreadsheet.

**Why:** Brian wants to control when a broker goes dormant — attempt count alone isn't enough signal. Some brokers are slow to respond but still valuable.

**Alternatives considered:** Keep auto-dormant at 3 attempts (prior behavior). Rejected — too aggressive.

**Owner:** Brian Norton

---

## 2026-06-08 — Realigned deal acquisition thresholds to Multifamily Mentor criteria

**Decision:** Changed the deal-analysis screening floors and unit policy after comparing our output to the "Multifamily Mentor AI" ChatGPT agent on a real Smyrna address:
- DSCR: >1.20 → **≥1.25**
- Cash-on-Cash (yr 3–4): ≥8% → **≥6%**
- Property IRR floor: 15% → **≥16%**
- Equity Multiple floor: 2.09x → **≥1.8x** (2.09x retained as the *target*, not the reject line)
- LP IRR: added **≥14%** as a documented target (not yet enforced — needs the LP waterfall modeled)
- Unit count: 15–50 still preferred, but **analysis floor lowered to 5+ doors** (warn 5–14, hard-fail below 5)

Applied in `scripts/deal_analysis.py` (`THRESHOLDS` dict + score gate) and synced across `references/knowledge-base-metrics.md`, `references/knowledge-base.md`, and `references/buy-box.md`.

**Why:** These are acquisition *screening floors* (minimum to stay alive), not goals. Brian's 18.21% ROI / 2.09x EM targets are unchanged. The looser CoC/EM floors keep marginal-but-workable deals in the funnel for a closer look rather than auto-rejecting them; the tighter DSCR/IRR floors reflect lender reality and a higher return bar. Validated on the Smyrna deal — even with looser floors it still correctly PASSED (75% rule + DSCR fails), so the screen kept its teeth.

**Alternatives considered:** Keep the stricter 8% CoC / 2.09x EM as hard rejects. Rejected — too aggressive for a first-pass screen; better to flag-and-review than auto-kill.

**Owner:** Brian Norton

---

## 2026-06-09 — Added underwriting-discipline rules to the deal knowledge base

**Decision:** Expanded `references/knowledge-base-metrics.md` and `knowledge-base-process.md` with hard-won underwriting rules that were previously implicit:
- **Property tax reassessment risk:** model reassessment at full acquisition price in Year 3 (not the seller's current tax bill) — in reassessment states taxes can jump 50–90%+ after a sale.
- **Exit cap sensitivity:** always run a sensitivity table; stress-test exit at going-in cap **+0.50% minimum**.
- **Sub-1.0x DSCR at acquisition:** value-add deals often go in below 1.0x — model an I/O period explicitly; never assume lender approval without it.
- **Return on Cost (ROC):** NOI ÷ total project cost; target a **150bps+ spread over exit cap** to justify execution risk.
- **CapEx benchmark:** $1.20–$1.30 annual rent increase per $1 of CapEx (20–30% rent lift per dollar).
- **Market filter:** added employer diversity (no single-employer towns; Fortune 500 presence = strong signal).
- **PM selection (process):** 100–1,000 unit portfolio sweet spot, ~10% + 50% first-month fee benchmark, 2–3 week lease-up targets.

**Why:** These are the traps that quietly kill value-add returns — reassessment and exit-cap expansion especially. Encoding them in the KB means every deal skill that reads it applies the discipline automatically, instead of relying on memory deal-by-deal. Directly serves the Q3 constraint (deal sourcing + underwriting drag).

**Alternatives considered:** Leave them as tribal knowledge / apply ad hoc. Rejected — the whole point of the KB is that the deal skills inherit the rules without re-deriving them each run.

**Owner:** Brian Norton

---

## 2026-06-09 — Automated the Daily Brief as a cloud routine (laptop-off, weekday 8am email)

**Decision:** Stood up a `/schedule` **cloud routine** (`trig_01UBdd7vKdi69SiSHiUM8u7c`) that runs `/daily-brief` every weekday and emails the result to brian@olivetreeinv.io — running on Anthropic's cloud, so it works with the computer off. Email only, no SMS. Sign-off on the AIOS wrapper email is **-Olive**.

**How it works:**
- New script `scripts/daily_brief_cloud.py` — stdlib-only (urllib; no `requests`, no `gws` CLI, no MCP). Modes: `fetch` (today's calendar + last-24h Gmail deal/investor/starred buckets as JSON), `send` (emails the finished brief), and `guard --hour` (DST gate). Reads Google OAuth creds from `GOOGLE_*` env vars and hits Google REST directly.
- Routine flow: `guard` → `fetch` → format per `.claude/skills/daily-brief/SKILL.md` in Brian's voice → `send`. Model: Sonnet 4.6.
- **DST handled automatically:** cron `0 12,13 * * 1-5` fires at both 12:00 and 13:00 UTC; the guard lets only the firing that is 8am Eastern proceed and aborts the other. Lands at 8am ET year-round with no manual cron swaps.
- Tested end-to-end locally 2026-06-09 (real fetch + real send both confirmed). `/code-review` pass: no correctness bugs.

**Why direct API, not MCP:** Cloud routines can't attach Google's first-party Gmail/Calendar integrations as MCP, and even where MCP auto-attached, direct API via env-var creds is cleaner and honors Brian's standing "always direct API, never MCP" rule — no exception needed.

**Setup path:** GitHub connected via the Claude GitHub App browser flow (the `/web-setup` slash command wasn't exposed in Brian's VSCode extension; `gh` CLI was already authed). Gmail + Calendar connected as claude.ai connectors.

**Remaining manual step (Brian):** add `GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN` to the cloud environment's Environment Variables (values from `gws auth export --unmasked`). Until then each run emails a graceful "missing GOOGLE_* env vars" note.

**Alternatives considered:** (1) `/loop` — rejected, runs locally so dies when the laptop is off. (2) Gmail/Calendar MCP for the routine — rejected, direct API is cleaner and rule-compliant. (3) Email-to-SMS gateway / Twilio for texting — deferred; email only for now. (4) Single-hour cron + manual DST swap — rejected in favor of the self-correcting two-firing + guard design.

**Owner:** Brian Norton

---

## 2026-06-10 — Two-template Deal Analyzer dispatch + deal folder convention

**Decision:** `--populate-analyzer` in `scripts/deal_analysis.py` auto-selects between two MF Schooled templates by door count: ≤50 units → *Deal Analyzer 0-50 v10* (`1smas_-1rTtqZSIvfqxF_NzRFyMe_ID-M17z1BQ7qQQU`); >50 units → *50+ Unit Proforma* (`1_vfRIk8lcj-bGLxj3pf46p8OYwjeiI3o7g7AgjwHZQk`). Output is a live Google Sheet named `[Property] — [template] — [date]` uploaded as a new file (not in-place edit of the template).

Every deal gets a **property folder** named by full street address inside *Olive Tree Investments - Deals* (Drive folder ID: `1pLWVMaLPy-8Rt1NGQsX2wg2oNDonWC-p`). All deal artifacts file there: OM/T-12/Rent Roll (auto-archived from Gmail), Deal Analyzer, LOI, and Pitch Deck. Folder creation is idempotent — re-runs reuse the existing folder and skip already-uploaded files.

**Why:** The 0–50 and 50+ models have fundamentally different schemas (the 50+ adds RUBS, refi, sensitivities, and a different T-12 income/expense layout) — they can't share a single cell-mapping. Central deal folder eliminates "where is that OM again?" and creates a clean handoff from underwriting → LOI → LP pitch → capital raise, all in one place. Folder name = address so any team member can find it without knowing an internal deal code.

**Alternatives considered:** Single template with hidden rows for the 50+ case — rejected, the models are structurally different enough that a franken-template would be fragile and hard to maintain. Separate scripts per template — rejected, one dispatcher with two dedicated populate functions is cleaner and shares the upload logic.

**Owner:** Brian Norton

---

## 2026-06-14 — `/lets-get-to-work` run: Hawthorne pass-as-relationship, broker_search FMLS fix + unit-filter, 7 new MF brokers

**Decision:** During the Saturday pipeline run, made four linked calls:

1. **4030 Hawthorne Circle SE (Smyrna, 30080) — PASS as a deal, pursued as a broker-relationship opener.** A 4-unit 1981 quadplex at $900K ($225K/unit) — below the 15-unit fund floor and well above Smyrna's $110–160K/door band. Did not chase the asset; instead used it to open the listing agent **Jingru Sui (Keller Williams Realty Atlanta Partners)**, who covers Smyrna (core buy-box) and was not in the Brokers List. Added her as Tier B; staged a buy-box intro draft.

2. **Skipped Justin Landis Group and Elena Gist despite high listing volume.** The broker scan's "6 listings" volume signal was a mirage — their FMLS "Residential Income" listings are 0–1 unit single-family/condo, not multifamily. Adding them would pollute the MF broker list.

3. **Fixed `scripts/broker_search.py` FMLS path + added a unit filter.** Two real bugs: (a) the script never called `load_dotenv()`, so *every* API key read empty and all platforms silently fell back to email — fixed by adding dotenv; (b) the FMLS block pointed at a dead endpoint (`api.fmls.com/v1`, `FMLS_API_KEY`) instead of the working Bridge Data Output OData API (`FMLS_API_TOKEN` + `FMLS_DATASET_ID`) that `deal_search.py` uses — ported it over with `@odata.nextLink` pagination and a 50-page safety cap. Then added `MIN_MF_UNITS = 5`: only listings ≥5 units count toward a broker's qualifying total, so retail SFR/duplex agents stop showing up. Result: FMLS broker discovery went 0 → 352 listings scanned, and the qualifying set tightened from 48 noise brokers to **6 genuine MF brokers**. `/code-review`: APPROVED, no criticals.

4. **Added 6 FMLS-sourced MF brokers to the Brokers List (Tier B)** with intro drafts staged for Monday, each including the broker's actual listings + review links: Anthony Lacy (16u + 6u — 16u is in-product), Jeil Howell (10u + 8u), Syed Firoz (10u + 10u), Jessica Stoddard (10u + 8u), Tim Cowan (8u + 5u), Danielle McCurdy (6u + 6u). None sit in the 3 GA buy-box zips — added for network width, on broker_search's "cast wide" mandate.

**Also this run:** Sent Karen Stephens (GA) a buy-box intro; held Nick Fluellen (TX, outside buy box — keep/cut still pending); surfaced one live in-box deal — Chris Hanné's 20-unit Smyrna (30080), nudge drafted for Monday to pull OM/T-12/rent roll.

**Why:** A no-fit listing is still worth a broker relationship when the agent works a core market — sourcing is the Q3 bottleneck, and broker width is the cheapest lever. The broker_search fixes turn a tool that had never actually queried FMLS into a working MF-broker discovery engine, and the unit filter is what separates real multifamily brokers from duplex agents.

**FMLS data note:** OData `eq` on `ListAgentFullName` is case-sensitive and FMLS stores some agents upper-case, some mixed — match the stored casing exactly or the query returns 0.

**Alternatives considered:** Add all 48 qualifying brokers (rejected — mostly residential agents); add Landis/Elena on volume alone (rejected once unit data showed 0–1 unit listings); leave broker_search on email-only fallback (rejected — the FMLS feed is the highest-signal source and was simply misconfigured).

**Owner:** Brian Norton

---

## 2026-06-14 — Killed "CRE underwriting tool as a product"; trialing Cash Flow Portal instead

**Decision:** Do not build the AI underwriting/OM-extraction tool as a sellable product. Keep it as an internal AIOS tool. Separately, evaluate **Cash Flow Portal's $1,199/mo AI Underwriting** for one month head-to-head against our own `scripts/deal_analysis.py` before deciding whether to buy, build further, or keep our stack as-is.

**Why:** Competitive scan (Perplexity, 2026-06-14) found the exact wedge we were targeting — "ugly OM PDF → auto-filled underwriting in 60 sec" — is already a shipped, productized feature at Cash Flow Portal, priced at $1,199/mo and aimed at our exact buyer (15–50 door syndicators raising from individual LPs). They claim >95% PDF / 99.9% Excel parse on rent rolls/T-12s and parse the OM for property/photos/demographics into a cloud underwriting model with waterfalls. A.CRE has no native ingestion (education + custom-GPTs only); Archer is institutional and "doc-analysis first, underwriting second." Building to sell would mean fighting a better-capitalized incumbent on the exact axis (deal-sourcing speed) that is Brian's Q3 edge — and handing that edge to competitors. The only defensible openings left (parse into the operator's *own* Excel; a sub-$100 screen-only tier) are narrow and not worth a side-quest against the Q3 goals.

**What would change this:** If a one-month trial shows Cash Flow Portal's parse is mediocre on real scanned OMs (the >95% is a marketing number), the "parse into your own model" gap may be real enough to reconsider — but as a tool we use, not necessarily a product we sell.

**Alternatives considered:** (1) Build the ingestion layer and sell it — rejected, feature already taken by an incumbent owning the full workflow. (2) Reverse-engineer A.CRE/Blank Excel templates and sell an ingestion add-on — parked; defensible but a distraction from Q3. (3) Ignore Cash Flow Portal and keep building ours blind — rejected; cheaper to trial theirs and learn than to guess.

**Owner:** Brian Norton

---

## 2026-06-14 — SQLite database backend for the AIOS (three-tier storage)

**Decision:** Stand up a local SQLite database (`data/olive.db`) as the queryable data layer for the AIOS. Three tiers: structured rows (deals, brokers, markets, investors, meetings, decisions) → SQLite via SQLAlchemy ORM; long-form documents (wiki, transcripts, skill docs) → stay Markdown, indexed by path+frontmatter in a `documents` table; binary files (OMs, decks) → filesystem/Drive, pointer stored in DB. DB mirrors Google Sheets (Brian still edits in Sheets; `scripts/db_sync.py` upserts nightly). When the Mac mini arrives, swap `DATABASE_URL` in `.env` to `postgresql://...` — SQLAlchemy handles the dialect, no queries change.

**Why:** No single source of truth today — deals and brokers are duplicated across Google Sheets and the wiki markdown and drift apart. Can't join across tables ("all Tier-A TN brokers with a deal in 90 days") without hand-coding loops. SQLite was already proven in this repo (govcon `cache.db`, `sam_data.db`). JSON files (the alternative considered) are a great field format but a poor database — they require hand-writing the filter, join, and dedup logic that SQL gives for free.

**Alternatives considered:** (1) Loose JSON files — rejected: no queries, no joins, no dedup enforcement. (2) PostgreSQL from day one — rejected: needs a running server process, overkill for a single-user laptop; lift to Postgres is a one-line `.env` change when the Mac mini arrives. (3) DB-as-master (replace Sheets) — deferred: Brian edits in Sheets today; switching the source of truth requires a new edit UI. DB-as-master is the right long-term move; DB-mirrors-Sheets reduces the transition risk.

**Owner:** Brian Norton

---

## 2026-06-14 — Launched CRE Services freelance line (`cre-services/`)

**Decision:** Stand up a productized service line selling Brian's underwriting, BPO, and market-analysis skills as fixed-price deliverables. First channel: Upwork. Project lives in top-level `cre-services/` (mirrors `olive-tree-govcon/`, `spcx-monitor/`).

**Why:** The AIOS already produces ~80% of each deliverable (`/market-research`, `/underwriting`, `/deal-analysis`), so marginal cost is near-zero and turnaround is fast. A $150 market analysis bills ~$300/hr of Brian's actual time while still underpricing the market. Generates side income and sharpens the same skills used on Olive Tree's own deals. Launch low to bank reviews (Upwork algorithm punishes zero-review sellers), then climb to established pricing.

**Alternatives considered:** Hourly-only listing (rejected — fixed-price productized gigs convert better on Upwork). Platform-specific naming (rejected — kept `cre-services` platform-agnostic to allow direct/referral expansion).

**Owner:** Brian Norton

---

## 2026-06-17 — Launched land-wholesaling vertical (Bartow GA, builder-first, free-first)

**Decision:** Stand up a land-wholesaling business line inside the AIOS as a distinct vertical (own skills/scripts/references + a dedicated Google Sheet `LAND_SHEET_ID`, GovCon-style), separate from the multifamily pipeline. Model is builder-first (per Carson & Jackson): lock out-of-state owners' vacant lots under assignable contracts ~10–20% below a builder/developer's price, then assign for the spread. Free-first MVP — county tax-assessor parcel data (ArcGIS Online) for scouting + seller lists, AI-generated contracts, Brian dials first. Launch market: **Cartersville (Bartow County), zips 30120/30121.**

**Why:** The doc's data sources (Zillow, True People Search) block automation here, but the authoritative source — county parcel layers on ArcGIS Online — is free and JSON-queryable, and it directly yields owner mailing addresses + out-of-state flags + acreage + land value. Live screening proved the market choice matters more than gut and rewards accurate tooling: Forsyth/30040 has a real absentee pool (~367 vacant out-of-state lots) but **uniformity 0.0 (non-cookie-cutter) and a high ~$256K avg land basis** → poor wholesale economics in a built-out, expensive metro. Bartow/Cartersville (30120/30121) has ~400 vacant out-of-state lots at a cheap basis (~$29K–$139K) with better uniformity (0.38) and package-deal owners → viable. So Forsyth is kept only as a GIS test county; Bartow is the launch market. (Note: an early "Forsyth has ~1 absentee lot" reading was a record-truncation artifact, corrected once `/land-scout` used exact server-side counts.) Mailing addresses are free but phones aren't → direct mail is the free auto-scale channel, cold calls need a skip-trace step.

**Alternatives considered:** (1) Zillow/portal scraping per the doc — rejected, blocked + ToS-hostile + wrong source. (2) Forsyth as launch market (Brian's first pick by familiarity) — rejected on the data (no absentee seller pool). (3) Out-of-state honey-hole (Lehigh Acres FL) — deferred; Bartow keeps it in-state and the model works there. (4) Paid stack (PropStream/Buyer Bridge/bulk SMS) from day one — deferred until deals validate the model.

**Owner:** Brian Norton


## 2026-06-24 — LOI Submitted: 641 Powder Springs St, Smyrna GA

**Offer:** $910,000 ($65K/unit) vs $1,500,000 ask
**Rationale:** DSCR-anchored ceiling. Stabilized IRR 23.3%, EM 3.21x at $910K. Property is 57% occupied (43% vacant, 1 delinquent unit). Bridge financing required. Offer is $590K below ask — Andy Lundsberg price-check call recommended before sending. Turnover corrected to JB standard ($5,250/yr); expense ratio 45% — within range for 1965 vintage.
**Special condition added:** T-12 within 3 days of acceptance + rent roll warranty at closing.
**LOI Doc:** https://docs.google.com/document/d/1pthPLPpcpeasv_JwAsF2NvfnMRddQSDV4p2pHaZhgSs/edit
**PDF:** https://drive.google.com/file/d/1JvCObDVqzS9QP4Li5fc0gwKrTKGEGFEM/view?usp=drivesdk

---

## 2026-06-24 — Side deal (personal): Dempsey estate auction flip analysis

**Decision:** Worked up a full flip analysis for the Richard Cole Estate absolute auction (Dempsey Auction, Cartersville/Bartow GA, Thu 6/25/26). For every lot: current bid, max hammer (walk-away), marketplace + viable sale price, time-to-sell, and margin at the low value estimate. Deliverables on Desktop: dempsey-auction-MASTER-workup.md + .pdf.

**Why:** Personal side hustle, NOT Olive Tree multifamily pipeline. Method: max hammer anchored to conservative (low-end) resale, then ~65–70% buffer, then back out 10% buyer's premium + 7% tax (GATE card exempts farm items). Confirmed specs: Ram 3500 = diesel; CAT 420 = 264 hrs (near-new); JD 5115M = 458 hrs; JD 333G = 290 hrs. Low hours made the CAT 420 the top play (+$8,800 margin at low est.), followed by 333G, 5115M, CLS63, Ram diesel.

**Alternatives considered:** Facebook Marketplace for everything — rejected for watches (Chrono24/r/Watchexchange net more) and firearms (FB-banned → GunBroker/Armslist/FFL). Most common firearms already bid past flip-viable; money is in 6 Browning/Benelli/S&W sleepers.

**Owner:** Brian Norton (personal)

---

## 2026-06-26 — Launched Multi-Agent Paper Trading Desk

**Decision:** Built a 5-agent paper-trading system inside the AIOS as a new vertical. Paper-only until a strategy survives walk-forward backtest + sustained paper performance + Brian's explicit go-ahead.

**Stack:**
- Broker: Alpaca paper (`paper-api.alpaca.markets`) — free, stocks + crypto
- Data: Polygon (equities history) + Alpaca (crypto + live quotes)
- Backtest: vectorbt walk-forward (70% IS / 30% OOS)
- Research: Claude Haiku (~$0.01–0.03/cycle) → ranked JSON theses
- Alerts: iMessage via existing `notify.sh` (no Twilio)
- Uptime: `caffeinate -i` wraps loop cycles (no daemon)

**Risk ceiling (Conservative):** −1% stop per position, −2% daily portfolio halt, 5% max position size, 5 max concurrent positions.

**Universe:** ~20 liquid US large-caps/ETFs (SPY, QQQ, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA + 12 more) + BTC/USD, ETH/USD overnight.

**Agent pipeline:** Research → Quant gate → Risk veto → Execution → Equity snapshot.

**Entry point:** `python3 scripts/trading_orchestrator.py --once --dry-run` (dry run), `--once` (live paper), `caffeinate -i python3 scripts/trading_orchestrator.py --loop` (continuous).

**Why:** Stocks + crypto is a 24/7 income stream candidate that reuses existing AIOS infrastructure (Anthropic key, Polygon key, SQLAlchemy DB, notify.sh, skill pattern). Paper-first policy prevents any real capital risk during POC. Walk-forward gate is the anti-overfitting defense — a strategy must pass OOS before it ever touches execution.

**Real money checklist (do NOT skip):** 2+ weeks sustained paper performance (Sharpe > 0.5, max DD < 10%) + walk-forward confirmed + risk ceiling re-approved + live Alpaca keys generated + `_PAPER = True` changed in `trading_execution.py` + Brian explicitly says go.

**Owner:** Brian Norton

## 2026-06-29 — Evaluating Paid Parcel Data for Multi-County Land Expansion

**Decision:** Pursue a paid parcel-data API to scale land wholesaling beyond Bartow — **ReportAllUSA first**, Regrid as fallback. Both free 30-day trials; sales-question drafts staged in Gmail (not sent).

**Why:** Ranked GA exurban land-flip markets by builder demand + cheap basis + absentee pool: top new adds are Carroll (30180), Paulding (30157), Barrow (30680), Spalding. But none are auto-scoutable — their ArcGIS Online parcel layers are geometry-only (Paulding/Barrow) or wrong state (the only "Carroll" AGO layer is Carroll County MD). Owner/mailing/value data for these counties lives in Schneider/qPublic, which `land_parcels.py` can't reach. Bartow works only because its ParcelInfo layer bundles CAMA inline.

**Cost picture:**
- Regrid Data Store (per-record ~$0.15/parcel): ~$4.5K–$11K per full county — dead on arrival.
- Regrid API: $500–$2K/mo flat, nationwide; owner mailing = premium (~$1K+/mo). 30-day free trial, no card.
- ReportAllUSA API: unpublished/sales-quoted but historically the budget option; owner mailing is STANDARD (not paywalled), queries by county FIPS + spatial filter (matches our zip pipeline). 30-day free trial.

**Plan:** Run ReportAll's free trial → pull vacant + out-of-state + 1–10 ac for the 4 counties, cache to olive.db, cancel before billing. Fall back to Regrid only if ReportAll's GA data is thin. Wiring lift ≈ 40 lines: a REGRID/REPORTALL source path in `land_parcels.py` feeding the existing normalize/filter pipeline.

**Interim (free, today):** Stay in Bartow, widen to the buy-box "Watch" zips 30184 (White) + 30137 (Emerson) — same reachable GIS.

**Owner:** Brian Norton

## 2026-06-29 — Land Wholesaling: 6-State Southeast Expansion Target List

**Decision:** Expand the land-wholesaling vertical beyond GA to a 6-state Southeast footprint (GA, AL, NC, SC, TN, KY). Researched and ranked top exurban counties by the buy-box test: cheap rural 1-10 ac + active builder demand + out-of-state absentee pool. Updated both parcel-data vendor drafts (Regrid, ReportAll) to this multi-state scope.

**Target counties (~19, by state):**
- GA: Carroll (30180), Paulding (30157/30132), Barrow (30680), Spalding (30223/30224)
- AL: Baldwin inland (36567/36576/36580/36551) ⭐, Autauga (36067/36066/36068) ⭐
- NC: Stanly (28001/28127/28071) ⭐, Rowan (28147/28144/28023/28039), Franklin
- SC: Lancaster ⭐, Cherokee (Gaffney), Berkeley (Moncks Corner)
- TN: Wilson (37090/37087/37184), Rutherford (37128/37130/37060)
- KY: Bullitt (40165/40047), Nelson (40004/40013) ⭐, Warren (Bowling Green), Scott (Lexington)

**Cheapest basis (⭐ = best wholesale spread, $8-20K/ac):** AL Baldwin inland, AL Autauga, NC Stanly, SC Lancaster, KY Nelson. Pull these first on trial day-one. TN is solid but pricier ($15-30K/ac) → thinner spreads, lower priority.

**Why this strengthens the paid-data decision:** ~19 counties across 6 states is unmanageable via per-county ArcGIS scrapers (most use qPublic/Schneider = unreachable; the few AGO layers are geometry-only, already proven with GA Carroll/Paulding/Barrow). ONE Regrid or ReportAll subscription covers all 6 states nationwide. Free 30-day trial validates at $0 before paying. Wiring lift unchanged: one normalize path in land_parcels.py feeds the existing filter pipeline.

**Source:** Perplexity sonar-pro market research (builder demand + land pricing + absentee patterns), 2026-06-29. None GIS-confirmed yet — trial data settles final per-county viability.

**Owner:** Brian Norton

## 2026-06-29 — Trading desk: dedup + stop-loss fixes
- **Bug 1 (concentration):** orchestrator re-bought the same symbol every cycle (6× Visa) because the MAX_POSITIONS check counts Alpaca positions, and Alpaca nets repeat buys into one. Fix: skip any thesis whose symbol is already an open position in our DB (`trading_orchestrator.py`).
- **Bug 2 (inverted stops):** `sync_fills` only recomputed entry/stop on a status-string change, and `get_orders()` returned open-only — so stops went stale vs. the real fill and landed above entry on down-moves. Fix: status=ALL + recompute entry/stop from fill on every sync (`trading_execution.py`).
- Repaired 2 live inverted stops (positions #6, #8 V) to entry×0.99.
- Open question: trim the 6-deep Visa stack (~$30K concentrated)? Pending Brian.

## 2026-06-29 — Quant gate: minimum-trades floor
- Added MIN_OOS_TRADES=5 to the quant gate (`trading_quant.py`). A backtest that made only 1-2 trades (rode one trend, 100% win, huge CAGR) is luck, not signal — it can no longer pass.
- Factored pass logic into `passes_gate()` + added `--test` self-check (fluke rejected, valid sample passes).
- Cleared phantom 1-share SPY DB row (#1, never in Alpaca).
- Watchlist re-test: SOXL (3x, 28% DD) and DTCR now correctly fail. Survivors: AMAT, LRCX, MRVL, MU, UFO.

## 2026-06-29 — Trading desk: stops were never sent to Alpaca + win-rate visibility
- **Trigger:** Added backtest-vs-realized win-rate reporting (`trading_report.py --win-rates`, also in `--print`) with plain-English metric definitions. It immediately exposed a 70% backtest win rate vs 20% realized, profit factor 0.06.
- **Diagnosis:** The 5 "losses" were not a strategy failure — they were ONE over-concentration in Visa (5 long V entries, one per hourly cycle on 6/29), all dumped at once by a manual trim at 20:45 (price 342.0). Win-rate table was an artifact of that single bad decision split across 5 rows.
- **Bug A (concentration):** Already fixed — `held_symbols` guard at `trading_orchestrator.py:117` skips any symbol already held. The 5 V trades predate it.
- **Bug B (stop never enforced) — THE REAL FIX:** `submit_order` only sent a market entry; the −1% stop was computed, stored in the DB, and printed, but **no stop order was ever submitted to Alpaca.** That's why V rode 350→342 (−2.29%) past a 346.5 "stop." Fix: `sync_fills()` now places a working GTC stop order on Alpaca once the real fill price is known (`_ensure_stop_order`, idempotent, equities only). Losses are now capped at −1% server-side instead of running unbounded.
- **Key reframe:** the strategy edge was never disproven — the execution/risk layer was leaking. Surfacing win rates before adding any new strategy (chose this over Fibonacci/more indicators) is what found it.
- **Open follow-ups:** (1) crypto stops — Alpaca rejects stop orders for crypto; those need monitor-based exits. (2) Reconcile stop fills → auto-mark position closed + compute P&L (currently relies on manual trim). (3) Re-judge realized win rate after a real sample of stop-protected trades accumulates.
- **Owner:** Brian Norton

## 2026-06-29 — Trading desk: stop-fill reconciliation + crypto stops shipped
Closed the three follow-ups from the stop-loss fix:
- **(2) Stop-fill reconciliation:** `sync_fills()` now closes a position when its stop order fills — `_close_position()` records exit price, time, and realized P&L via the pure, tested `_compute_pnl()` (`--check-pnl` self-check). Also fixed a latent bug: the entry-reconcile block ran for *every* filled order, so a stop fill would have overwritten `entry_price`; it's now gated to `order_type="market"`.
- **(1) Crypto stops:** Alpaca rejects resting stop orders for crypto, so `check_crypto_stops()` checks live price vs the stored stop each cycle and fires a market exit if breached (tagged `order_type="stop"`, idempotent). Wired into `run_cycle()` before `sync_fills()`, so both equity resting-stop hits and crypto synthetic exits close through the same reconcile path.
- **(3) Re-judge win rate:** no code — run `trading_report.py --win-rates` once stop-protected trades accumulate a real sample.
- Verified: imports clean, both self-checks pass, crypto monitor runs clean against live DB (0 open positions).
- **Owner:** Brian Norton

## 2026-06-29 — Trading desk was live but running 2-day-old broken code
- **Runtime:** launchd `com.olivetree.trading-desk` (KeepAlive + RunAtLoad + caffeinate -i) runs the orchestrator loop continuously — but only while this Mac is on/awake. Cloud blocks market-data APIs, so it can't move off this machine.
- **Found:** the live process (PID 99110) started Jun 27 and was running stale code — none of the 6/29 stop/reconcile fixes were loaded — and erroring every crypto cycle with `invalid crypto time_in_force`. Root cause: entry order hardcoded `TimeInForce.DAY`; Alpaca requires GTC for crypto. Fixed `submit_order` to use GTC for `/`-symbols (`trading_execution.py`). Verified directly: DAY rejected, GTC accepted.
- Reloaded the launchd job → fresh process (PID 37777) now runs today's code at the plist's intended 300s interval (was stale at 3600s).
- **Owner:** Brian Norton

## 2026-06-29 — Trading desk: holiday-aware sessions, live logging, unified stops
- **Holiday-aware market hours:** `is_market_open()` now reads Alpaca's `/v2/clock` (knows holidays + half-days) with the old weekday-window kept as a network-failure fallback (`trading_data.py`). Fixes the latent bug where Fri Jul 3 2026 (NYSE closed for Jul 4) would have switched to equities and rejected every order all day. Verified: clock returns is_open=False overnight, next_open next weekday 09:30 ET.
- **Live log visibility:** added `PYTHONUNBUFFERED=1` to the plist so cycles stream to the log instead of block-buffering (looked empty between cycles before).
- **Stops reworked — resting stops don't work for this book.** Watching a live cycle caught `fractional orders must be DAY orders`: Alpaca won't hold resting stop orders for crypto OR fractional-share equities, and the risk sizer produces fractional qty. Replaced the resting-stop path (`_ensure_stop_order`, deleted) with one unified `check_stops()` — monitor-based for ALL positions: compare live price to stored stop each cycle, fire a market exit on breach (DAY for equities, GTC for crypto). Called each cycle before `sync_fills()`.
- **Known ceiling (documented in code):** monitor stops protect per-cycle (~5 min) and only while the desk runs; a between-cycle gap or a sleeping Mac leaves positions unguarded until the next check. Equity exits fill only in market hours; after-hours breaches retry until open.
- Session-switch confirmed: `--market-session auto` re-evaluates every cycle, so it flips equities↔crypto automatically at 09:30/16:00 ET.
- Verified: imports clean, `--check-pnl` passes, live cycle runs clean (no fractional-stop error), open V/SPY stops monitored without firing.
- **Owner:** Brian Norton

## 2026-06-29 — Trading desk: 60s stops (cost-decoupled) + session-close reports
- **60s stops without 5× cost:** each cycle calls Claude Haiku (research) + Polygon data, so running the whole loop at 60s would 5× LLM/data spend (~$19→~$95/mo on Haiku) and risk Polygon rate limits. Instead split the loop: research/quant stays at `--interval 300`, stops enforced every `--stop-interval 60` in between (just one quote per open position, ~free). `sync_fills()` only runs when a stop actually fires. One process, no new files, no DB concurrency. Net: 5-min → 60-sec stop protection, LLM cost unchanged.
- **Session-close/switch reports:** none existed (alerts were only HALT/per-order/ERROR). Added `send_session_report()` — on every equities↔crypto flip (market open 09:30 / close 16:00 ET) it texts equity, today's P&L, trades closed today (count/wins/net $), and open positions. Wired into the loop via last-session tracking.
- **Crypto trade texts:** confirmed already working — the per-order `send_alert` is session-agnostic, fires on any filled order incl. crypto. Sent a test iMessage to confirm the channel is live.
- Verified: imports clean, live loop runs `research=300s, stops=60s`, inner stop loop error-free past 60s.
- **Owner:** Brian Norton

## 2026-06-30 — Land builders: Google Places over BBB for lead discovery
- **Question:** scrape the Better Business Bureau to auto-populate viable builders (full contact + into the sheet)?
- **Decision:** No BBB. Built `--discover-builders [zip]` on the **Google Places API (New)** instead.
- **Why BBB lost:** (1) no email published — BBB gives name/phone/address/site only, so it never delivered "full contact info" anyway; (2) Cloudflare anti-bot 403s the sandbox (same class as Crexi/LoopNet/Zillow) → needs a paid proxy to run reliably; (3) ToS prohibits automated collection. Google Places is an official API — no 403 games, official quota, returns the same fields BBB would minus the accreditation badge.
- **Cost:** $200/mo free credit, ~2 calls/zip → effectively $0/mo. Key in `.env` as `GOOGLE_MAPS_API_KEY`; Places API (New) enabled on GCP project 693920842531.
- **Scope kept lazy:** discovery only feeds *leads* (name/phone/city/website) as `Tier=unverified` rows. Buy-box fields (price/acre, lot band, conditions) stay blank — those come from the call, so `/land-sellers` and `--price-for` ignore unverified rows. Dedups by phone (one builder, not one row per community). Verified live on 30120: 20 clean leads after phone-dedup + no-phone filter.
- **Skipped, add when needed:** county building-permit discovery (higher signal = *active* permit-pullers, but per-county parsing); email enrichment (no clean free source).
- **Owner:** Brian Norton

---

## 2026-07-01 — SE land-flip re-evaluation: 12 candidates logged; data-scout blocked on vendor quota

**Decision:** Re-ranked the top Southeast land-flipping zips (full 6-state+FL scope) and logged 12 as `CANDIDATE` rows to the Land Markets tab. Two distinct strategies surfaced and are tagged per row:
- **STRAT-A** — exurban acreage (1–10 ac), the proven Bartow model: Hall/30506, Maury-TN/38401, Jackson-GA/30549, Limestone-AL/35611, Johnston-NC/27520, Paulding/30157, York-SC/29730.
- **STRAT-B** — uniform platted small-lot (0.2–0.5 ac), highest-volume land-flip meccas: Marion-FL/34472 (Ocala), Lee-FL/33972 (Lehigh Acres), Charlotte-FL/33948 (Port Charlotte), Citrus-FL/34434. Horry-SC/29526 (Conway) straddles both.

**Blocker (external, not code):** Data-verified scouting (real vacant/absentee counts) is blocked — the **ReportAll free trial hit its all-time 1000-request quota**. Regrid has no key/trial started. Free ArcGIS reaches only ~3 GA counties, all geometry-only (no owner/mailing → can't compute the absentee pool). Every path to finish now costs money.

**Brian's call:** Pause the data spend — the 12 ranked candidates are enough for now. Revisit a paid parcel feed later.

**Shipped anyway (free, push-button for when quota returns):** Wired a `--source reportall` path into `land_markets.py` (`screen_zip_reportall`) so any unwired SE county scouts by zip via ReportAll, reusing the existing normalize/filter/stats pipeline. Bills per parcel returned → `--cap` guards it (default 2000); Total/Vacant counts left blank (no free count-only endpoint); `Vacant Out-of-State` is the capped in-band pool (a floor if cap is hit). Offline mapping test passes; dispatch verified to route correctly (dies only at the 429 quota boundary). Doc updated in `land-scout/SKILL.md`.

**Next when unblocked:** email support@reportallusa.com for a quota bump / paid quote, then run the 12 zips with one command each.

**Owner:** Brian Norton

---

## 2026-07-01 — Trading Desk: 15 positions @ 4%, add 6 ETFs on a 730d gate

**Decision:** Raised the paper trading desk's concurrent-position cap from 5 → 15 and cut per-position size from 5% → 4% of equity (15 × 4% = 60% max deployed, 40% cash buffer). Added a top-rated ETF set — IWM, VTI, SCHD, VUG, XLK, GLD — evaluated every equities cycle alongside the day's top-15 S&P movers. ETFs run the quant walk-forward on a 730d window (vs 365d for stocks); theses are conviction-sorted so the best fill the 15 slots. Stops (−1%) and daily halt (−2%) unchanged.

**Why:** Brian wanted broader coverage (S&P + top ETFs) and more names held, with size dropped to stay manageable. At the default 365d window 0/12 candidate ETFs cleared the gate — not on quality (Sharpe 3–4) but on trade count (1–4 trades < the 5-trade sample floor), same issue crypto hit on daily bars. A 730d window fires enough trades: 6/12 pass. Kept only those 6.

**Alternatives considered:** (a) Diversifiers only (GLD + SCHD) — leaner, less redundant beta; (b) drop ETFs entirely. Brian chose all 6 that pass at 730d for max coverage. Noted risks: the 6 passes are regime-favorable (fail at a 3yr window / through 2022) and 4 of them (IWM/VTI/VUG/XLK) are equity beta overlapping the S&P names — GLD is the one true diversifier. Rejected lowering MIN_OOS_TRADES (would defeat the significance guard).

**Owner:** Brian Norton

## 2026-07-06 — Trading desk split into two $50k books + covered-call trader shipped

**Decision:** Split the $100k paper account into two $50k books on the same Alpaca account: (1) the momentum desk, now sizing off `min(equity, $50k)`, and (2) a new covered-call income book (`scripts/trading_covered_calls.py`) — pure rules, no LLM cost.

**Covered-call rules (best-practice consensus):** 100-share lots of quality names (20-name universe, 100 shares ≤ $25k), sell 30–45 DTE calls at ~0.25Δ (0.20–0.30 band, 4% OTM fallback), min 10% annualized premium yield, max 3 underlyings, 10% cash buffer. Close at 70% profit captured; roll at ≤21 DTE net-credit-only; NEVER sell a strike below cost basis; wheel via ~0.25Δ cash-secured puts on assignment. Income target $500+/mo. Runs inside the orchestrator equities loop at most every 4h (`--no-cc` to disable).

**Momentum upgrades (aimed at the realized-win-rate gap):** ATR(14)×1.5 stops clamped 1–3% (replaces the fixed −1% whipsaw stop), breakeven at +1R then high-water trailing (ratchet-only), SPY 200d-SMA regime filter (fail-flat on data errors — no new entries either direction).

**Book isolation:** symbol-partitioned; each book excludes the other's live Alpaca positions + open orders (option orders block their underlying via OCC parse). Daily −2% halt stays whole-account.

**Process:** designed on Fable, built by a Sonnet subagent, money-path review by an Opus subagent (9 findings: 3 HIGH — fill-confirmation before DB writes, per-leg crash recovery, P&L booked at mid vs ask — all fixed and re-verified). All order legs now confirm fills via poll→cancel→recheck before any DB/ledger write.

**Verified:** risk tests 7/7, CC self-checks 5/5, dry-run cycles clean, `_PAPER=True` everywhere. launchd job restarted 2026-07-06 12:33 ET on the new code — first cycle logged the book split + RISK-ON regime.
