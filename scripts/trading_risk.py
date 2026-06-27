#!/usr/bin/env python3
"""
trading_risk.py — Risk agent for the Olive Tree Trading Desk.

Conservative ceiling (locked 2026-06-26):
  - Max loss per position: -1% of entry value
  - Max concurrent positions: 5
  - Max position size: 5% of portfolio equity
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
MAX_POSITION_PCT   = 0.05   # 5% of portfolio equity per position
MAX_POSITIONS      = 5      # concurrent open positions
STOP_LOSS_PCT      = 0.01   # 1% loss from entry → hard stop
DAILY_HALT_PCT     = 0.02   # 2% portfolio drawdown from day-open → halt all trades


@dataclass
class RiskDecision:
    approved:     bool
    veto_reason:  str        # empty if approved
    symbol:       str
    side:         str        # long / short
    qty:          float      # share/coin count (0 if vetoed)
    position_usd: float      # USD notional (0 if vetoed)
    stop_price:   float      # hard stop price (0 if vetoed)
    entry_price:  float


def _open_position_count() -> int:
    # ponytail: Alpaca is source of truth — works in cloud where local DB is empty
    count = _alpaca_position_count()
    if count > 0:
        return count
    s = Session()
    try:
        return s.query(TradingPosition).filter_by(status="open").count()
    finally:
        s.close()


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


def stop_price(entry_price: float, side: str) -> float:
    """Return hard stop price: -1% from entry for longs, +1% for shorts."""
    if side == "long":
        return entry_price * (1 - STOP_LOSS_PCT)
    return entry_price * (1 + STOP_LOSS_PCT)


def evaluate(
    symbol: str,
    side: str,
    entry_price: float,
    quant_passed: bool,
    portfolio_equity: float,
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

    qty, pos_usd = size_position(portfolio_equity, entry_price)
    if qty <= 0:
        base.veto_reason = "Position size computed to zero"
        return base

    return RiskDecision(
        approved=True,
        veto_reason="",
        symbol=symbol,
        side=side,
        qty=round(qty, 8),
        position_usd=round(pos_usd, 2),
        stop_price=round(stop_price(entry_price, side), 4),
        entry_price=entry_price,
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

    # 1. Normal approval
    r = evaluate("SPY", "long", entry_price=734.0, quant_passed=True, portfolio_equity=equity)
    assert r.approved, "Should be approved"
    assert r.qty > 0
    assert r.stop_price < 734.0
    assert r.position_usd <= equity * MAX_POSITION_PCT + 1
    print(f"  ✅ Normal approval: qty={r.qty:.4f}  pos=${r.position_usd:,.2f}  stop={r.stop_price:.2f}")

    # 2. Quant gate not cleared → veto
    r2 = evaluate("SPY", "long", entry_price=734.0, quant_passed=False, portfolio_equity=equity)
    assert not r2.approved
    print(f"  ✅ Quant veto:       {r2.veto_reason}")

    # 3. Max positions → veto (mock open positions by patching count)
    import unittest.mock as mock
    with mock.patch(__name__ + "._open_position_count", return_value=5):
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
    assert r5.stop_price > 500.0, "Short stop must be above entry"
    print(f"  ✅ Short stop above entry: stop={r5.stop_price:.2f} vs entry=500.00")

    print("\n  All risk checks passed. ✅")


if __name__ == "__main__":
    main()
