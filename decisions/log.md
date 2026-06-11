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
