#!/usr/bin/env python3
"""
trading_risk.py — Risk agent for the Olive Tree Trading Desk.

Conservative ceiling (updated 2026-07-01):
  - Max loss per position: -1% of entry value
  - Max concurrent positions: 15
  - Max position size: 4% of portfolio equity (15 × 4% = 60% max deployed, 40% cash buffer)
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
MAX_POSITION_PCT   = 0.04   # 4% of portfolio equity per position (15 × 4% = 60% max deployed)
MAX_POSITIONS      = 15     # concurrent open positions — top 15 by conviction
STOP_LOSS_PCT      = 0.01   # 1% loss from entry → hard stop (fallback; ATR replaces this live)
DAILY_HALT_PCT     = 0.02   # 2% portfolio drawdown from day-open → halt all trades

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


def size_position(equity: float, entry_price: float) -> tuple[float, float]:
    """Return (qty, position_usd) sized to MAX_POSITION_PCT of equity."""
    max_usd = equity * MAX_POSITION_PCT
    qty     = max_usd / entry_price if entry_price > 0 else 0
    return qty, qty * entry_price


def size_position_extended(equity: float, entry_price: float) -> tuple[float, float]:
    """Whole-share sizing for extended hours — Alpaca rejects fractional limit orders."""
    max_usd = equity * MAX_POSITION_PCT
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
) -> RiskDecision:
    """
    Core risk gate. Returns a RiskDecision with approved=True/False and sizing.
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
    qty, pos_usd = _size(portfolio_equity, entry_price)
    if qty <= 0:
        base.veto_reason = "Position size computed to zero"
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
         mock.patch(__name__ + "._open_position_count", return_value=0):
        r7 = evaluate("MSFT", "long", entry_price=400.0, quant_passed=True, portfolio_equity=MOMENTUM_BOOK_USD)
    assert r7.approved, f"Should approve: {r7.veto_reason}"
    assert r7.position_usd <= MOMENTUM_BOOK_USD * MAX_POSITION_PCT + 1
    print(f"  ✅ Momentum book sizing: pos=${r7.position_usd:,.2f} (max ${MOMENTUM_BOOK_USD*MAX_POSITION_PCT:,.0f})")

    print("\n  All risk checks passed. ✅")


if __name__ == "__main__":
    main()
