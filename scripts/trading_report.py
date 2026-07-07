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
import calendar
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
_START_EQUITY = 50_000.0    # Premium Desk v2 paper account (PA3TCU0QOGVS) starting equity
# Soft daily profit goal — tracking/visibility only. Does NOT force or block trades
# (the -2% daily halt is the only hard daily rule). Override via env.
_DAILY_TARGET = float(os.getenv("DAILY_TARGET_USD", "1000"))
_DESK_START = "2026-07-07"  # first equity-curve row of the v2 account — SPY comparisons anchor here


def _spy_same_window(rows) -> float:
    """SPY return over the desk's actual life (first curve row → latest), from stored
    spy_close. The rows' spy_return_pct column uses a 400-day window — misleading."""
    spy = [r.spy_close for r in rows if r.spy_close]
    return (spy[-1] / spy[0] - 1) if len(spy) >= 2 else 0.0


def _bottom_line(equity: float = None) -> list[str]:
    """Plain-English 'is this working?' block. Deterministic, no quant jargon."""
    s = Session()
    try:
        rows = s.query(TradingEquityCurve).order_by(TradingEquityCurve.date).all()
    finally:
        s.close()
    if equity is None:
        equity = rows[-1].portfolio_equity if rows else _START_EQUITY

    total = equity - _START_EQUITY
    today_str = date.today().isoformat()
    prior = [r for r in rows if r.date < today_str]
    prev_eq = prior[-1].portfolio_equity if prior else _START_EQUITY
    today_pnl = equity - prev_eq

    spy_ret = _spy_same_window(rows)
    spy_dollars = _START_EQUITY * spy_ret          # what the same start in SPY would have made
    gap = total - spy_dollars

    # Local import — trading_covered_calls imports send_alert from this module,
    # so a top-of-file import here would be circular.
    from scripts.trading_covered_calls import CC_MONTHLY_TARGET_USD, CC_BOOK_USD

    cc = _cc_book_summary()
    prem     = cc.get("premium_mtd", 0)  if cc else 0
    realized = cc.get("realized_pnl", 0) if cc else 0
    t = date.today()
    pace = CC_MONTHLY_TARGET_USD * t.day / calendar.monthrange(t.year, t.month)[1]
    days_elapsed = t.day  # MTD always starts the 1st
    annualized_yield = (prem / CC_BOOK_USD) * (365 / days_elapsed) if days_elapsed else 0

    age = (t - date.fromisoformat(_DESK_START)).days
    max_dd = max((r.max_drawdown or 0) for r in rows) if rows else 0.0

    lines = [
        f"{'Up' if total >= 0 else 'Down'} ${abs(total):,.0f} since the ${_START_EQUITY:,.0f} start "
        f"(${today_pnl:+,.0f} today).",
        f"If you'd just bought the S&P 500 instead, you'd be "
        f"{'up' if spy_dollars >= 0 else 'down'} ${abs(spy_dollars):,.0f} — "
        f"the desk is {'ahead' if gap >= 0 else 'behind'} by ${abs(gap):,.0f}.",
        f"${prem:,.0f} of covered-call/wheel premium banked this month — "
        f"{'on' if prem >= pace else 'behind'} pace for the ${CC_MONTHLY_TARGET_USD:,.0f} target "
        f"({annualized_yield:.0%} annualized yield-on-book vs the 30-40% goal). "
        f"Wheel realized P&L: ${realized:+,.0f}.",
    ]
    if age < 30:
        lines.append(f"Too early to call — {age} days of data, need ~30.")
    elif total > 0 and gap >= 0 and max_dd < 0.10:
        lines.append("Working — beating the market with smaller swings.")
    elif total > 0:
        lines.append("Mixed — making money but the market's doing better.")
    else:
        lines.append("Not working — losing money / trailing badly. Worth reviewing.")
    return lines


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

    print("\n  ── Bottom Line ─────────────────────────────────────")
    for ln in _bottom_line():
        print(f"  {ln}")

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
    # Same-window comparison: desk return vs SPY over the desk's actual life —
    # the stored spy_return_pct uses a 400-day window and overstates SPY badly.
    alpha  = (latest.port_return_pct or 0) - _spy_same_window(rows)
    print(f"\n  Alpha vs SPY (since {_DESK_START}): {alpha:+.2%}  |  Running Sharpe: {latest.sharpe_running:.2f}  |  Max Drawdown: {latest.max_drawdown:.1%}")
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

    # ── Core SPY holding (idle-cash sweep) ────────────────────────────────────
    try:
        from scripts.trading_core import core_value
        cv = core_value()
        print(f"  Core S&P holding: ${cv:,.0f} (auto-invested idle cash)")
    except Exception:
        pass


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


def _gmail_send(subject: str, html_body: str):
    """Low-level Gmail send. Raises on failure."""
    import base64
    from email.mime.text import MIMEText
    from email.header import Header
    sys.path.insert(0, str(Path(__file__).parent))
    from gws_auth import get_token
    import requests as _req
    token = get_token()
    msg = MIMEText(html_body, "html", "utf-8")
    msg["to"] = "brian@olivetreeinv.io"
    msg["from"] = "brian@olivetreeinv.io"
    msg["subject"] = str(Header(subject, "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = _req.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=20,
    )
    r.raise_for_status()


def _build_scorecard_html(prev: str, new: str, is_friday: bool = False) -> tuple[str, str]:
    """
    Build the full daily scorecard HTML for the equities-close email.
    Returns (subject, html_body).
    """
    acct = get_account()
    equity = acct["equity"]

    s = Session()
    try:
        today = date.today().isoformat()
        mtd_start = today[:7] + "-01"
        week_start = (date.today() - __import__("datetime").timedelta(days=date.today().weekday())).isoformat()

        open_pos   = s.query(TradingPosition).filter_by(status="open").all()
        closed_all = s.query(TradingPosition).filter(
            TradingPosition.status.in_(("closed", "stopped"))
        ).all()
        closed_today = [p for p in closed_all if (p.exit_time or "").startswith(today) and p.pnl is not None]
        closed_week  = [p for p in closed_all if (p.exit_time or "") >= week_start and p.pnl is not None]

        row_ec = s.query(TradingEquityCurve).filter_by(date=today).first()
        ec_rows = s.query(TradingEquityCurve).order_by(TradingEquityCurve.date).all()

        # CC book
        from db.schema import TradingCCPosition
        open_cc   = s.query(TradingCCPosition).filter_by(status="open").all()
        closed_cc = s.query(TradingCCPosition).filter(
            TradingCCPosition.status.in_(("closed", "assigned", "expired", "wheeled")),
            TradingCCPosition.closed_at >= mtd_start,
        ).all()
        cc_events_today = s.query(TradingCCPosition).filter(
            TradingCCPosition.opened_at >= today
        ).all() + s.query(TradingCCPosition).filter(
            TradingCCPosition.closed_at >= today,
            TradingCCPosition.status.in_(("closed", "assigned", "expired", "wheeled")),
        ).all()
    finally:
        s.close()

    # ── Account header ────────────────────────────────────────────────────────
    prev_equity = ec_rows[-2].portfolio_equity if len(ec_rows) >= 2 else _START_EQUITY
    today_pnl_dollar = equity - prev_equity
    today_pnl_pct    = today_pnl_dollar / prev_equity if prev_equity else 0
    latest_ec = ec_rows[-1] if ec_rows else None

    # ── Momentum book ─────────────────────────────────────────────────────────
    day_realized  = sum(p.pnl for p in closed_today)
    day_wins      = sum(1 for p in closed_today if p.pnl > 0)
    inception_pnl = sum(p.pnl for p in closed_all if p.pnl is not None)

    # Open positions with current quotes
    from scripts.trading_data import get_quote
    pos_rows_html = ""
    for p in open_pos:
        try:
            q = get_quote(p.symbol)
            cur = q.get("last") or q.get("ask") or p.entry_price or 0
        except Exception:
            cur = p.entry_price or 0
        unreal = (cur - (p.entry_price or 0)) * p.qty if p.side == "long" else \
                 ((p.entry_price or 0) - cur) * p.qty
        stop = p.stop_price or 0
        stop_dist_pct = abs(cur - stop) / cur if cur else 0
        pos_rows_html += (
            f"<tr><td>{p.symbol}</td><td>{p.side}</td>"
            f"<td>${p.entry_price or 0:,.2f}</td><td>${cur:,.2f}</td>"
            f"<td style='color:{'green' if unreal>=0 else 'red'}'>${unreal:+,.0f}</td>"
            f"<td>${stop:,.2f} ({stop_dist_pct:.1%} away)</td></tr>"
        )
    if not pos_rows_html:
        pos_rows_html = "<tr><td colspan='6'>No open momentum positions</td></tr>"

    # ── CC book ───────────────────────────────────────────────────────────────
    premium_mtd  = sum((r.premium_received or 0) for r in open_cc) + \
                   sum((r.premium_received or 0) for r in closed_cc)
    cc_realized  = sum((r.realized_pnl or 0) for r in closed_cc)
    from scripts.trading_covered_calls import CC_MONTHLY_TARGET_USD, CC_BOOK_USD
    cc_target    = CC_MONTHLY_TARGET_USD
    cc_rows_html = ""
    for r in open_cc:
        lot_type = "CSP" if (r.option_type == "put" and not r.shares_qty) else "covered"
        call_info = f"{r.option_symbol or '—'} @ ${r.strike or 0:.2f} exp {r.expiry or '—'}"
        dte_val   = _dte(r.expiry) if r.expiry else "—"
        dte_disp  = f"{dte_val} Days To Expiration (DTE)" if isinstance(dte_val, int) else dte_val
        cc_rows_html += (
            f"<tr><td>{r.underlying}</td><td>{r.shares_qty or 0}</td>"
            f"<td>${r.avg_cost or 0:,.2f}</td><td>{call_info}</td>"
            f"<td>{dte_disp}</td><td>${r.premium_received or 0:,.0f}</td>"
            f"<td>{lot_type}</td></tr>"
        )
    if not cc_rows_html:
        cc_rows_html = "<tr><td colspan='7'>No open CC positions</td></tr>"

    # ── Moves made today ──────────────────────────────────────────────────────
    moves_html = ""
    for p in open_pos:
        if (p.entry_time or "").startswith(today):
            thesis_line = ""
            if p.signal and p.signal.thesis:
                t = p.signal.thesis
                thesis_line = t.rationale or t.catalyst or ""
                if thesis_line:
                    thesis_line = thesis_line[:80] + ("…" if len(thesis_line) > 80 else "")
            if not thesis_line:
                sig = p.signal
                thesis_line = f"conviction {sig.oos_sharpe:.2f} OOS Sharpe" if sig and sig.oos_sharpe else "no thesis"
            moves_html += f"<li>ENTERED {p.symbol} {p.side} {p.qty:.1f}sh @ ${p.entry_price:,.2f} — {thesis_line}</li>"
    for p in closed_today:
        reason = p.notes or ("stop-out" if p.status == "stopped" else "target")
        moves_html += f"<li>EXITED {p.symbol} {p.side} — net ${p.pnl:+,.0f} ({p.pnl_pct:+.1%}) [{reason}]</li>"
    # ponytail: CC events_today uses opened_at/closed_at strings; may double-count if a position both opens and closes today
    seen_cc = set()
    for r in cc_events_today:
        if r.id in seen_cc:
            continue
        seen_cc.add(r.id)
        if (r.opened_at or "").startswith(today):
            moves_html += f"<li>CC OPENED {r.underlying} lot — {r.shares_qty or 0}sh @ ${r.avg_cost or 0:.2f}</li>"
        if (r.closed_at or "").startswith(today):
            ev = r.status.upper()
            pnl = r.realized_pnl or 0
            moves_html += f"<li>CC {ev} {r.underlying} — P&L ${pnl:+,.0f}</li>"
        if r.option_symbol and (r.opened_at or "").startswith(today):
            moves_html += (f"<li>CC SOLD CALL {r.underlying} {r.option_symbol} "
                           f"exp {r.expiry} strike ${r.strike:.2f} — ${r.premium_received or 0:,.0f} premium</li>")
    if not moves_html:
        moves_html = "<li>No trades today</li>"

    # ── Planned moves (from CC next-actions) ─────────────────────────────────
    from scripts.trading_covered_calls import cc_next_actions
    planned = cc_next_actions()
    planned_html = "".join(f"<li>{a}</li>" for a in planned) if planned else "<li>Nothing queued</li>"

    # ── Friday: week-in-review section ───────────────────────────────────────
    friday_section = ""
    if is_friday:
        week_pnl = sum(p.pnl for p in closed_week)
        bt_stats = {}
        try:
            from db.schema import TradingSignal
            s2 = Session()
            try:
                passed = s2.query(TradingSignal).filter_by(passed_gate=True).all()
                bt_stats["bt_wr"]  = (sum(x.win_rate or 0 for x in passed) / len(passed)) if passed else 0
                bt_stats["bt_shp"] = (sum(x.oos_sharpe or 0 for x in passed) / len(passed)) if passed else 0
            finally:
                s2.close()
        except Exception:
            pass
        realized_stats = _win_stats([p.pnl for p in closed_all if p.pnl is not None])
        sharpe = latest_ec.sharpe_running if latest_ec else 0
        max_dd = latest_ec.max_drawdown if latest_ec else 0
        # Same-window SPY (desk life), not the stored 400-day figure
        alpha  = ((latest_ec.port_return_pct or 0) - _spy_same_window(ec_rows)) if latest_ec else 0
        friday_section = f"""
<hr>
<h3>Week in Review ({week_start} – {today})</h3>
<p>
  <b>Momentum P&amp;L this week (retired, --momentum only):</b> ${week_pnl:+,.0f} across {len(closed_week)} trade{'s' if len(closed_week) != 1 else ''}<br>
  <b>CC/wheel premium banked this month:</b> ${premium_mtd:,.0f} / ${cc_target:.0f} target ({premium_mtd/cc_target:.0%})<br>
  <b>Open positions:</b> {len(open_pos)} momentum (retired), {len(open_cc)} CC/wheel
</p>
<table border="1" cellpadding="4" style="border-collapse:collapse">
  <tr><th>Metric</th><th>Backtest (OOS)</th><th>Realized (live)</th><th>What it means</th></tr>
  <tr><td>Win rate</td><td>{bt_stats.get('bt_wr',0):.0%}</td><td>{realized_stats['win_rate']:.0%}</td>
    <td>% of trades that closed profitable. A good system can win &lt;50% if wins are bigger than losses.</td></tr>
  <tr><td>Running Sharpe</td><td>{bt_stats.get('bt_shp',0):.2f}</td><td>{sharpe:.2f}</td>
    <td>Return per unit of risk. &gt;1 is good, &gt;2 is excellent. Negative = losing money for the volatility taken.</td></tr>
  <tr><td>Max drawdown</td><td>—</td><td>{max_dd:.1%}</td>
    <td>Worst peak-to-trough equity drop since launch. 15% = strategy rejection threshold.</td></tr>
  <tr><td>Alpha vs SPY</td><td>—</td><td>{alpha:+.2%}</td>
    <td>Your return minus just buying the S&amp;P 500. The only number that says whether the bot beats doing nothing.</td></tr>
  <tr><td>Trades (live)</td><td>{len(passed) if 'passed' in dir() else '—'}</td><td>{realized_stats['n']}</td>
    <td>Sample size — small N means low confidence in the percentages above.</td></tr>
</table>"""

    # ── Bottom line (plain-English verdict, above everything) ────────────────
    bl = _bottom_line(equity=equity)
    bottom_line_html = "<br>".join(bl[:-1]) + f"<br><b>{bl[-1]}</b>"

    # ── Core SPY holding ──────────────────────────────────────────────────────
    core_html = ""
    try:
        from scripts.trading_core import core_value
        cv = core_value()
        core_html = f" &nbsp;|&nbsp; <b>Core S&amp;P holding:</b> ${cv:,.0f} (auto-invested idle cash)"
    except Exception:
        pass

    # ── Assemble HTML ─────────────────────────────────────────────────────────
    html = f"""
<h2>Trading Desk — Daily Scorecard ({today})</h2>
<h3>Bottom Line</h3>
<p>{bottom_line_html}</p>
<h3>Account</h3>
<p>
  <b>Equity:</b> ${equity:,.0f} &nbsp;|&nbsp;
  <b>Today P&amp;L:</b> <span style="color:{'green' if today_pnl_dollar>=0 else 'red'}">${today_pnl_dollar:+,.0f} ({today_pnl_pct:+.2%})</span>
  {core_html}
</p>

<h3>Momentum Book <small>(retired by default — only runs with --momentum)</small></h3>
<p>
  <b>Day realized P&amp;L:</b> ${day_realized:+,.0f} &nbsp;|&nbsp;
  <b>Trades:</b> {len(closed_today)} ({day_wins} win{'s' if day_wins != 1 else ''}) &nbsp;|&nbsp;
  <b>Inception realized total:</b> ${inception_pnl:+,.0f}
</p>
<table border="1" cellpadding="4" style="border-collapse:collapse">
  <tr><th>Symbol</th><th>Side</th><th>Entry</th><th>Current</th><th>Unrealized</th><th>Stop (distance)</th></tr>
  {pos_rows_html}
</table>

<h3>Covered-Call / Wheel Book (Premium Desk v2 — primary)</h3>
<p>
  <b>Premium collected Month-To-Date (MTD):</b> ${premium_mtd:,.0f} / ${cc_target:.0f} target ({premium_mtd/cc_target:.0%}) &nbsp;|&nbsp;
  <b>Annualized yield-on-book:</b> {(premium_mtd/CC_BOOK_USD)*(365/date.today().day):.0%} (goal 30-40%) &nbsp;|&nbsp;
  <b>Realized P&amp;L MTD:</b> ${cc_realized:+,.0f}
</p>
<table border="1" cellpadding="4" style="border-collapse:collapse">
  <tr><th>Underlying</th><th>Shares</th><th>Basis/sh</th><th>Call sold</th><th>DTE</th><th>Premium rcvd</th><th>Type</th></tr>
  {cc_rows_html}
</table>

<h3>Moves Made Today</h3>
<ul>{moves_html}</ul>

<h3>Planned Moves / Next Actions</h3>
<ul>{planned_html}</ul>
{friday_section}
"""
    subject = f"Trading Desk — Daily Scorecard {today}" + (" (Week in Review)" if is_friday else "")
    return subject, html


def _dte(expiry_str: str) -> int:
    """Days to expiration from today (local import of CC helper)."""
    try:
        from datetime import date as _d
        return (_d.fromisoformat(expiry_str) - _d.today()).days
    except Exception:
        return -1


def _send_session_email(prev: str, new: str, equity: float, daily_pnl: float,
                        n: int, wins: int, realized: float, open_list: str,
                        cc: dict | None = None):
    """Send a Gmail performance summary email at session flip.
    For equities-close (prev='equities'), sends the full scorecard instead.
    """
    try:
        is_equities_close = (prev == "equities")
        is_friday = date.today().weekday() == 4  # 0=Mon, 4=Fri
        if is_equities_close:
            subject, html_body = _build_scorecard_html(prev, new, is_friday=is_friday)
        else:
            # Morning / other flips: compact summary + CC line
            cc_html = ""
            if cc:
                cc_html = (
                    f"<p><b>CC book:</b> {cc['underlyings']} underlyings "
                    f"({cc['covered']} covered, {cc['uncovered']} naked) &nbsp;|&nbsp; "
                    f"Premium Month-To-Date (MTD): ${cc['premium_mtd']:,.0f} &nbsp;|&nbsp; "
                    f"Realized P&amp;L: ${cc['realized_pnl']:+,.0f}</p>"
                )
            subject = f"Trading Desk — {prev.upper()} session close"
            html_body = (
                f"<h3>{prev.upper()} &rarr; {new.upper()}</h3>"
                f"<p><b>Equity:</b> ${equity:,.0f} &nbsp; (today {daily_pnl:+,.0f})</p>"
                f"<p><b>Closed today:</b> {n} trade{'s' if n != 1 else ''}, "
                f"{wins} win{'s' if wins != 1 else ''}, net ${realized:+,.0f}</p>"
                f"<p><b>Open now:</b> {open_list}</p>"
                f"{cc_html}"
            )
        _gmail_send(subject, html_body)
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
    _send_session_email(prev_session, new_session, equity, daily_pnl, n, wins, realized, open_list, cc=cc)
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
    ap.add_argument("--test-email", nargs="?", const="normal", metavar="friday",
                    help="Render scorecard to stdout (pass 'friday' to force the week-in-review section)")
    ap.add_argument("--send-test-email", nargs="?", const="normal", metavar="friday",
                    help="Same as --test-email but actually sends to brian@olivetreeinv.io")
    args = ap.parse_args()

    if args.test:
        w = _win_stats([10, 10, -5, -5, -10])
        assert w["n"] == 5 and abs(w["win_rate"] - 0.4) < 1e-9, w
        assert abs(w["avg_win"] - 10) < 1e-9 and abs(w["avg_loss"] - (20/3)) < 1e-9, w
        assert abs(w["profit_factor"] - 1.0) < 1e-9, w          # 20 won / 20 lost
        assert _win_stats([])["win_rate"] == 0.0
        assert _win_stats([5, 5])["profit_factor"] == float("inf")  # no losses
        class _R:  # stub row
            def __init__(self, c): self.spy_close = c
        assert abs(_spy_same_window([_R(100), _R(None), _R(110)]) - 0.10) < 1e-9
        assert _spy_same_window([_R(100)]) == 0.0
        print("  ✅ _win_stats + _spy_same_window self-checks passed.")
        return

    if args.test_email or args.send_test_email:
        flag_val = args.test_email or args.send_test_email
        force_friday = (flag_val == "friday")
        is_friday = force_friday or (date.today().weekday() == 4)
        subject, html_body = _build_scorecard_html("equities", "crypto", is_friday=is_friday)
        if args.send_test_email:
            try:
                _gmail_send(subject, html_body)
                print(f"  📧 Test scorecard email sent to brian@olivetreeinv.io")
                print(f"  Subject: {subject}")
            except Exception as e:
                print(f"  ⚠️  Send failed: {e}")
        else:
            print(f"\nSubject: {subject}\n{'─'*60}")
            print(html_body)
    elif args.alert:
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
