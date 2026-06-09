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
