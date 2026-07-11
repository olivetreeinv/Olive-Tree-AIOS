---
type: trading-video-synthesis
title: Trading Strategy Upgrade Proposals from Kenneth Suna Videos
generated: 2026-07-10
source_videos: 30
candidates_considered: 1
status: AWAITING BRIAN'S APPROVAL — no strategies modified
---

# Premium Desk Strategy Upgrades — Proposal Doc

> **Note:** Only **1 raw candidate** was included in the payload (not 30). The ranked list below reflects what was provided. I've flagged the gap so we can re-run extraction before Brian reviews a full slate.

---

## Ranked Upgrades

### #1 — Trading Desk: Add SPYD as a High-Yield Wheel Underlying (partial allocation)

**Why it matters:** Raises the passive-income *floor* via a 4.67% dividend yield vs SPY's ~1.42%, supplementing the $1,250/mo premium target with dividends that pay regardless of option outcomes.

**Paste-ready change:**
```
UNDERLYING ALLOCATION (Wheel):
- Core: SPY (liquid options, tight spreads) — 70% of wheel capital
- Yield sleeve: SPYD — up to 20% of wheel capital ($10k cap)
  * Purpose: dividend floor (4.67%), NOT primary premium engine
  * ONLY sell CCs/CSPs on SPYD if bid/ask spread ≤ $0.10 and OI ≥ 500
  * If SPYD option liquidity insufficient → hold SPYD shares for dividend only
- Reserve: 10% cash for CSP assignment buffer
```

**Confidence:** **Low**
**Source:** "SPY vs SPYD" (4Z7lUs8i0so)

---

## ⚠️ Analyst Flags Before Approval

This candidate needs scrutiny — the source video compares dividend yields but does **not** validate it against the actual mechanics of an options-selling wheel:

1. **Options liquidity risk.** SPYD has dramatically thinner options markets than SPY — wide spreads erode premium and make rolling difficult. This can *hurt* the $1,250/mo target more than the dividend helps.
2. **Yield ≠ total return.** A higher dividend often comes with lower price appreciation and no free lunch (price drops ex-div). The 4.67% vs 1.42% comparison is misleading in isolation.
3. **Premium engine, not dividend engine.** The Premium Desk's job is selling premium. Optimizing for dividends is a different mandate; this may be scope drift.

**Recommendation:** Treat as **experimental sleeve only** ($10k cap, hard liquidity gates) or **defer** pending a premium-yield-per-spread analysis on SPYD options chains.

---

## Coverage Gap

I was told upgrades were mined from **30 videos** but received **1**. Before this goes to Brian, please re-supply the remaining 29 candidates so I can:
- De-duplicate across the full set
- Rank by leverage (Greeks/entry rules/sizing likely rank higher than underlying selection)
- Deliver a real "highest-leverage first" doc

As-is, this is a single low-confidence idea, not a strategy overhaul.
