---
name: trading-desk
description: "Paper-trading multi-agent system: Claude research → quant walk-forward gate → risk veto → Alpaca paper execution. Stocks during market hours, crypto overnight. Run /trading-desk, 'start the trading desk', 'run a trade cycle', 'show my P&L', 'backtest all symbols'."
---

# Trading Desk Skill — Olive Tree Investments

Multi-agent paper-trading bot. Five scripts, one orchestrator, all paper money until Brian explicitly approves real capital.

## Architecture

```
trading_orchestrator.py  (entry point)
  ↓ research_agent()   scripts/trading_research.py  — Claude (Haiku) → ranked JSON theses
  ↓ quant_agent()      scripts/trading_quant.py      — vectorbt walk-forward gate
  ↓ risk_agent()       scripts/trading_risk.py       — Conservative ceiling + veto
  ↓ execution_agent()  scripts/trading_execution.py  — Alpaca paper orders
  ↓ cc_trader()        scripts/trading_covered_calls.py — covered-call book (every ≤4h)
  ↓ report()           scripts/trading_report.py     — SQLite equity curve + ntfy alerts
```

Shared data layer: `scripts/trading_data.py` (Polygon equities, Alpaca crypto, account balance).

## Two books, one paper account ($50k each — since 2026-07-06)

- **Momentum book ($50k):** the original desk. All sizing runs off `min(account equity, MOMENTUM_BOOK_USD)`.
- **Covered-call book ($50k):** `scripts/trading_covered_calls.py`. Pure rules, no LLM ($0/cycle). Buys 100-share lots of quality names, sells WEEKLY calls (4–10 DTE, ~0.25Δ), closes at 60% profit captured; at ≤1 DTE: ITM → roll to next week for net credit, OTM → let expire and re-sell. Wheels via cash-secured puts on assignment. Never sells a strike below cost basis. Two-stage fills: mid 45s → bid (floored at the 10%-annualized-yield price). Income target: $500+/mo premium.
- Books are symbol-partitioned: each excludes the other's live symbols + open orders. Daily halt (−2%) spans the whole account.
- **SPY core sweep (2026-07-06):** idle cash above a $3k floor auto-invests into SPY at the end of each equities cycle (`scripts/trading_core.py`); either book sells core SPY back (`release_core`) when it needs capital. Core has no stop/gate — it IS the benchmark. `python3 scripts/trading_core.py --status` to inspect.
- **Conviction-weighted sizing:** momentum positions scale 4% → 8% of the book linearly with thesis conviction (0.60 → 1.00); new entries vetoed past 90% book deployment.

```bash
python3 scripts/trading_covered_calls.py --status           # CC book + premium MTD vs $500 target
python3 scripts/trading_covered_calls.py --once --dry-run   # print intended CC actions
python3 scripts/trading_covered_calls.py --test             # stub-driven rules self-check
```
Orchestrator runs the CC cycle inside equities sessions at most every 4h (`data/cc_last_run.txt`); disable with `--no-cc`.

## Run commands

```bash
# Single cycle dry-run (no orders, no Anthropic cost):
python3 scripts/trading_orchestrator.py --once --dry-run

# Single live cycle (paper orders):
python3 scripts/trading_orchestrator.py --once

# Continuous loop (keep Mac awake):
caffeinate -i python3 scripts/trading_orchestrator.py --loop --interval 3600

# Backtest all 25 symbols, print gate results:
python3 scripts/trading_orchestrator.py --backtest-only

# Today's P&L vs SPY:
python3 scripts/trading_orchestrator.py --report

# Research agent alone (see what Claude would trade):
python3 scripts/trading_research.py --symbols SPY QQQ AAPL NVDA

# Overnight crypto session:
python3 scripts/trading_research.py --market-session crypto

# Risk unit tests:
python3 scripts/trading_risk.py --test

# Place + cancel a test paper order:
python3 scripts/trading_execution.py --test
```

## Universe

**Equities (market hours 09:30–16:00 ET):**
SPY QQQ AAPL MSFT NVDA AMZN GOOGL META TSLA BRK.B JPM V UNH XOM AMD NFLX CRM ADBE IWM GLD TLT

**Crypto (overnight, 24/7):** BTC/USD ETH/USD

Benchmark: SPY buy-and-hold (shown in `--report`).

## Risk ceiling (Conservative — updated 2026-07-06)

| Rule | Value |
|---|---|
| Stop per position | ATR(14) × 1.5, clamped 1–3% of entry (fallback 1%) |
| Stop management | breakeven at +1R, then high-water trailing; stops only ratchet forward |
| Max position size | 4% of the $50k momentum book |
| Max concurrent positions | 15 |
| Regime filter | SPY vs 200d SMA: above → longs only; below → shorts only; data failure → no new entries |
| Daily portfolio halt | −2% from day-open equity (whole account) → stop all trading |

To change ceilings, edit constants at the top of `scripts/trading_risk.py` and log the decision in `decisions/log.md`.

## Strategy

Dual-momentum (fast EMA × slow EMA crossover) + RSI filter. Walk-forward gate (70% IS / 30% OOS):
- OOS Sharpe ≥ 0.5
- OOS max drawdown ≤ 15%
- Win rate ≥ 45%

Parameters in `scripts/trading_quant.py` → `DEFAULT_PARAMS`.

## Keys required (.env)

```
ALPACA_API_KEY=...        # paper account
ALPACA_SECRET_KEY=...     # paper account
POLYGON_API_KEY=...       # already set
ANTHROPIC_API_KEY=...     # already set
NOTIFY_IMESSAGE_TO=...    # already set
```

## Cost per cycle

Research agent (Haiku): ~485 tokens in / ~600 out ≈ $0.01–0.03.
Data calls (Polygon/Alpaca): free tier.
vectorbt backtest: local CPU, no cost.

## Gotchas

- **Market hours**: `is_market_open()` uses EDT (UTC-4) fixed offset — works Apr–Nov. In EST (Nov–Mar) adjust if equity cycles are running an hour off.
- **SPY Polygon timestamp**: bars come back as epoch-ms integers, not ISO strings. `trading_quant.py` handles both.
- **Crypto Alpaca data**: use `/v1beta3/crypto/us/` endpoint, not `/v2/stocks/`. Symbol format is `BTC/USD` (with slash).
- **Paper is hard-coded**: `_PAPER = True` in `trading_execution.py`. Never set to False without Brian's explicit approval and real Alpaca live keys.
- **Walk-forward with few bars**: BTC fails the gate when only 180d of data is pulled (not enough OOS trades). Use `--days 365` or more.
- **Claude JSON fences**: Haiku sometimes wraps output in ``` fences despite instructions. `trading_research.py` strips them automatically.
- **caffeinate**: required for `--loop` so macOS doesn't sleep mid-cycle. `caffeinate -i python3 scripts/trading_orchestrator.py --loop`.

## Real money checklist (do NOT skip)

Before switching off paper:
- [ ] 2+ weeks sustained paper performance (Sharpe > 0.5, max DD < 10%)
- [ ] Walk-forward gate confirmed on most recent 365d data
- [ ] Risk ceiling reviewed and explicitly re-approved by Brian
- [ ] Alpaca live keys generated (separate from paper keys) and added to `.env`
- [ ] `_PAPER = True` changed to `False` in `trading_execution.py` with a `decisions/log.md` entry
- [ ] Brian gives explicit go-ahead in this chat
