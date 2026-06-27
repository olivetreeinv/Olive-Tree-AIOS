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
  ↓ report()           scripts/trading_report.py     — SQLite equity curve + iMessage alerts
```

Shared data layer: `scripts/trading_data.py` (Polygon equities, Alpaca crypto, account balance).

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

## Risk ceiling (Conservative — locked 2026-06-26)

| Rule | Value |
|---|---|
| Max loss per position | −1% of entry |
| Max position size | 5% of portfolio equity |
| Max concurrent positions | 5 |
| Daily portfolio halt | −2% from day-open equity → stop all trading |

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
