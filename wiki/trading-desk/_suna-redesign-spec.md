---
type: trading-spec
title: Premium Desk v3 — Suna-Method Redesign Spec
status: BUILT 2026-07-10 — live under launchd --suna, trades from Mon 2026-07-13
generated: 2026-07-10
source: wiki/trading-desk/kenneth-suna-site/covered-calls-explained.md + kenneth-suna/* videos
---

# Premium Desk v3 — Suna-Method Redesign

Re-points the paper desk from a mechanical CSP-first monthly wheel to Kenneth Suna's
discretionary-but-ruled **weekly, share-first income wheel**. Almost all plumbing is
reused; this is a rules/parameter redesign plus two new modules.

## Goal
**$1,000/week premium** (≈ $4,333/mo, ~104% annualized) on the $50k CC/wheel book.
Aggressive stretch goal; honest base case 15–35% annualized until paper proves the pace.
Weekly is the primary unit — `--status` leads with premium WTD vs $1,000.

## Locked decisions (Brian, 2026-07-10)
1. **Cadence:** WEEKLY (5–7 DTE calls), true Suna. ~4x more cycles/turnover than the old 30–45 DTE.
2. **Delta stance:** INCOME-FIRST — sell ~0.45Δ, one strike OTM; assignment is welcome, not avoided.
3. **Sell-fear vs breaker:** redesign for the Suna method. Resolved by splitting two events:
   - The anomaly breaker guards **unexplained equity moves with no trade activity** (the $100k→$3.5k
     data glitch). It STILL halts those.
   - A **normal market selloff** (equity moved because positions moved — fully explained by marks/fills)
     is NOT an anomaly. It becomes a GREEN LIGHT for fear-inflated CSPs, Suna's highest-edge entry,
     with his hard gap-risk check + tighter size. Same guard, sharper definition.

## The weekly cycle

```
trading_orchestrator.py  (unchanged entry point)
  ↓ trading_guard.py            — anomaly breaker FIRST; halts only UNEXPLAINED moves (unchanged)
  ↓ trading_suna.py  (NEW driver, active under --suna)
       ↓ 0. DISCOVER  → movers scan (NEW, Mondays): Alpaca screener most-actives + movers
                         (gainers AND losers) → rebuild the week's candidate pool
       ↓ 1. UNIVERSE  → premium-band rank (NEW): rank pool by THIS WEEK's call premium ÷ price;
                         keep 0.8–2.5%, PAUSE >3%, skip <0.8%
       ↓ 2. ENTRY-GATE→ entry-timing filter (NEW): skip names that already ripped this week;
                         require pullback/consolidation
       ↓ 3. ENTER     → share-first: buy 100sh lot, sell 1-strike-OTM WEEKLY call (~0.45Δ)
       ↓ 4. MANAGE    → Wed-close check: >$1 ITM → roll out+up net-credit only, else ride to Fri
       ↓ 5. WHEEL     → assigned → sell CSP at repurchase price; skip token-premium far-OTM puts;
                         sell into post-selloff fear when breaker confirms market- (not data-) driven
       ↓ 6. REPAIR    → underwater lot → ladder strikes a few $ OTM, step up weekly toward basis (NEW)
  ↓ trading_report.py           — equity curve + premium WTD/MTD vs target (unchanged)
```

## Step 0 — Movers discovery (the piece that makes it truly Suna's hunt)

Replaces the frozen 38-name blue-chip list with a weekly-rebuilt pool, mirroring Suna's
CNBC-movers workflow — but sourced natively from Alpaca (our existing data provider, free).

**Source (Alpaca screener, free tier):**
- `GET /v1beta1/screener/stocks/most-actives?top=100` — by volume/trade count
- `GET /v1beta1/screener/stocks/movers?top=50` — top gainers AND losers (Suna explicitly hunts droppers)

**Pipeline each Monday pre-market:**
1. Pull most-actives + movers → raw ticker pool.
2. Hard filters (reject junk automatically):
   - Optionable with **weekly** expirations listed.
   - Price band $10–$100 (100sh lot ≤ $10k position cap → ≤ $100/share).
   - **Options liquidity floor** (NEW, important — movers surface illiquid meme names the blue-chip
     list never did): min open interest + min daily option volume + bid/ask spread ≤10%. No thin chains.
   - Earnings filter (existing): no earnings before expiry + 2 days.
3. Premium filter: this-week's 1-strike-OTM call pays **0.8–2.5%** of price (the sellable band).
4. **Droppers** get the optional Haiku event-screen: **structural** bad news ("sales slow for
   several quarters" → reject) vs **transient** ("one-off miss" → keep, overreaction can snap back).
   This is the one part of Suna's judgment that needs an LLM (~$0.01–0.03/scan).
5. Dedup against names already held; **merge** with a small vetted core (keep ~10 liquid staples as a
   stability floor) → the week's candidate pool, capped at ~25 names.

Result: the universe rebuilds itself weekly from real market movers instead of a frozen list —
Suna's actual hunt, not just his rules on our old list.

## Parameter diff (v2 → v3)

| Lever | v2 (today) | v3 (Suna) |
|---|---|---|
| Universe | Fixed 38 blue-chips | **Weekly movers pool** + ~10 vetted core |
| Discovery | Sort static list | **Alpaca most-actives + movers scan** |
| Rank by | IV-rank 40–70 | **Weekly premium-band (0.8–2.5%, >3% pause)** |
| Cadence / DTE | 30–45 DTE, manage 21 | **Weekly, 5–7 DTE** |
| Entry direction | CSP-first | **Share-first**, CSP post-assignment / into fear |
| Call delta | 0.30Δ (retain) | **~0.45Δ, 1-strike-OTM** (income-first) |
| Roll trigger | 21 DTE ITM up-and-out | **Wed close >$1 ITM → roll, else ride** |
| Underwater | unspecified | **Repair ladder** |
| Liquidity gate | (universe was pre-vetted) | **OI + volume + spread floor** on discovered names |

## Reused unchanged
`trading_guard.py` (anomaly breaker), `trading_report.py`, `trading_data.py` (Alpaca SIP+OPRA),
options-chain/greek fetchers, earnings filter, ex-div check, `_PAPER=True` hard lock,
−2% daily halt, $10k/underlying, 8 names, 2/sector, 5% cash buffer.

## New code (BUILT 2026-07-10)
- `scripts/trading_movers.py` — Alpaca screener discovery (most-actives + gainers/losers), denylist/price/dedup filters, `--test`.
- `scripts/trading_suna.py` — weekly SHARE-FIRST driver: SYNC(reused)→MANAGE→COVER→ENTER→WHEEL, with premium-band gate, entry-timing filter (`already_ripped`, 5-day return), ~0.45Δ weekly-call pick, Wednesday ITM roll, repair ladder, liquidity floor, `--test`/`--discover`/`--once`.
- `--suna` wired into `trading_orchestrator.py` (`_maybe_run_cc` picks the v3 driver); launchd plist updated to `--loop --suna`.
- Weekly target `$1,000` applied in `trading_covered_calls.py`; `--status` leads with premium WTD.

**Structural-drop screen (BUILT):** `structural_drop_screen()` in trading_suna.py runs a Haiku read on any meaningful dropper (`source==losers` or daily ≤ −8%) that clears every cheap filter, classifying the drop as **structural** (deteriorating business → skip) vs **transient** (overreaction → buy the dip). Lazy + per-cycle-cached so only names we'd actually buy cost tokens (~$0.01–0.03 each); fail-open on any error so it can never block the desk. Live-verified (INTC→structural, PLUG→transient).

**Validation done:** both `--test` self-checks pass; live `--once --suna` runs SYNC + skips correctly with market closed; entry logic traced end-to-end (SOFI → $19 weekly call, 0.46Δ, 2.55% premium, in-band).

**Code review (2026-07-10):** APPROVED, 0 critical, 4 warnings — all resolved. (1) partial-roll now books the buyback + clears the option before the new sell; (2) per-sector cap skips the "Unknown" bucket so off-universe movers aren't throttled to ~2/cycle; (3) `_DROP_CACHE` cleared each cycle; (4) cash math reconciled — `_book_available()` = notional $50k − committed − buffer, capped by real `buying_power`, replacing the double-counting `_free_cash` (live: $36k available vs $11.4k deployed, deployment unblocked).

## Validation before real-money talk
- `--test` assert-based self-check (no network) for each new rule.
- `--backtest` weekly-rules replay over stored history — see the churn/assignment profile
  (v3 turns over ~4x v2; needs proof the net survives capped-upside + debit rolls).
- 2+ weeks paper at ≥ $1,000/week pace, no unresolved anomaly halts.

## Open questions / risks
- $1k/week ≈ 2%/week gross — top of Suna's aggressive band. Net will run below gross after
  assignment give-back. Watch WTD actuals vs target.
- Movers pool raises single-name blowup risk vs blue-chips → the liquidity floor + $10k cap +
  event-screen are the mitigations. Revisit if a discovered name gaps through a CSP strike.
- Alpaca screener coverage vs CNBC's list — validate they surface the same high-vol names Suna trades.
