#!/usr/bin/env python3
"""
trading_report.py — Daily P&L report + iMessage alerts for the Trading Desk.

Snapshots portfolio equity vs SPY buy-and-hold, computes running Sharpe
and max drawdown, and sends iMessage alerts on halt triggers or big moves.

Usage:
  python3 scripts/trading_report.py --snapshot      # record today's equity curve row
  python3 scripts/trading_report.py --print         # print current performance table
  python3 scripts/trading_report.py --alert "msg"  # send a test iMessage alert
"""

import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data import get_bars, get_account
from db.connection import Session
from db.schema import TradingEquityCurve, TradingPosition

_NOTIFY_TO = os.getenv("NOTIFY_IMESSAGE_TO", "")
_NOTIFY_SH = str(Path(__file__).parent / "notify.sh")
_START_EQUITY = 100_000.0   # paper starting equity


def send_alert(title: str, body: str):
    """Send an iMessage via notify.sh (osascript). Fire-and-forget."""
    if not _NOTIFY_TO:
        print(f"  [alert] {title}: {body}")
        return
    try:
        subprocess.run(
            ["sh", _NOTIFY_SH, title, body],
            timeout=10, check=False, capture_output=True,
        )
    except Exception as e:
        print(f"  ⚠️  Alert send failed: {e}")


def snapshot_equity():
    """Record today's equity snapshot to trading_equity_curve."""
    acct      = get_account()
    equity    = acct["equity"]
    cash      = acct["cash"]
    today_str = date.today().isoformat()

    spy_bars  = get_bars("SPY", days=400)
    spy_close = spy_bars[-1]["c"] if spy_bars else None
    spy_start = spy_bars[0]["c"]  if spy_bars else None

    spy_return_pct  = ((spy_close / spy_start) - 1) if spy_close and spy_start else 0
    port_return_pct = (equity / _START_EQUITY) - 1

    # Running Sharpe from all snapshots
    s = Session()
    try:
        rows = s.query(TradingEquityCurve).order_by(TradingEquityCurve.date).all()
        equities = [r.portfolio_equity for r in rows if r.portfolio_equity > 0] + [equity]
        daily_rets = [
            (equities[i] / equities[i-1]) - 1
            for i in range(1, len(equities))
            if equities[i-1] > 0
        ]
        if len(daily_rets) >= 5:
            mean_r = np.mean(daily_rets)
            std_r  = np.std(daily_rets, ddof=1)
            sharpe = (mean_r / std_r * (252 ** 0.5)) if std_r > 0 else 0.0
        else:
            sharpe = 0.0

        # Max drawdown over all snapshots
        peak = _START_EQUITY
        max_dd = 0.0
        for eq in equities:
            peak   = max(peak, eq)
            dd     = (peak - eq) / peak
            max_dd = max(max_dd, dd)

        open_pos = s.query(TradingPosition).filter_by(status="open").count()

        # Upsert today's row
        existing = s.query(TradingEquityCurve).filter_by(date=today_str).first()
        if existing:
            row = existing
        else:
            row = TradingEquityCurve(date=today_str)
            s.add(row)

        row.portfolio_equity = equity
        row.cash             = cash
        row.spy_close        = spy_close
        row.spy_return_pct   = spy_return_pct
        row.port_return_pct  = port_return_pct
        row.sharpe_running   = round(sharpe, 3)
        row.max_drawdown     = round(max_dd, 4)
        row.open_positions   = open_pos
        s.commit()
    finally:
        s.close()

    print(f"  📊 {today_str} equity=${equity:,.2f}  port={port_return_pct:+.2%}  spy={spy_return_pct:+.2%}  sharpe={sharpe:.2f}  dd={max_dd:.1%}")
    return {"equity": equity, "port_return_pct": port_return_pct, "spy_return_pct": spy_return_pct}


def print_performance():
    """Print a running performance table from the equity curve."""
    s = Session()
    try:
        rows = s.query(TradingEquityCurve).order_by(TradingEquityCurve.date).all()
    finally:
        s.close()

    if not rows:
        print("  No equity curve data yet. Run --snapshot first.")
        return

    print(f"\n  {'Date':12s}  {'Equity':>12s}  {'Portfolio':>10s}  {'SPY':>8s}  {'Sharpe':>7s}  {'MaxDD':>7s}  {'Pos':>4s}")
    print("  " + "-" * 75)
    for r in rows:
        halted = " 🛑" if r.daily_halted else ""
        print(
            f"  {r.date:12s}  ${r.portfolio_equity:>11,.2f}"
            f"  {r.port_return_pct:>+9.2%}  {r.spy_return_pct:>+7.2%}"
            f"  {r.sharpe_running:>7.2f}  {r.max_drawdown:>6.1%}  {r.open_positions or 0:>4d}{halted}"
        )

    latest = rows[-1]
    alpha  = (latest.port_return_pct or 0) - (latest.spy_return_pct or 0)
    print(f"\n  Alpha vs SPY: {alpha:+.2%}  |  Running Sharpe: {latest.sharpe_running:.2f}  |  Max Drawdown: {latest.max_drawdown:.1%}")


def main():
    ap = argparse.ArgumentParser(description="Trading Desk report + alerts")
    ap.add_argument("--snapshot", action="store_true", help="Record today's equity snapshot")
    ap.add_argument("--print",    action="store_true", help="Print performance table")
    ap.add_argument("--alert",    help="Send a test iMessage alert")
    args = ap.parse_args()

    if args.alert:
        send_alert("Trading Desk — Test", args.alert)
        print(f"  📱 Alert sent: {args.alert}")
    elif args.snapshot:
        snapshot_equity()
    elif args.print:
        print_performance()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
