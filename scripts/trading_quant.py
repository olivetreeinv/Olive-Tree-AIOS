#!/usr/bin/env python3
"""
trading_quant.py — Quant agent for the Olive Tree Trading Desk.

Strategy: dual-momentum (fast EMA × slow EMA crossover) with RSI filter.
Gate: walk-forward backtest must clear minimum Sharpe and drawdown thresholds
      on the out-of-sample (OOS) fold before a signal is approved.

Usage:
  python3 scripts/trading_quant.py --symbol SPY --days 365
  python3 scripts/trading_quant.py --symbol BTC/USD --days 180
  python3 scripts/trading_quant.py --backtest-all       # run universe + print table
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data import get_bars, EQUITY_UNIVERSE, CRYPTO_UNIVERSE

# ── Gate thresholds (Conservative risk profile) ──────────────────────────────
MIN_OOS_SHARPE   = 0.5   # OOS Sharpe must exceed this
MAX_OOS_DRAWDOWN = 0.15  # OOS max drawdown must be below this (15%)
MIN_WIN_RATE     = 0.45  # at least 45% of trades profitable

# ── Strategy parameters ───────────────────────────────────────────────────────
DEFAULT_PARAMS = {
    "fast_ema": 10,
    "slow_ema": 30,
    "rsi_period": 14,
    "rsi_oversold": 35,   # only go long when RSI > oversold (not chasing oversold bounces)
    "rsi_overbought": 70, # exit / don't enter when RSI > overbought
}

# Walk-forward split: 70% in-sample, 30% out-of-sample
WF_TRAIN_RATIO = 0.70


def _bars_to_series(bars: list[dict]) -> pd.Series:
    """Convert get_bars() output to a close-price pd.Series with DatetimeIndex."""
    if not bars:
        return pd.Series(dtype=float)
    df = pd.DataFrame(bars)
    # Polygon timestamps are epoch-ms; Alpaca are ISO strings
    if isinstance(df["t"].iloc[0], (int, float)):
        df["dt"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    else:
        df["dt"] = pd.to_datetime(df["t"], utc=True)
    df = df.set_index("dt").sort_index()
    return df["c"].astype(float)


def _compute_signals(close: pd.Series, params: dict, direction: str = "long") -> pd.Series:
    """Return a boolean entry Series for the given direction (long or short)."""
    fast = close.ewm(span=params["fast_ema"], adjust=False).mean()
    slow = close.ewm(span=params["slow_ema"], adjust=False).mean()

    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=params["rsi_period"] - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=params["rsi_period"] - 1, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    if direction == "short":
        # Short when fast EMA below slow (bearish) and RSI not yet oversold (room to fall)
        entries = (fast < slow) & (rsi < params["rsi_overbought"]) & (rsi > params["rsi_oversold"])
    else:
        entries = (fast > slow) & (rsi > params["rsi_oversold"]) & (rsi < params["rsi_overbought"])
    return entries


def _backtest_fold(close: pd.Series, params: dict, direction: str = "long") -> dict:
    """Run a vectorised backtest on a price series slice. Returns metrics dict."""
    import vectorbt as vbt

    signal = _compute_signals(close, params, direction)

    if direction == "short":
        # For shorts: negate daily returns when signal is active.
        # Avoids vectorbt short-position API inconsistencies across versions.
        daily_ret = close.pct_change().fillna(0)
        strat_ret = daily_ret.where(~signal, -daily_ret)   # earn inverse when short
        strat_ret -= 0.001 * signal.diff().abs().fillna(0)  # friction on trades
        equity = (1 + strat_ret).cumprod() * 100_000

        # Trade-level win rate: compute cumulative return per trade (entry→exit)
        trade_rets = []
        in_trade   = False
        trade_ret  = 0.0
        for sig, ret in zip(signal, strat_ret):
            if sig and not in_trade:
                in_trade  = True
                trade_ret = 0.0
            if in_trade:
                trade_ret += ret
            if not sig and in_trade:
                trade_rets.append(trade_ret)
                in_trade = False
        if in_trade:
            trade_rets.append(trade_ret)
        n_trades = len(trade_rets)
        win_rate = sum(1 for r in trade_rets if r > 0) / n_trades if n_trades > 0 else 0.0

        total_return = float((equity.iloc[-1] / 100_000) - 1)
        years = len(close) / 252
        cagr  = ((1 + total_return) ** (1 / max(years, 0.01))) - 1

        active_rets = strat_ret[signal]
        if len(active_rets) > 1 and active_rets.std() > 0:
            sharpe = float(active_rets.mean() / active_rets.std() * (252 ** 0.5))
        else:
            sharpe = 0.0

        peak    = equity.cummax()
        drawdown = float(((peak - equity) / peak).max())
    else:
        entries = signal
        exits   = ~signal

        pf = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            freq="D",
            init_cash=100_000,
            fees=0.001,
            slippage=0.0005,
        )
        n_trades     = int(pf.stats().get("Total Trades", 0) or 0)
        if n_trades == 0:
            return {"symbol": "", "error": "No trades in fold", "passed_gate": False, "bars": len(close)}
        stats        = pf.stats()
        sharpe       = float(stats.get("Sharpe Ratio", 0) or 0)
        drawdown     = float(pf.max_drawdown())
        total_return = float(pf.total_return())
        win_rate     = float(stats.get("Win Rate [%]", 0) or 0) / 100
        years        = len(close) / 252
        cagr         = ((1 + total_return) ** (1 / max(years, 0.01))) - 1

    return {
        "sharpe":       sharpe,
        "max_drawdown": drawdown,
        "total_return": total_return,
        "cagr":         cagr,
        "win_rate":     win_rate,
        "n_trades":     n_trades,
        "bars":         len(close),
    }


def run_walk_forward(symbol: str, days: int = 365, params: dict | None = None, direction: str = "long") -> dict:
    """
    Walk-forward backtest on `symbol` using `days` of history.
    Returns a result dict with in-sample, out-of-sample metrics, and a passed_gate flag.
    """
    if params is None:
        params = DEFAULT_PARAMS

    bars = get_bars(symbol, days=days)
    if len(bars) < 60:
        return {"symbol": symbol, "error": f"Insufficient bars ({len(bars)} < 60)", "passed_gate": False}

    close = _bars_to_series(bars)
    split  = int(len(close) * WF_TRAIN_RATIO)
    is_close  = close.iloc[:split]
    oos_close = close.iloc[split:]

    if len(is_close) < 30 or len(oos_close) < 10:
        return {"symbol": symbol, "error": "Folds too short after split", "passed_gate": False}

    is_metrics  = _backtest_fold(is_close,  params, direction)
    oos_metrics = _backtest_fold(oos_close, params, direction)

    passed = (
        oos_metrics["sharpe"]       >= MIN_OOS_SHARPE
        and oos_metrics["max_drawdown"] <= MAX_OOS_DRAWDOWN
        and oos_metrics["win_rate"]     >= MIN_WIN_RATE
    )

    return {
        "symbol":      symbol,
        "direction":   direction,
        "params":      params,
        "is":          is_metrics,
        "oos":         oos_metrics,
        "passed_gate": passed,
        "run_at":      datetime.now(timezone.utc).isoformat(),
    }


def _print_result(r: dict):
    sym = r["symbol"]
    if "error" in r:
        print(f"  ❌ {sym}: {r['error']}")
        return
    gate = "✅ PASS" if r["passed_gate"] else "❌ FAIL"
    oos  = r["oos"]
    print(
        f"  {gate}  {sym:12s}"
        f"  OOS Sharpe={oos['sharpe']:.2f}"
        f"  DD={oos['max_drawdown']:.1%}"
        f"  WinRate={oos['win_rate']:.0%}"
        f"  CAGR={oos['cagr']:.1%}"
        f"  Trades={oos['n_trades']}"
    )


def main():
    ap = argparse.ArgumentParser(description="Trading Desk quant backtest gate")
    ap.add_argument("--symbol",       help="Single symbol")
    ap.add_argument("--days",  type=int, default=365)
    ap.add_argument("--backtest-all", action="store_true", help="Run full universe")
    ap.add_argument("--json",         action="store_true", help="Output JSON")
    args = ap.parse_args()

    if args.backtest_all:
        universe = EQUITY_UNIVERSE + CRYPTO_UNIVERSE
        print(f"Walk-forward backtest — {len(universe)} symbols — {args.days}d history")
        print(f"Gate: OOS Sharpe≥{MIN_OOS_SHARPE}  DD≤{MAX_OOS_DRAWDOWN:.0%}  WinRate≥{MIN_WIN_RATE:.0%}\n")
        results = []
        for sym in universe:
            try:
                r = run_walk_forward(sym, days=args.days)
            except Exception as e:
                r = {"symbol": sym, "error": str(e), "passed_gate": False}
            _print_result(r)
            results.append(r)
        passed = [r for r in results if r.get("passed_gate")]
        print(f"\n{len(passed)}/{len(universe)} symbols passed the quant gate.")
        if args.json:
            print(json.dumps(results, indent=2))
    elif args.symbol:
        r = run_walk_forward(args.symbol, days=args.days)
        _print_result(r)
        if args.json:
            print(json.dumps(r, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
