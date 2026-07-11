---
type: trading-video-synthesis
title: Trading Strategy Upgrade Proposals from Kenneth Suna Videos
generated: 2026-07-10
source_videos: 52
candidates_considered: 49
status: AWAITING BRIAN'S APPROVAL — no strategies modified
---

# Premium Desk Strategy Upgrades — PROPOSAL (Brian to approve)

**Scope:** $50k covered-call + CSP wheel · Target: $1,250/mo (~$288/week) premium
**Method:** 49 candidates merged into 12 ranked upgrades. Highest-leverage first. Off-strategy/vague ETF-picking items dropped (see bottom).

---

## TIER 1 — Sourcing & Yield Gate (do these first)

### 1. Systematic screener workflow + volatility "rolodex"
**Why it matters:** Replaces ad-hoc stock picking; individual names lose IV over time, so a rotating pipeline keeps premium consistent.
**Paste-ready:**
```
WEEKLY UNIVERSE SCREEN (run Sunday):
  1. Sector filter (tech/growth-lean) → 2. Price $10–$150/share (100 shares = $1k–$15k)
  3. Beta 1.0–2.0  → 4. Short interest 10–30%  → 5. IV Rank > 60%
  Output: rank ~8–10 qualified names by premium-% yield.
  Maintain a 5–7 name "rolodex"; rotate out names as IV decays.
```
**Confidence:** High · **Sources:** l5J9v_Ykeks, 58lcGTl97Jg, CrKJP0Lo4AY, XO4tsH6Mels, Iu3J4KhO0qg, JCTs4QXTIwI

### 2. Minimum premium-to-capital yield gate (reject low-yield trades)
**Why it matters:** Kenneth's own HIMS trade failed at 1% on $5k. A hard floor prevents deploying capital into positions that can't hit $288/week.
**Paste-ready:**
```
ENTRY GATE — reject any CC/CSP unless:
  Weekly premium ÷ capital deployed ≥ 2.0%
  (Kenneth's validated floor: 2.26% on Snapchat; CSP floor 2.0%.)
  If no candidate clears the gate → hold cash, do NOT force a trade.
```
**Confidence:** High · **Sources:** Hq4gacM61gU, I0RHS0i1OHw, r1HJWJNyMVI, 7UFks7QD7mc, JCTs4QXTIwI

---

## TIER 2 — Entry Timing & Risk Control

### 3. Entry-timing filter: no chasing surges, no earnings weeks
**Why it matters:** Selling CCs into a spike caps upside at the worst point; earnings weeks add uncontrollable tail risk (Kenneth's admitted mistake).
**Paste-ready:**
```
SKIP entry if ANY true:
  • Underlying up >10% on the day, OR RSI > 70 → wait ≥5 days / next-week pullback
  • Earnings fall within the option's expiry window → no CSP/CC that week
  • Stock is down "dramatically" on a recoverable catalyst (surge risk against short call)
```
**Confidence:** High · **Sources:** D1UIfiXVu3o, UKu4lUs08G8, T7wgeMJSGoQ, hakKpzx72U0

### 4. Diversify to 3–5 concurrent positions (cap concentration)
**Why it matters:** Single-stock bad news forces long recovery waits; spreading capital stabilizes weekly premium and assignment risk.
**Paste-ready:**
```
POSITION SIZING:
  • 3–5 concurrent CC positions, ~$5k tranches each (100-share lots).
  • No single position > 25% of $50k desk.
  • Optional volatility-tier split: 60% stable-dividend names (1–1.5%/wk),
    40% higher-IV names (3.5–4.5%/wk) → blends to ~$1,250/mo with managed risk.
```
**Confidence:** High · **Sources:** GumGpGQ8yc8, NJFuY_spZXo, tqHoXmj1E4w, Rw_N9lqxN-w, _KuRRTStvKw

### 5. Strike-selection framework (delta/OTM tiering)
**Why it matters:** Balances premium capture vs. keeping shares; conviction level should drive how far OTM you sell.
**Paste-ready:**
```
CC STRIKE RULES:
  • Default: sell $1–$1.50 OTM on high-IV weekly names (Kenneth's baseline).
  • High-conviction / bullish long-term holds: 3–5% OTM (keep upside + premium).
  • Probability-of-keeping-shares blend: ~70% of contracts at ~30-delta,
    ~30% at ≥50-delta for premium boost.
  • Neutral positions you'd exit anyway: at-the-money OK.
```
**Confidence:** Med (candidates give differing OTM specifics — Brian to pick house default) · **Sources:** dWyf9u4zzPI, yJwMge5CUho, sIMNUX_nBok, fOPOWak0abo, eK6LGByAomQ

---

## TIER 3 — Position Management

### 6. Rolling & buyback discipline (quantified triggers)
**Why it matters:** Stops emotional deep-ITM buybacks (Kenneth lost $2,600 chasing a $535 premium) and captures roll credits when future IV is rich.
**Paste-ready:**
```
BUYBACK RULE: only buy-to-close a CC if cost ≤ 20–30% of premium collected.
  Otherwise accept assignment and redeploy.
ROLL RULE: roll out/up when premium ≥2 weeks out exceeds current buyback cost
  by ≥30% (typically earnings/news-driven IV). Take small loss now for larger credit.
REPAIR: if underlying closes >85% of short strike, begin systematic roll-up.
```
**Confidence:** High · **Sources:** NKotIpmszGo, ghsmUm2apjM, 5nNwGFWO5yU

### 7. Post-assignment redeployment loop
**Why it matters:** Keeps the wheel turning — no idle capital after a call is assigned.
**Paste-ready:**
```
ON ASSIGNMENT: next trading day, re-buy shares (or sell CSP), write new CC
  $1–$2 OTM targeting $200–$250/contract. Log assignment-vs-roll each cycle.
```
**Confidence:** High · **Sources:** 18mo5UwZkq0, Rw_N9lqxN-w

### 8. CSP discipline pack
**Why it matters:** Ensures assignment capacity, locks in profits early, and avoids capital traps.
**Paste-ready:**
```
CSP RULES:
  • Hold full cash reserve per contract (e.g., $4,700 for a $47 strike). Non-negotiable.
  • Buy-to-close at 50% of max profit to cut late assignment risk.
  • Reject CSPs returning <2% premium/capital (see Gate #2).
  • No CSPs in earnings weeks.
  • When high-IV name is in a defined pullback, prefer holding dry powder for
    intraweek entry over locking capital in a CSP until Friday.
```
**Confidence:** High · **Sources:** Sj9QUUoXxs4, 7UFks7QD7mc, T7wgeMJSGoQ, Sf5_PcOCqcM

### 9. Intraweek rotation on rallies
**Why it matters:** Adds flexibility to reset strikes when a name runs, recapturing premium quality.
**Paste-ready:**
```
ROTATION: if underlying rallies >5–7% intraweek, consider exiting the CC,
  re-entering after a ~10–15% pullback to reset the strike. Only where liquidity allows.
```
**Confidence:** Med · **Sources:** GumGpGQ8yc8

---

## TIER 4 — Process & Structural

### 10. Formalize the weekly workflow (Sunday research → Monday execution)
**Why it matters:** A repeatable 1-hour cadence produced Kenneth's $600–1,400/wk; Brian's $288/wk target is conservative under the same process.
**Paste-ready:**
```
CADENCE:
  Sunday (20–30 min): run screen (#1), document strike/premium/%-return per candidate.
  Monday AM (30 min): execute refined list; sell weekly (Fri) expiries.
  Log fills vs. plan for consistency tracking.
```
**Confidence:** Med · **Sources:** ri9qTdRWn_I, 6iNlGsIvtQ4, 7ZuI7QPIA1o, M5mQL-VrD_0

### 11. Sell CCs preferentially on positions you'd exit anyway
**Why it matters:** Avoids capping upside on core growth holds; captures premium on names slated for liquidation.
**Paste-ready:**
```
Do NOT write CCs on high-conviction compounders held for appreciation.
Write CCs on positions already flagged for exit → premium is pure upside.
```
**Confidence:** Med · **Sources:** eK6LGByAomQ, TOiDE7kBJ54

### 12. If any ETF sleeve is used: avoid high-fee CC ETFs; recycle premium to quality
**Why it matters:** Single-stock CC ETFs (~1% fee + NAV decay) underperform running the wheel directly; premium is better redeployed to quality dividend/index funds than back into a decaying ETF.
**Paste-ready:**
```
ETF POLICY:
  • Prefer direct stock + CC over single-stock CC ETFs (MSTY/TSLY-type) — fee + NAV decay.
  • If holding any CC ETF for passive sleeve, sweep distributions into SCHD /
    broad index rather than reinvesting into the same volatile ETF.
```
**Confidence:** Med · **Sources:** wb17wPdxzfg, xYHAMt0l1c8

---

## DROPPED (vague / off-strategy for a self-managed wheel)
- **ETF beauty-contest comparisons** — QYLD vs JEPI (XCh01Jacx0M), JEEPQ vs JEPPY (Y1Ear3loycE), SPYI vs QQQI (JXl_W_2ai-c), XYLG/JEPPY (CvZZ94gDI7c), $30k ETF (HDAM-LNH8L8), CONY/TSLY explainer (kSt-0dRRoU4): educational, not actionable wheel rules. Recommend not adding passive ETF sleeves unless Brian wants a separate mandate.
- **"Broadcom/high-priced weekly rotation"** (rfRXK891apY, YRR7HbchoxQ): $44k–$50k per 100 shares blows the diversification cap (#4) on a $50k desk — infeasible at current size.
- **Generic "supplement with more CCs to hit $1,500–2,000"** (Pa4OX6diJqE, UqM-U1xP2_g): aspirational, no concrete rule beyond what #1–5 already encode.

---

**Next step:** Brian selects a house default for #5 strike distance and confirms the #4 tier split, then we codify #1–#8 as hard desk rules and #9–#12 as guidelines.
