---
type: trading-video-synthesis
title: Trading Strategy Upgrade Proposals from Kenneth Suna Videos
generated: 2026-07-10
source_videos: 5
candidates_considered: 7
status: AWAITING BRIAN'S APPROVAL — no strategies modified
---

# Premium Desk Upgrade Proposal — Suna Tactics Applied to $50k CC + CSP Wheel

*Status: DRAFT for Brian's approval. Nothing applied until signed off.*

De-duplicated from 7 raw candidates → **6 concrete upgrades** (1 merge, several tightened). Ranked by leverage on the wheel.

---

## 1. Standardize covered-call strike at one-strike OTM
**Strategy:** covered-calls
**Why it matters:** Captures consistent weekly premium while retaining shares below strike — the core premium-generation lever for the wheel.
**Paste-ready change:**
```
CC STRIKE RULE (default):
- Sell nearest weekly call ONE strike above spot (first OTM).
- Target net premium ≥ $170 / contract.
- If assigned, roll up +$1 strike the following week (e.g., $57 -> $58).
- Only deviate to ATM/ITM under the vol-threshold rule (#4).
```
**Confidence:** High · **Source:** m-c_EHk1tok

---

## 2. Set Schwab default lot method to LIFO
**Strategy:** trading-desk
**Why it matters:** Prevents your oldest, highest-profit shares from being assigned away first — pure risk/tax control at zero cost.
**Paste-ready change:**
```
ACCOUNT SETUP (one-time, per account):
Schwab > Profile > Cost Basis Method > set default = LIFO (not FIFO).
Rationale: on assignment, newest lots are called first; long-held
high-conviction lots (e.g., 180% gainers) are protected.
Verify setting after any new-symbol first purchase.
```
**Confidence:** High · **Source:** m-c_EHk1tok

---

## 3. Predetermined rolling rule for ITM calls
**Strategy:** trading-desk
**Why it matters:** Removes case-by-case discretion; preserves shares and extends premium collection with a mechanical trigger.
**Paste-ready change:**
```
ROLL RULE:
- If short call is >$1.00 ITM by Wednesday close -> roll out (+1 week)
  and up (+1 strike), for a NET CREDIT only.
- If roll cannot be done for a net credit -> accept assignment,
  wheel into CSP (see #5).
- No rolling for a debit to "save" shares.
```
**Confidence:** High · **Source:** ELs2IKme24o

---

## 4. Volatility-threshold on/off switch for CC frequency
**Strategy:** covered-calls / trading-desk
**Why it matters:** Stops selling calls for pennies when IV cools — protects upside and keeps premium-per-risk economical. *(Merged from two candidates: the IV-based "pause" and the vol-based weekly scaling idea.)*
**Paste-ready change:**
```
VOL GATE:
- Compute best-available first-OTM weekly premium each Monday.
- If premium ≥ $170/contract -> sell full size.
- If $50-170 -> half size OR skip that name for the week.
- If < $50 -> do NOT sell calls; hold shares uncapped.
- Redeploy freed capacity to higher-IV wheel candidates.
```
**Confidence:** Med · **Source:** m-c_EHk1tok, Uk4ha1mwznA
*(Note: candidate claimed "$25/week" scaling — kept only the vol-gating logic, which is the transferable part.)*

---

## 5. CSP gap/event-risk filter
**Strategy:** trading-desk
**Why it matters:** Avoids being forced to buy at a strike far above a gapped-down open — the single largest tail risk in the put leg.
**Paste-ready change:**
```
CSP ENTRY FILTER:
- Do NOT sell a CSP if a known catalyst (earnings, FDA, guidance)
  lands before expiry.
- Reject if plausible overnight gap > (strike - premium) - i.e.,
  a realistic bad-open could exceed the entire premium cushion.
- "Would rather miss the $100 than eat the gap."
```
**Confidence:** Med · **Source:** 18mo5UwZkq0
> ⚠️ **Flag for Brian:** the source candidate's "≥0.5% premium" math is self-contradicting ($188/$5,700 = 3.3%, which *passes* a 0.5% test). The real reason Kenneth skipped the trade was **gap risk**, not thin premium. I've reframed the rule around event/gap risk. Please confirm before we adopt any premium-% floor.

---

## 6. Crash-below-entry decision template
**Strategy:** covered-calls
**Why it matters:** Codifies what to do when a holding drops below cost — avoids locking in losses by selling calls below basis.
**Paste-ready change:**
```
UNDERWATER SHARE RULE (spot < cost basis):
- Never sell a call at a strike BELOW cost basis (locks in loss on assignment).
- If no strike ≥ basis pays ≥ $170 -> sit out; hold shares, wait for recovery.
- Log basis, current strike-for-basis premium, and decision each week.
```
**Confidence:** Med · **Source:** r1HJWJNyMVI

---

### Items dropped / not proposed
- None fully dropped, but **#4** absorbed the vague "$25/week scaling" candidate (Uk4ha1mwznA) which had no concrete rule of its own.

### Suggested rollout order
Setup-once first (**#2 LIFO**), then mechanical entry/exit (**#1, #3**), then gating/filters (**#4, #5, #6**). Recommend paper-tracking #4–#6 on HIMS for 2–3 weeks before applying portfolio-wide.
