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
from db.schema import TradingEquityCurve, TradingPosition, TradingSignal

_NOTIFY_TO = os.getenv("NOTIFY_IMESSAGE_TO", "")
_NOTIFY_SH = str(Path(__file__).parent / "notify.sh")
_START_EQUITY = 100_000.0   # paper starting equity
# Soft daily profit goal — tracking/visibility only. Does NOT force or block trades
# (the -2% daily halt is the only hard daily rule). Override via env.
_DAILY_TARGET = float(os.getenv("DAILY_TARGET_USD", "1000"))


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

        # Today's $ P&L vs the soft target = today's equity − last prior day's close
        prior = [r for r in rows if r.date < today_str]
        prev_equity = prior[-1].portfolio_equity if prior else _START_EQUITY
        daily_pnl = equity - prev_equity

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

    pct_target = (daily_pnl / _DAILY_TARGET) if _DAILY_TARGET else 0
    hit = "✅" if daily_pnl >= _DAILY_TARGET else ""
    print(f"  📊 {today_str} equity=${equity:,.2f}  port={port_return_pct:+.2%}  spy={spy_return_pct:+.2%}  sharpe={sharpe:.2f}  dd={max_dd:.1%}")
    print(f"  🎯 Today P&L ${daily_pnl:+,.2f} / ${_DAILY_TARGET:,.0f} soft target ({pct_target:+.0%}) {hit}")
    return {"equity": equity, "port_return_pct": port_return_pct,
            "spy_return_pct": spy_return_pct, "daily_pnl": daily_pnl}


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
    if len(rows) >= 2:
        daily_pnl = latest.portfolio_equity - rows[-2].portfolio_equity
        hit = "✅" if daily_pnl >= _DAILY_TARGET else ""
        print(f"  Today P&L: ${daily_pnl:+,.2f} / ${_DAILY_TARGET:,.0f} soft target ({daily_pnl/_DAILY_TARGET:+.0%}) {hit}")

    # ── Two-book breakdown: momentum (table above) + covered-call book ──
    cc = _cc_book_summary()
    if cc:
        print(f"  CC book: {cc['underlyings']} underlyings "
              f"({cc['covered']} covered, {cc['uncovered']} naked)  "
              f"premium MTD ${cc['premium_mtd']:,.0f}  realized ${cc['realized_pnl']:+,.0f}")


def _win_stats(pnls: list[float]) -> dict:
    """Win rate + avg win/loss + profit factor from a list of realized $ P&L per trade."""
    n = len(pnls)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": 0.0}
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win  = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "n":             n,
        "win_rate":      len(wins) / n,
        "avg_win":       (gross_win / len(wins)) if wins else 0.0,
        "avg_loss":      (gross_loss / len(losses)) if losses else 0.0,
        # ponytail: profit_factor=inf when no losses yet; cap display, not the math
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
    }


def print_win_rates():
    """Backtest-expected (OOS) vs realized (closed trades) win rates, side by side, + definitions."""
    s = Session()
    try:
        closed = s.query(TradingPosition).filter(
            TradingPosition.status.in_(("closed", "stopped"))
        ).all()
        # Backtest-expected: the trades we actually approved (passed the gate)
        passed = s.query(TradingSignal).filter_by(passed_gate=True).all()
    finally:
        s.close()

    realized = _win_stats([p.pnl for p in closed if p.pnl is not None])
    bt_wr    = (sum(x.win_rate for x in passed) / len(passed)) if passed else 0.0
    bt_dd    = (sum((x.max_drawdown or 0) for x in passed) / len(passed)) if passed else 0.0
    bt_shp   = (sum((x.oos_sharpe or 0) for x in passed) / len(passed)) if passed else 0.0

    pf = realized["profit_factor"]
    pf_str = "∞ (no losses yet)" if pf == float("inf") else f"{pf:.2f}"

    print("\n  ── Win Rates: Backtest-Expected vs Realized ──")
    print(f"  {'Metric':22s}  {'Backtest (OOS)':>16s}  {'Realized (live)':>16s}")
    print("  " + "-" * 60)
    print(f"  {'Win rate':22s}  {bt_wr:>15.0%}   {realized['win_rate']:>15.0%}")
    print(f"  {'Sample size (trades)':22s}  {len(passed):>15d}   {realized['n']:>15d}")
    print(f"  {'OOS Sharpe (avg)':22s}  {bt_shp:>16.2f}  {'—':>16s}")
    print(f"  {'Max drawdown (avg)':22s}  {bt_dd:>15.0%}   {'—':>16s}")
    print(f"  {'Avg win  ($/trade)':22s}  {'—':>16s}  ${realized['avg_win']:>14,.2f}")
    print(f"  {'Avg loss ($/trade)':22s}  {'—':>16s}  ${realized['avg_loss']:>14,.2f}")
    print(f"  {'Profit factor':22s}  {'—':>16s}  {pf_str:>16s}")

    if realized["n"] == 0:
        print("\n  (No closed trades yet — realized column fills in once paper trades exit.)")

    print("""
  ── What the metrics mean ──
  Win rate         % of trades that closed profitable. 45% is the gate floor —
                   a good system can win <50% if wins are bigger than losses.
  Backtest (OOS)   Out-of-sample: measured on price history the strategy was
                   NOT tuned on. The honest estimate of forward performance.
  Realized (live)  What actually happened on closed paper trades. If this drifts
                   well below Backtest, the edge isn't holding live — investigate.
  Sample size      How many trades the number is based on. Small N = low trust;
                   a 100% win rate on 2 trades is luck, not skill.
  OOS Sharpe       Return per unit of risk (volatility), out-of-sample. >1 good,
                   >2 excellent. Negative = losing money for the risk taken.
  Max drawdown     Worst peak-to-trough equity drop. 15% cap = if it falls more,
                   the strategy is rejected. This is your 'how bad does it hurt'.
  Avg win/loss     Mean $ on winning vs losing trades. Win > loss means you can
                   profit even below a 50% win rate.
  Profit factor    Gross profit ÷ gross loss. >1 = profitable; 1.5+ is healthy;
                   below 1 means losers outweigh winners.
  Alpha vs SPY     Your return minus just buying-and-holding the S&P 500. The
                   only number that says whether the bot beats doing nothing.""")


def _send_session_email(prev: str, new: str, equity: float, daily_pnl: float,
                        n: int, wins: int, realized: float, open_list: str):
    """Send a Gmail performance summary email at session flip."""
    try:
        import base64
        from email.mime.text import MIMEText
        from email.header import Header
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from gws_auth import get_token
        token = get_token()
        subject = f"Trading Desk — {prev.upper()} session close"
        html_body = (
            f"<h3>{prev.upper()} → {new.upper()}</h3>"
            f"<p><b>Equity:</b> ${equity:,.0f} &nbsp; (today {daily_pnl:+,.0f})</p>"
            f"<p><b>Closed today:</b> {n} trade{'s' if n != 1 else ''}, "
            f"{wins} win{'s' if wins != 1 else ''}, net ${realized:+,.0f}</p>"
            f"<p><b>Open now:</b> {open_list}</p>"
        )
        msg = MIMEText(html_body, "html", "utf-8")
        msg["to"] = "brian@olivetreeinv.io"
        msg["from"] = "brian@olivetreeinv.io"
        msg["subject"] = str(Header(subject, "utf-8"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        import requests as _req
        r = _req.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"raw": raw},
            timeout=20,
        )
        r.raise_for_status()
        print(f"  📧 Session email sent to brian@olivetreeinv.io")
    except Exception as e:
        print(f"  ⚠️  Session email failed: {e}")


def _cc_book_summary() -> dict:
    """Summarize the covered-call book: positions, premium MTD, realized P&L, market value."""
    from db.schema import TradingCCPosition
    s = Session()
    try:
        today = date.today().isoformat()
        mtd_start = today[:7] + "-01"  # YYYY-MM-01
        open_cc = s.query(TradingCCPosition).filter_by(status="open").all()
        closed_cc = s.query(TradingCCPosition).filter(
            TradingCCPosition.status.in_(("closed", "assigned", "expired", "wheeled")),
            TradingCCPosition.closed_at >= mtd_start,
        ).all()
        premium_mtd = sum((r.premium_received or 0) for r in open_cc) + \
                      sum((r.premium_received or 0) for r in closed_cc)
        realized_pnl = sum((r.realized_pnl or 0) for r in closed_cc)
        covered   = sum(1 for r in open_cc if r.option_symbol)
        uncovered = sum(1 for r in open_cc if not r.option_symbol)
        return {
            "underlyings":   len(open_cc),
            "covered":       covered,
            "uncovered":     uncovered,
            "premium_mtd":   round(premium_mtd, 2),
            "realized_pnl":  round(realized_pnl, 2),
        }
    except Exception:
        return {}
    finally:
        s.close()


def send_session_report(prev_session: str, new_session: str):
    """Text an activity summary when the market session flips (equities↔crypto)."""
    acct   = get_account()
    equity = acct["equity"]
    s = Session()
    try:
        today = date.today().isoformat()
        open_pos = s.query(TradingPosition).filter_by(status="open").all()
        closed_today = [p for p in s.query(TradingPosition).filter(
            TradingPosition.status.in_(("closed", "stopped"))).all()
            if (p.exit_time or "").startswith(today) and p.pnl is not None]
        row = s.query(TradingEquityCurve).filter_by(date=today).first()
    finally:
        s.close()

    daily_pnl = (row.portfolio_equity - _START_EQUITY) if row else 0.0
    wins   = sum(1 for p in closed_today if p.pnl > 0)
    realized = sum(p.pnl for p in closed_today)
    n = len(closed_today)
    open_list = ", ".join(f"{p.symbol} {p.side}" for p in open_pos) or "none"

    # ── Two-book breakdown ─────────────────────────────────────────
    cc = _cc_book_summary()
    cc_line = ""
    if cc:
        cc_line = (
            f"\nCC book: {cc['underlyings']} underlyings "
            f"({cc['covered']} covered, {cc['uncovered']} naked)  "
            f"premium MTD ${cc['premium_mtd']:,.0f}  realized ${cc['realized_pnl']:+,.0f}"
        )

    body = (
        f"{prev_session.upper()} → {new_session.upper()}\n"
        f"Equity ${equity:,.0f}  (today {daily_pnl:+,.0f})\n"
        f"[Momentum] Closed today: {n} trades, {wins} win{'s' if wins != 1 else ''}, "
        f"net ${realized:+,.0f}  |  Open: {open_list}"
        f"{cc_line}"
    )
    send_alert(f"Trading Desk — {prev_session} close", body)
    _send_session_email(prev_session, new_session, equity, daily_pnl, n, wins, realized, open_list)
    print(f"  📋 Session report sent ({prev_session}→{new_session})")
    if cc_line:
        print(f"  {cc_line.strip()}")


def main():
    ap = argparse.ArgumentParser(description="Trading Desk report + alerts")
    ap.add_argument("--snapshot", action="store_true", help="Record today's equity snapshot")
    ap.add_argument("--print",    action="store_true", help="Print performance table + win rates")
    ap.add_argument("--win-rates", action="store_true", help="Win rates (backtest vs realized) + metric definitions")
    ap.add_argument("--alert",    help="Send a test iMessage alert")
    ap.add_argument("--test",     action="store_true", help="Self-check win-stat math")
    args = ap.parse_args()

    if args.test:
        w = _win_stats([10, 10, -5, -5, -10])
        assert w["n"] == 5 and abs(w["win_rate"] - 0.4) < 1e-9, w
        assert abs(w["avg_win"] - 10) < 1e-9 and abs(w["avg_loss"] - (20/3)) < 1e-9, w
        assert abs(w["profit_factor"] - 1.0) < 1e-9, w          # 20 won / 20 lost
        assert _win_stats([])["win_rate"] == 0.0
        assert _win_stats([5, 5])["profit_factor"] == float("inf")  # no losses
        print("  ✅ _win_stats self-check passed.")
        return

    if args.alert:
        send_alert("Trading Desk — Test", args.alert)
        print(f"  📱 Alert sent: {args.alert}")
    elif args.snapshot:
        snapshot_equity()
    elif args.win_rates:
        print_win_rates()
    elif args.print:
        print_performance()
        print_win_rates()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
