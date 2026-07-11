---
type: trading-video-synthesis
title: Trading Strategy Upgrade Proposals from Kenneth Suna Videos
generated: 2026-07-10
source_videos: 21
candidates_considered: 1
status: AWAITING BRIAN'S APPROVAL — no strategies modified
---

# Premium Desk Strategy Upgrades — PROPOSAL (Brian's Approval Required)

**Scope:** $50k covered-call + CSP wheel | **Source pool:** 1 candidate extracted (note: 20 of 21 video candidates were empty/absent in the payload — see caveat below)

---

## Ranked Upgrades

### #1 — trading-desk: Dividend-ETF Sleeve Alongside the Wheel
**Why it matters:** Adds a lower-volatility, capital-preserving income stream that diversifies away from single-name assignment/concentration risk while the wheel keeps generating premium.

**Paste-ready change:**
```
RULE: Core-Satellite Capital Split (Premium Desk, $50k)
- Core income sleeve: 20–30% ($10k–$15k) in high-quality dividend ETF (e.g., SCHD)
  * Held long, unlevered; collects qualified dividends
  * NOT used as CSP cash-secured collateral
- Wheel sleeve: 70–80% ($35k–$40k) runs covered calls + CSPs as usual
- Rebalance band: if dividend sleeve drifts >±5% of target weight, rebalance quarterly
- Optional: write covered calls on the ETF sleeve only at >30 delta OTM, >30 DTE,
  to avoid capping the dividend-growth thesis
```
**Confidence:** LOW–MED (single source; sizing % is inferred, not stated by Kenneth)
**Source videos:** *How to REALLOCATE Your Portfolio BEFORE you Retire* (`55kRoAKdBZs`)

---

## ⚠️ Data Caveat — Read Before Approving

You stated **21 videos** were mined, but the payload contained **only 1 usable candidate**. I cannot manufacture the other 20 — doing so would violate the "drop anything vague" instruction and risk feeding Brian fabricated tactics.

**What I need to complete this properly:**
- The remaining 20 candidate objects (entry rules, Greeks, sizing tactics, etc.)

## Open Questions on the One Candidate
Before this even reaches Brian, flag these for the analyst:
1. **Sizing source:** "20–30%" appears invented by the extractor, not quoted from Kenneth. Confirm or downgrade.
2. **Collateral conflict:** A dividend-ETF sleeve reduces cash available to secure puts — does this shrink CSP premium capacity enough to offset the diversification benefit? Needs a yield-vs-premium comparison.
3. **Retirement framing:** Kenneth's advice was pre-retirement reallocation. Confirm Brian's Premium Desk shares that risk tolerance before importing a "safer/capital-preservation" tilt into a premium-generation product.

**Recommendation:** Hold this proposal as a **stub** until the full 21-candidate set arrives. One candidate is insufficient to rank, de-duplicate, or lead with "highest-leverage" changes.
