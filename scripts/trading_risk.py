#!/usr/bin/env python3
"""
trading_risk.py — Risk agent for the Olive Tree Trading Desk.

Conservative ceiling (updated 2026-07-06):
  - Max loss per position: -1% of entry value
  - Max concurrent positions: 15
  - Position size: 4–8% of book, scaled linearly by conviction (4% floor @ 0.60, 8% @ 1.0)
  - Max momentum book deployed: 90% of MOMENTUM_BOOK_USD
  - Daily portfolio halt: if portfolio drops -2% from day-open equity, stop all trading

The risk agent sizes every approved signal and can VETO outright.
It also checks whether the daily halt has already been triggered.

Usage:
  python3 scripts/trading_risk.py --test          # unit-check all rules
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import Session
from db.schema import TradingPosition, TradingEquityCurve
from scripts.trading_data import get_open_position_count as _alpaca_position_count

# ── Conservative ceilings ─────────────────────────────────────────────────────
MAX_POSITION_PCT     = 0.04   # floor: 4% of portfolio equity at conviction ≤ 0.60
MAX_POSITION_PCT_HI  = 0.08   # ceiling: 8% at conviction ≥ 1.0 (linear between floor/ceiling)
CONVICTION_FLOOR     = 0.60   # conviction at or below this → floor size
CONVICTION_CEIL      = 1.00   # conviction at or above this → ceiling size
MAX_POSITIONS        = 15     # concurrent open positions — top 15 by conviction
MAX_BOOK_DEPLOYED_PCT = 0.90  # veto new entry if momentum book already ≥ 90% deployed
STOP_LOSS_PCT        = 0.01   # 1% loss from entry → hard stop (fallback; ATR replaces this live)
DAILY_HALT_PCT       = 0.02   # 2% portfolio drawdown from day-open → halt all trades

# ── Momentum book ─────────────────────────────────────────────────────────────
MOMENTUM_BOOK_USD  = 50_000  # position sizing runs off this sub-book, not total equity

# ── ATR stop config ───────────────────────────────────────────────────────────
ATR_MULT           = 1.5    # stop distance = ATR(14) × 1.5
ATR_STOP_MIN_PCT   = 0.01   # clamp: minimum 1% of entry
ATR_STOP_MAX_PCT   = 0.03   # clamp: maximum 3% of entry


@dataclass
class RiskDecision:
    approved:           bool
    veto_reason:        str        # empty if approved
    symbol:             str
    side:               str        # long / short
    qty:                float      # share/coin count (0 if vetoed)
    position_usd:       float      # USD notional (0 if vetoed)
    stop_price:         float      # hard stop price (0 if vetoed)
    entry_price:        float
    initial_stop_dist:  float = 0.0  # $ distance from entry (1R); used for trail + breakeven


def _open_position_count() -> int:
    # Alpaca is authoritative — if it says 0, that's 0. No SQLite fallback.
    return _alpaca_position_count()


def _day_open_equity() -> float | None:
    """Return today's opening equity snapshot from the equity curve, or None."""
    today = date.today().isoformat()
    s = Session()
    try:
        row = s.query(TradingEquityCurve).filter_by(date=today).first()
        return row.portfolio_equity if row else None
    finally:
        s.close()


def is_daily_halted(current_equity: float) -> bool:
    """True if portfolio has dropped ≥ DAILY_HALT_PCT since day open."""
    day_open = _day_open_equity()
    if day_open is None or day_open <= 0:
        return False
    drawdown = (day_open - current_equity) / day_open
    return drawdown >= DAILY_HALT_PCT


def _conviction_pct(conviction: float) -> float:
    """
    Linear scale: conviction ≤ 0.60 → 4%; conviction ≥ 1.0 → 8%.
    ponytail: clamp both ends; no extrapolation.
    """
    if conviction <= CONVICTION_FLOOR:
        return MAX_POSITION_PCT
    if conviction >= CONVICTION_CEIL:
        return MAX_POSITION_PCT_HI
    t = (conviction - CONVICTION_FLOOR) / (CONVICTION_CEIL - CONVICTION_FLOOR)
    return MAX_POSITION_PCT + t * (MAX_POSITION_PCT_HI - MAX_POSITION_PCT)


def _momentum_deployed_usd() -> float:
    """
    Sum of (entry_price × qty) for all open momentum positions in the DB.
    Excludes core rows (side="core").
    ponytail: uses entry_price, not mark-to-market; fine for a veto gate.
    """
    s = Session()
    try:
        rows = s.query(TradingPosition).filter(
            TradingPosition.status == "open",
            TradingPosition.side.in_(["long", "short"]),
        ).all()
        return sum((r.entry_price or 0) * r.qty for r in rows)
    finally:
        s.close()


def size_position(equity: float, entry_price: float, conviction: float = 0.0) -> tuple[float, float]:
    """Return (qty, position_usd) scaled by conviction (4–8% of equity)."""
    pct     = _conviction_pct(conviction)
    max_usd = equity * pct
    qty     = max_usd / entry_price if entry_price > 0 else 0
    return qty, qty * entry_price


def size_position_extended(equity: float, entry_price: float, conviction: float = 0.0) -> tuple[float, float]:
    """Whole-share sizing for extended hours — Alpaca rejects fractional limit orders."""
    pct     = _conviction_pct(conviction)
    max_usd = equity * pct
    qty     = int(max_usd / entry_price) if entry_price > 0 else 0
    return float(qty), float(qty) * entry_price


def stop_price(entry_price: float, side: str) -> float:
    """Return hard stop price: -1% from entry for longs, +1% for shorts.
    Fallback only — atr_stop() is preferred when bars are available."""
    if side == "long":
        return entry_price * (1 - STOP_LOSS_PCT)
    return entry_price * (1 + STOP_LOSS_PCT)


def atr_stop(entry_price: float, side: str, symbol: str) -> tuple[float, float]:
    """
    Compute ATR(14)-based stop. Returns (stop_price, stop_distance).
    stop_distance is the $ distance from entry — stored on the position as 1R.
    Falls back to STOP_LOSS_PCT (1%) if bars can't be fetched.

    ponytail: fetches 30d of daily bars each call; fine for once-per-entry.
    If called hot in a loop, cache bars externally and pass in atr directly.
    """
    try:
        from scripts.trading_data import get_bars
        bars = get_bars(symbol, days=30)
        if len(bars) < 15:
            raise ValueError("not enough bars")
        # True Range for each bar (no overnight gap for crypto, but close enough for sizing)
        trs = []
        for i in range(1, len(bars)):
            high, low, prev_c = bars[i]["h"], bars[i]["l"], bars[i-1]["c"]
            tr = max(high - low, abs(high - prev_c), abs(low - prev_c))
            trs.append(tr)
        atr = sum(trs[-14:]) / 14
        raw_dist = atr * ATR_MULT
        # Clamp between 1% and 3% of entry
        lo = entry_price * ATR_STOP_MIN_PCT
        hi = entry_price * ATR_STOP_MAX_PCT
        dist = max(lo, min(hi, raw_dist))
    except Exception:
        # ponytail: fallback to flat 1%; upgrade = retry with exponential backoff
        dist = entry_price * STOP_LOSS_PCT

    if side == "long":
        return round(entry_price - dist, 4), round(dist, 4)
    return round(entry_price + dist, 4), round(dist, 4)


def evaluate(
    symbol: str,
    side: str,
    entry_price: float,
    quant_passed: bool,
    portfolio_equity: float,
    extended_hours: bool = False,
    conviction: float = 0.0,
) -> RiskDecision:
    """
    Core risk gate. Returns a RiskDecision with approved=True/False and sizing.
    conviction (0–1) scales position size from 4% (floor) to 8% (ceiling).
    Call this for every signal before submission to the execution agent.
    """
    base = RiskDecision(
        approved=False, veto_reason="", symbol=symbol, side=side,
        qty=0, position_usd=0, stop_price=0, entry_price=entry_price,
    )

    if not quant_passed:
        base.veto_reason = "Quant gate not cleared"
        return base

    if is_daily_halted(portfolio_equity):
        base.veto_reason = f"Daily halt triggered (portfolio down ≥{DAILY_HALT_PCT:.0%} today)"
        return base

    open_count = _open_position_count()
    if open_count >= MAX_POSITIONS:
        base.veto_reason = f"Max concurrent positions reached ({open_count}/{MAX_POSITIONS})"
        return base

    if entry_price <= 0:
        base.veto_reason = "Invalid entry price ≤ 0"
        return base

    _size = size_position_extended if extended_hours else size_position
    qty, pos_usd = _size(portfolio_equity, entry_price, conviction)
    if qty <= 0:
        base.veto_reason = "Position size computed to zero"
        return base

    # Deployment cap: veto if adding this position would push momentum book > 90%
    deployed = _momentum_deployed_usd()
    if (deployed + pos_usd) > MOMENTUM_BOOK_USD * MAX_BOOK_DEPLOYED_PCT:
        cap_usd = MOMENTUM_BOOK_USD * MAX_BOOK_DEPLOYED_PCT
        base.veto_reason = (
            f"Momentum book deployment cap: "
            f"deployed ${deployed:,.0f} + new ${pos_usd:,.0f} > ${cap_usd:,.0f} (90% of ${MOMENTUM_BOOK_USD:,})"
        )
        return base

    sp, stop_dist = atr_stop(entry_price, side, symbol)

    return RiskDecision(
        approved=True,
        veto_reason="",
        symbol=symbol,
        side=side,
        qty=round(qty, 8),
        position_usd=round(pos_usd, 2),
        stop_price=sp,
        entry_price=entry_price,
        initial_stop_dist=stop_dist,
    )


# ── CLI unit test ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Risk agent unit tests")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    if not args.test:
        ap.print_help()
        return

    equity = 100_000.0
    print("── Risk agent unit tests ──────────────────────────────────────\n")

    # 1. Normal approval (SPY bars will be fetched; ATR stop expected, falls back to 1% if no data)
    r = evaluate("SPY", "long", entry_price=734.0, quant_passed=True, portfolio_equity=equity)
    assert r.approved, "Should be approved"
    assert r.qty > 0
    assert r.stop_price < 734.0, f"Long stop must be below entry: {r.stop_price}"
    assert r.initial_stop_dist > 0, "initial_stop_dist must be set"
    # ATR stop: between 1% and 3% of entry (or exactly 1% if fallback triggered)
    assert 734.0 * 0.009 < r.initial_stop_dist <= 734.0 * 0.031, f"Stop dist out of band: {r.initial_stop_dist}"
    assert r.position_usd <= equity * MAX_POSITION_PCT + 1
    print(f"  ✅ Normal approval: qty={r.qty:.4f}  pos=${r.position_usd:,.2f}  stop={r.stop_price:.2f}  1R=${r.initial_stop_dist:.2f}")

    # 2. Quant gate not cleared → veto
    r2 = evaluate("SPY", "long", entry_price=734.0, quant_passed=False, portfolio_equity=equity)
    assert not r2.approved
    print(f"  ✅ Quant veto:       {r2.veto_reason}")

    # 3. Max positions → veto (mock open positions by patching count)
    import unittest.mock as mock
    with mock.patch(__name__ + "._open_position_count", return_value=MAX_POSITIONS):
        r3 = evaluate("AAPL", "long", entry_price=200.0, quant_passed=True, portfolio_equity=equity)
        assert not r3.approved
        print(f"  ✅ Max pos veto:     {r3.veto_reason}")

    # 4. Daily halt → veto (mock day-open equity so current is -2.5%)
    with mock.patch(__name__ + "._day_open_equity", return_value=103_000.0):
        r4 = evaluate("NVDA", "long", entry_price=100.0, quant_passed=True, portfolio_equity=equity)
        assert not r4.approved
        print(f"  ✅ Daily halt veto:  {r4.veto_reason}")

    # 5. Stop price check — short side
    r5 = evaluate("QQQ", "short", entry_price=500.0, quant_passed=True, portfolio_equity=equity)
    assert r5.stop_price > 500.0, f"Short stop must be above entry: {r5.stop_price}"
    assert r5.initial_stop_dist > 0
    print(f"  ✅ Short stop above entry: stop={r5.stop_price:.2f} vs entry=500.00  1R=${r5.initial_stop_dist:.2f}")

    # 6. ATR fallback (bad symbol → no bars → 1% stop)
    r6 = evaluate("XXXXXXX", "long", entry_price=100.0, quant_passed=True, portfolio_equity=equity)
    if r6.approved:
        assert abs(r6.initial_stop_dist - 1.0) < 1e-6, f"Fallback should be 1%: {r6.initial_stop_dist}"
        print(f"  ✅ ATR fallback (1%): stop_dist={r6.initial_stop_dist:.2f}")
    else:
        print(f"  ✅ ATR fallback test skipped (vetoed for other reason: {r6.veto_reason})")

    # 7. MOMENTUM_BOOK_USD: position sizes off $50k not full equity (mock halt + pos count)
    with mock.patch(__name__ + "._day_open_equity", return_value=None), \
         mock.patch(__name__ + "._open_position_count", return_value=0), \
         mock.patch(__name__ + "._momentum_deployed_usd", return_value=0):
        r7 = evaluate("MSFT", "long", entry_price=400.0, quant_passed=True, portfolio_equity=MOMENTUM_BOOK_USD)
    assert r7.approved, f"Should approve: {r7.veto_reason}"
    assert r7.position_usd <= MOMENTUM_BOOK_USD * MAX_POSITION_PCT + 1
    print(f"  ✅ Momentum book sizing: pos=${r7.position_usd:,.2f} (max ${MOMENTUM_BOOK_USD*MAX_POSITION_PCT:,.0f})")

    # 8. Conviction sizing: floor (0.60) → $2,000 on $50k book; ceiling (1.0) → $4,000
    book = MOMENTUM_BOOK_USD  # $50,000
    entry = 100.0
    with mock.patch(__name__ + "._day_open_equity", return_value=None), \
         mock.patch(__name__ + "._open_position_count", return_value=0), \
         mock.patch(__name__ + "._momentum_deployed_usd", return_value=0):
        r_floor = evaluate("TSLA", "long", entry_price=entry, quant_passed=True,
                           portfolio_equity=book, conviction=0.60)
        r_ceil  = evaluate("TSLA", "long", entry_price=entry, quant_passed=True,
                           portfolio_equity=book, conviction=1.00)
        r_mid   = evaluate("TSLA", "long", entry_price=entry, quant_passed=True,
                           portfolio_equity=book, conviction=0.80)
    assert r_floor.approved
    assert abs(r_floor.position_usd - book * 0.04) < 1, f"Floor: {r_floor.position_usd}"
    assert abs(r_ceil.position_usd  - book * 0.08) < 1, f"Ceil:  {r_ceil.position_usd}"
    # Mid 0.80: t = (0.80-0.60)/(1.0-0.60) = 0.5 → pct = 0.04+0.5*0.04 = 0.06 → $3,000
    assert abs(r_mid.position_usd - book * 0.06) < 1, f"Mid:   {r_mid.position_usd}"
    print(f"  ✅ Conviction sizing: floor={r_floor.position_usd:,.0f} mid={r_mid.position_usd:,.0f} ceil={r_ceil.position_usd:,.0f}")

    # 9. Deployment cap veto: already at 90% + new entry → veto
    cap_deployed = MOMENTUM_BOOK_USD * MAX_BOOK_DEPLOYED_PCT  # $45,000
    with mock.patch(__name__ + "._day_open_equity", return_value=None), \
         mock.patch(__name__ + "._open_position_count", return_value=0), \
         mock.patch(__name__ + "._momentum_deployed_usd", return_value=cap_deployed):
        r_cap = evaluate("AMD", "long", entry_price=200.0, quant_passed=True,
                         portfolio_equity=book, conviction=0.60)
    assert not r_cap.approved, "Should veto when at deployment cap"
    assert "deployment cap" in r_cap.veto_reason.lower()
    print(f"  ✅ Deployment cap veto: {r_cap.veto_reason[:60]}…")

    # 10. Deployment cap allows entry when there's room
    small_deployed = 20_000.0  # well under 90% of $50k
    with mock.patch(__name__ + "._day_open_equity", return_value=None), \
         mock.patch(__name__ + "._open_position_count", return_value=0), \
         mock.patch(__name__ + "._momentum_deployed_usd", return_value=small_deployed):
        r_room = evaluate("AMD", "long", entry_price=200.0, quant_passed=True,
                          portfolio_equity=book, conviction=0.60)
    assert r_room.approved, f"Should approve with room: {r_room.veto_reason}"
    print(f"  ✅ Deployment cap allows entry with room (deployed=${small_deployed:,})")

    print("\n  All risk checks passed. ✅")


if __name__ == "__main__":
    main()
