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
