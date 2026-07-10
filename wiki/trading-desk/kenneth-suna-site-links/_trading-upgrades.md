---
type: trading-video-synthesis
title: Trading Strategy Upgrade Proposals from Kenneth Suna Videos
generated: 2026-07-10
source_videos: 16
candidates_considered: 1
status: AWAITING BRIAN'S APPROVAL — no strategies modified
---

# Premium Desk Strategy Upgrades — PROPOSAL

**Base strategy:** Brian Norton's $50k covered-call + CSP wheel (target ~$1,250/mo premium)
**Status:** Awaiting Brian's approval before implementation
**Source pool:** 16 Kenneth Suna videos (1 usable candidate extracted; see note below)

---

## ⚠️ Data Note
Only **1 of 16** candidates was included in the payload. This ranked list reflects the single actionable item provided. The remaining 15 slots are empty — recommend re-running extraction to fill the pipeline before Brian reviews a "final" doc.

---

## Ranked Upgrades

### #1 — Trading-Desk: Dividend Safety Pre-Screen for CC/CSP Underlyings
**Why it matters:** A dividend cut on a wheel underlying triggers a price gap-down that can blow through your CSP strike or trap assigned shares below cost basis — directly threatening the $1,250/mo premium base.

**Paste-ready rule:**
```
DIVIDEND SAFETY SCREEN (apply before any CC write or CSP sale)
Reject underlying if ANY of:
  - Payout ratio > 80% (earnings-based) OR > 100% (FCF-based)
  - TTM free cash flow < declared annual dividend
  - Cash-and-equivalents declining 2+ consecutive quarters
  - Net debt / EBITDA > 4.0x (leverage stress on payout)
Flag (manual review, half size) if:
  - Payout ratio 70–80%
  - Dividend growth streak broken in last 4 quarters

Action on existing positions failing screen:
  - Do NOT roll CSPs; let expire or close
  - On assigned shares: write CCs at/above cost basis to exit
```
**Confidence:** Medium — sound principle, but thresholds are inferred from general commentary, not a stated Norton rule. Calibrate to Premium Desk's actual watchlist volatility before locking numbers.
**Source:** `pIPqH7MNHgI` — "Is KMI's dividend safe??"

---

## Cannot Rank / Dropped
None from the provided data (single valid candidate).

---

## Recommended Next Step for Brian
1. **Re-extract** the other 15 videos — this doc is not decision-ready with 1/16 coverage.
2. On the item above: approve the **framework** but let the desk **calibrate thresholds** against your current underlyings (a 80% payout cap may be too strict for utilities/REITs you already wheel).

Want me to draft the extraction template so the next batch comes back complete and de-dupe-ready?
