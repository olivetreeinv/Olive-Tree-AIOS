---
name: trading-desk
description: "Paper-trading covered-call/wheel income desk: screener (IV rank + earnings filter + AI event-screen) → CSP-first wheel entries → 21-DTE management → equity anomaly circuit breaker → Alpaca paper execution. Run /trading-desk, 'start the trading desk', 'run a trade cycle', 'show my P&L'."
---

# Trading Desk Skill — Olive Tree Investments — Premium Desk v3 (Suna)

Paper-trading income desk. Covered-call/wheel book is PRIMARY. All paper money until Brian explicitly approves real capital.

## Premium Desk v3 — Kenneth Suna weekly wheel (LIVE since 2026-07-10, trades from Mon 2026-07-13)

The desk now runs **Suna's weekly share-first income wheel** by default (launchd plist runs `--loop --suna`). It supersedes the v2 monthly CSP-first wheel described below, which is still fully wired and runs if `--suna` is dropped. Full spec + rationale: `wiki/trading-desk/_suna-redesign-spec.md`; decision: `decisions/log.md` 2026-07-10. Source: `wiki/trading-desk/kenneth-suna*` (mined from his videos + paid guide).

- **Goal:** $1,000/week premium (weekly is the primary unit; `--status` leads with premium WTD).
- **New code:** `scripts/trading_suna.py` (weekly driver) + `scripts/trading_movers.py` (Alpaca movers discovery). Reuses v2's guard/report/DB/execution primitives.
- **Cycle:** SYNC (reused) → MANAGE (profit-close / Wed >$1 ITM roll) → COVER (weekly ~0.45Δ call, repair-aware) → ENTER (share-first from the movers pool, premium-band 0.8–2.5%, >3% pause, entry-timing filter) → WHEEL (weekly CSP on assigned).
- **Discovery:** rebuilt weekly from Alpaca most-actives + gainers/losers (`trading_movers.discover()`), not the fixed 38-name list. Options-liquidity floor + $10–100 price band + earnings filter cull junk movers.
- **Structural-drop screen:** meaningful droppers get a Haiku "structural vs transient" read before buying the dip (`structural_drop_screen()`) — skips deteriorating businesses, buys overreactions. Lazy, cached per cycle, fail-open.

```bash
python3 scripts/trading_suna.py --test        # offline rules self-check
python3 scripts/trading_suna.py --discover    # this week's movers pool
python3 scripts/trading_suna.py --once --dry-run   # print intended actions, no orders
python3 scripts/trading_movers.py --test      # discovery self-check
python3 scripts/trading_orchestrator.py --once --suna   # one live Suna cycle
```

---

## Premium Desk v2 (still available without --suna)

## Architecture (Premium Desk v2 — since 2026-07-07)

```
trading_orchestrator.py  (entry point — default cycle)
  ↓ trading_guard.py           — equity anomaly circuit breaker (runs FIRST, every cycle)
  ↓ trading_covered_calls.py   — CSP-first wheel cycle (SYNC → MANAGE → COVER → ENTER → WHEEL)
       ↓ trading_screener.py   — IV-rank/richness ranking, earnings filter, optional Claude event-screen
  ↓ trading_report.py          — SQLite equity curve + ntfy/email alerts

--momentum (opt-in, retired by default):
  ↓ trading_research.py   — Claude (Haiku) → ranked JSON theses
  ↓ trading_quant.py      — vectorbt walk-forward gate
  ↓ trading_risk.py       — Conservative ceiling + veto
  ↓ trading_execution.py  — Alpaca paper orders
  ↓ trading_core.py       — SPY core sweep (idle cash → SPY)
```

Shared data layer: `scripts/trading_data.py` — **Alpaca is the sole data source** (SIP equities feed + OPRA options data via `ALPACA_DATA_FEED=sip`). Polygon has been fully removed — canceled after the A/B comparison showed 0.4bps avg diff and 100% quant-gate agreement between the two feeds (see `decisions/log.md`, 2026-07-07).

## Why momentum retired

The walk-forward gate was passing small-sample noise — Sharpe/win-rate stats built on too few OOS trades to trust. The momentum pipeline (research → quant → risk → execution) and the SPY core sweep are still fully wired, just gated behind `--momentum`; nothing was deleted. Re-enable to resume or to run it alongside CC for comparison.

## Premium Desk v2 — CC/wheel book (the primary book, $50k)

`scripts/trading_covered_calls.py`. Pure rules, no LLM cost except the optional `--ai` event-screen pass in the screener.

- **Entries are CSP-first**: `scripts/trading_screener.py` ranks a curated ~38-name liquid-optionable universe by IV richness (true IV-rank once 60d of history is stored, bootstrap ratio before that), filters on price band, option-spread quality, and upcoming earnings (skips if earnings falls before expiry + 2 days). New capital deploys via 0.25Δ cash-secured puts (0.20–0.30Δ band), not by buying shares outright.
- **Covered calls**: sells 0.30Δ calls (0.25–0.35Δ band) against 100-share lots (existing + post-assignment), 30–45 DTE at entry.
- **Management at 21 DTE**: ITM → roll out-and-up for a net credit; OTM and <60% profit captured → roll to the next monthly-ish expiry for a net credit. A debit roll is skipped and left to ride — never rolls for a net debit.
- **Profit-close**: buys back at 60% of premium captured, any time before 21 DTE.
- **Wheel**: assignment → sells CSPs on the assigned underlying to re-enter.
- **Fills**: two-stage — mid for 45s, then falls to the bid, floored at the price implying a 10%-annualized yield. Never sells a strike below cost basis.
- **Optional AI event-screen** (`trading_screener.py --ai`): Claude Haiku flags known binary catalysts (FDA/litigation/M&A/guidance) the earnings-date filter alone can't see.

```bash
python3 scripts/trading_screener.py                      # ranked candidate table
python3 scripts/trading_screener.py --json                # machine-readable
python3 scripts/trading_screener.py --ai                  # + Claude event-screen pass
python3 scripts/trading_screener.py --test                # self-check, no network

python3 scripts/trading_covered_calls.py --status          # CC/wheel book + premium WTD vs $1,000/week target
python3 scripts/trading_covered_calls.py --once --dry-run  # print intended actions
python3 scripts/trading_covered_calls.py --test             # stub-driven rules self-check
```

Orchestrator runs the CC cycle every default cycle (equities + extended sessions only); disable with `--no-cc`.

## Equity anomaly circuit breaker (new — the important one)

**Incident (2026-07-06/07):** the paper account's equity dropped from ~$100k to ~$3.5k overnight with **zero entries** in Alpaca's account activities log — an account/data glitch, not a trading loss. Reported to Alpaca; that paper account is abandoned. `scripts/trading_guard.py` exists so this can never again silently corrupt sizing decisions.

Runs at the start of **every** cycle, before any trading:
1. Fetch `equity` and `last_equity` from `/v2/account`.
2. If `|equity - last_equity| / last_equity > 5%`: fetch `/v2/account/activities` for the gap window, sum the plausible $ impact of fills + non-trade activity.
3. If the unexplained portion of the move is still `> 5%` of `last_equity` → **HALT**: skip all trading this cycle, write `data/trading_halt.json` (reason + timestamps), push an ntfy/iMessage alert via `trading_report.send_alert`.
4. The halt **persists** — checked at the start of every subsequent cycle — until the flag file is deleted or `--clear-halt` is passed.
5. Fails open, not open-to-crash: an Alpaca outage/auth error during the check is treated as "can't judge, don't halt," logged, and the cycle continues — the breaker itself must never become the outage.

```bash
python3 scripts/trading_guard.py --test          # assert-based self-check, no network
python3 scripts/trading_guard.py --check          # one live check against Alpaca
python3 scripts/trading_orchestrator.py --clear-halt   # clear a tripped halt and resume
```

## Run commands

```bash
# Single cycle dry-run — CC/wheel + guard only, no orders:
python3 scripts/trading_orchestrator.py --once --dry-run

# Single live cycle (paper orders), CC/wheel-primary:
python3 scripts/trading_orchestrator.py --once

# Also run the retired momentum pipeline + SPY core sweep this cycle:
python3 scripts/trading_orchestrator.py --once --momentum

# Continuous loop (keep Mac awake):
caffeinate -i python3 scripts/trading_orchestrator.py --loop --interval 3600

# Backtest all symbols, print gate results (momentum pipeline):
python3 scripts/trading_orchestrator.py --backtest-only

# Today's P&L vs SPY + CC/wheel premium + yield-on-book:
python3 scripts/trading_orchestrator.py --report

# Clear a tripped equity-anomaly halt:
python3 scripts/trading_orchestrator.py --clear-halt

# Risk unit tests / equity guard unit tests:
python3 scripts/trading_risk.py --test
python3 scripts/trading_guard.py --test
```

## Universe

**CC/wheel screener universe (~38 names, weeklies-listed, no meme/biotech binaries):** see `SECTOR` dict in `scripts/trading_screener.py` — Technology, Communication Services, Consumer Discretionary, and more, spread across sectors so the max-2-per-sector rule has real breadth.

**Momentum universe (--momentum only):** SPY QQQ AAPL MSFT NVDA AMZN GOOGL META TSLA BRK.B JPM V UNH XOM AMD NFLX CRM ADBE IWM GLD TLT + BTC/USD ETH/USD overnight.

Benchmark: SPY buy-and-hold (shown in `--report`).

## Risk ceiling (Premium Desk v2 — updated 2026-07-07)

| Rule | Value |
|---|---|
| Max position per underlying | $10,000 (≤20% of the $50k CC/wheel book; 100sh lot ≤ $100/share) |
| Max concurrent underlyings | 8 |
| Max per sector | 2 |
| Cash buffer | ≥5% of the CC/wheel book held in cash |
| Option delta targets | Calls 0.30Δ (0.25–0.35 band); CSPs 0.25Δ (0.20–0.30 band) |
| Entry DTE window | 30–45 DTE |
| Management trigger | 21 DTE — ITM rolls out-and-up, OTM rolls to next monthly, both net-credit only |
| Profit-close | Buy back at 60% of premium captured |
| Minimum entry yield | Skip entries yielding < 10% annualized |
| Daily portfolio halt | −2% from day-open equity (whole account) → stop all trading |
| **Equity anomaly breaker** | **|equity − last_equity| > 5% AND unexplained > 5% of last_equity → HALT, persists until cleared** |
| Momentum ceiling (--momentum only) | 4–8% of $50k book per position, 15 max positions, ATR(14)×1.5 stop |

To change ceilings, edit constants at the top of `scripts/trading_covered_calls.py` (CC/wheel) or `scripts/trading_risk.py` (momentum) and log the decision in `decisions/log.md`.

## Goal

**$1,000/week premium** (≈ $4,333/mo) on the $50k CC/wheel book — a ~104% annualized yield-on-book target (Suna-method weekly cadence). This is an aggressive stretch goal: it implies selling near-the-money weekly calls at ~2%/week gross, which in practice means frequent assignment and real capped-upside/drawdown drag. Weekly is the primary unit (`--status` leads with premium WTD vs $1,000); treat 15–35% annualized as the honest base case until paper results prove the pace. Tracked in `--report` and the daily scorecard email.

## Keys required (.env)

```
ALPACA_API_KEY=...        # paper account — NEW account as of 2026-07-07
ALPACA_SECRET_KEY=...     # paper account — NEW account as of 2026-07-07
ALPACA_DATA_FEED=sip      # SIP equities + OPRA options
ANTHROPIC_API_KEY=...     # already set (screener --ai + momentum research, if used)
NOTIFY_IMESSAGE_TO=...    # already set
NTFY_TOPIC=...            # already set — reliable phone push, used by the anomaly breaker
```

**⚠️ Action needed:** the prior Alpaca paper account is abandoned after the unexplained $100k→$3.5k equity glitch (reported to Alpaca, no activity trail found). A **new paper account** was created — paste its key/secret into `.env` before running live cycles. Polygon has been fully removed; `POLYGON_API_KEY` is no longer read anywhere.

## Cost per cycle

CC/wheel cycle: $0 (pure rules) + optional screener `--ai` Haiku pass (~$0.01–0.03).
Data calls (Alpaca): free tier (SIP + OPRA already included on Algo Trader Plus).
Momentum pipeline (--momentum only): Haiku research ~$0.01–0.03/cycle + local vectorbt backtest (free).

## Gotchas

- **Market hours**: `is_market_open()` uses EDT (UTC-4) fixed offset — works Apr–Nov. In EST (Nov–Mar) adjust if cycles run an hour off.
- **Alpaca timestamps**: bars come back as epoch-ms integers in some endpoints, ISO strings in others — `trading_quant.py` and `trading_screener.py` handle both.
- **Crypto Alpaca data**: use `/v1beta3/crypto/us/` endpoint, not `/v2/stocks/`. Symbol format is `BTC/USD` (with slash). Crypto/momentum only matter under `--momentum`.
- **Paper is hard-coded**: `_PAPER = True` in `trading_execution.py` and `trading_covered_calls.py`. Never set to False without Brian's explicit approval and real Alpaca live keys.
- **Claude JSON fences**: Haiku sometimes wraps output in ``` fences despite instructions. `trading_research.py` and the screener's `--ai` pass strip them automatically.
- **caffeinate**: required for `--loop` so macOS doesn't sleep mid-cycle. `caffeinate -i python3 scripts/trading_orchestrator.py --loop`.
- **Equity anomaly breaker fails open on Alpaca errors** — an auth/network failure during the check is logged and trading continues; it only halts when it can positively confirm an unexplained move, since a broken breaker must never itself take the desk down.

## Real money checklist (do NOT skip)

Before switching off paper:
- [ ] 2+ weeks sustained paper performance on the CC/wheel book (premium pace ≥ $1,000/week, no unresolved anomaly halts)
- [ ] Screener candidate quality reviewed — no low-liquidity or earnings-adjacent false negatives
- [ ] Risk ceiling reviewed and explicitly re-approved by Brian
- [ ] Alpaca live keys generated (separate from paper keys) and added to `.env`
- [ ] `_PAPER = True` changed to `False` in `trading_execution.py` and `trading_covered_calls.py` with a `decisions/log.md` entry
- [ ] Brian gives explicit go-ahead in this chat
