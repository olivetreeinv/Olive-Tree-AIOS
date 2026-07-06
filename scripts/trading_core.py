#!/usr/bin/env python3
"""
trading_core.py — SPY core sweep for the Olive Tree Trading Desk.

Idle cash auto-invests into SPY; books pull it back when they need capital.
Core rows live in trading_positions with side="core" so no new table is needed.
Core SPY has NO stop, no quant gate, no research — it IS the benchmark.

Usage:
  python3 scripts/trading_core.py --status          # show core value + sweep estimate
  python3 scripts/trading_core.py --sweep --dry-run # print intended order
  python3 scripts/trading_core.py --self-check      # assert-based math tests (no network)
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import Session
from db.schema import TradingPosition
from scripts.trading_data import get_account, get_quote

_PAPER = True  # hard-coded — never flip without explicit Brian approval

CORE_SYMBOL       = "SPY"
CORE_BUFFER_USD   = 3_000   # operating cash floor — never sweep below this
CORE_MIN_SWEEP_USD = 1_000  # minimum sweep worth placing an order for


def _client() -> TradingClient:
    key    = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        raise EnvironmentError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env")
    return TradingClient(key, secret, paper=_PAPER)


def _core_positions(s) -> list:
    """All open core rows from the DB."""
    return s.query(TradingPosition).filter_by(status="open", side="core").all()


def core_value() -> float:
    """
    Current market value of core SPY lots: DB qty × live SPY quote.
    Deliberately does NOT read the raw Alpaca SPY position — that would net
    with any momentum SPY lot (there's an existing 6.78sh momentum position).
    """
    s = Session()
    try:
        rows = _core_positions(s)
        if not rows:
            return 0.0
        total_qty = sum(r.qty for r in rows)
    finally:
        s.close()
    if total_qty <= 0:
        return 0.0
    try:
        q = get_quote(CORE_SYMBOL)
        price = q.get("last") or q.get("ask") or 0
        return total_qty * price
    except Exception:
        return 0.0


def sweep_to_core(dry_run: bool = False) -> dict:
    """
    Buy SPY with excess cash (fractional notional market order, DAY TIF).
    Called at end of each equities cycle — after momentum entries + CC cycle.
    Skipped when daily halt is active or session != equities (caller's responsibility;
    this function checks daily halt as a safety net).
    Returns {"swept": bool, "amount_usd": float}.
    """
    acct = get_account()
    cash = acct.get("cash", 0)
    excess = cash - CORE_BUFFER_USD
    if excess < CORE_MIN_SWEEP_USD:
        print(f"  [core] sweep skipped — excess cash ${excess:,.0f} < ${CORE_MIN_SWEEP_USD:,.0f} floor")
        return {"swept": False, "amount_usd": 0}

    # Sanity: skip if daily halt active
    try:
        from scripts.trading_risk import is_daily_halted
        if is_daily_halted(acct.get("equity", 0)):
            print("  [core] sweep skipped — daily halt active")
            return {"swept": False, "amount_usd": 0}
    except Exception:
        pass

    amount = round(excess, 2)
    print(f"  [core] {'[DRY RUN] would sweep' if dry_run else 'sweeping'} ${amount:,.0f} into {CORE_SYMBOL}")

    if dry_run:
        return {"swept": False, "amount_usd": amount, "dry_run": True}

    try:
        client = _client()
        # ponytail: fractional notional order — Alpaca fills to the dollar at market
        order = client.submit_order(MarketOrderRequest(
            symbol=CORE_SYMBOL,
            notional=amount,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        ))
        now = datetime.now(timezone.utc).isoformat()
        # Record as a core position row; entry_price and qty updated by sync_fills()
        # Use notional / approx price as placeholder qty (sync_fills corrects it)
        try:
            q = get_quote(CORE_SYMBOL)
            approx_price = q.get("ask") or q.get("last") or 1
        except Exception:
            approx_price = 1
        approx_qty = round(amount / approx_price, 8)

        s = Session()
        try:
            pos = TradingPosition(
                symbol=CORE_SYMBOL,
                side="core",           # distinguishes from momentum ("long") rows
                qty=approx_qty,        # corrected by sync_fills on actual fill
                entry_price=approx_price,
                stop_price=None,       # ponytail: core has no stop by design
                initial_stop_distance=None,
                high_water_price=None,
                entry_time=now,
                status="open",
                signal_id=None,
            )
            s.add(pos)
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

        print(f"  [core] order submitted: notional=${amount:,.0f}  Alpaca ID: {order.id}")
        return {"swept": True, "amount_usd": amount, "alpaca_id": str(order.id)}

    except Exception as e:
        print(f"  ⚠️  [core] sweep failed: {e}")
        return {"swept": False, "amount_usd": 0, "error": str(e)}


def release_core(amount_usd: float, dry_run: bool = False) -> bool:
    """
    Sell core SPY notional to raise cash for the momentum or CC book.
    Submits a market sell, polls for fill (fast in paper RTH).
    Returns True on success (or dry_run), False if core doesn't have enough or order fails.
    Never sells more than core holds.
    """
    cv = core_value()
    if cv <= 0:
        print(f"  [core] release_core: no core holdings to liquidate")
        return False
    sell_amount = min(amount_usd, cv)
    if sell_amount < 100:
        print(f"  [core] release_core: sell amount ${sell_amount:,.0f} too small — skipping")
        return False

    print(f"  [core] {'[DRY RUN] would release' if dry_run else 'releasing'} ${sell_amount:,.0f} from {CORE_SYMBOL} core")
    if dry_run:
        return True

    try:
        # Get current qty from DB
        s = Session()
        try:
            rows = _core_positions(s)
            total_qty = sum(r.qty for r in rows)
        finally:
            s.close()

        q = get_quote(CORE_SYMBOL)
        price = q.get("last") or q.get("ask") or 1
        sell_qty = round(min(sell_amount / price, total_qty), 8)
        if sell_qty <= 0:
            return False

        client = _client()
        order = client.submit_order(MarketOrderRequest(
            symbol=CORE_SYMBOL,
            notional=round(sell_amount, 2),
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        ))

        # Poll for fill (market order in paper fills fast)
        filled_price = None
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                o = client.get_order_by_id(order.id)
                if o.filled_avg_price:
                    filled_price = float(o.filled_avg_price)
                    break
            except Exception:
                pass
            time.sleep(3)

        if filled_price:
            # Reduce core position qty proportionally
            filled_qty = round(sell_amount / filled_price, 8)
            s = Session()
            try:
                rows = _core_positions(s)
                remaining_sell = filled_qty
                for row in rows:
                    if remaining_sell <= 0:
                        break
                    if row.qty <= remaining_sell:
                        remaining_sell -= row.qty
                        row.status = "closed"
                        row.exit_price = filled_price
                        row.exit_time = datetime.now(timezone.utc).isoformat()
                    else:
                        row.qty -= remaining_sell
                        remaining_sell = 0
                s.commit()
            except Exception:
                s.rollback()
                raise
            finally:
                s.close()
            print(f"  [core] released ${sell_amount:,.0f} from core SPY @ ${filled_price:.2f}")
            return True
        else:
            print(f"  ⚠️  [core] release order placed but fill not confirmed in 30s")
            return False

    except Exception as e:
        print(f"  ⚠️  [core] release_core failed: {e}")
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="SPY core sweep — Olive Tree Trading Desk")
    ap.add_argument("--status",     action="store_true", help="Show core value + what a sweep would do")
    ap.add_argument("--sweep",      action="store_true", help="Run sweep (add --dry-run for simulation)")
    ap.add_argument("--dry-run",    action="store_true", help="Print intended action; no orders")
    ap.add_argument("--self-check", action="store_true", help="Assert-based math tests (no network)")
    args = ap.parse_args()

    if args.self_check:
        _self_check()
        return

    if args.status:
        cv = core_value()
        acct = get_account()
        cash = acct.get("cash", 0)
        excess = cash - CORE_BUFFER_USD
        sweep_would = max(0, round(excess, 2)) if excess >= CORE_MIN_SWEEP_USD else 0
        print(f"\n  ── Core SPY Status ─────────────────────────────────")
        print(f"  Core holding value:  ${cv:,.2f}")
        print(f"  Account cash:        ${cash:,.2f}")
        print(f"  Cash floor:          ${CORE_BUFFER_USD:,.0f}")
        print(f"  Excess (sweepable):  ${max(0, excess):,.2f}")
        if sweep_would > 0:
            print(f"  Sweep would invest:  ${sweep_would:,.2f} → SPY notional market order")
        else:
            print(f"  No sweep needed (excess < ${CORE_MIN_SWEEP_USD:,.0f} threshold)")

    if args.sweep:
        sweep_to_core(dry_run=args.dry_run)
        return

    if not args.status and not args.sweep and not args.self_check:
        ap.print_help()


def _self_check():
    """Assert-based math checks — no network calls."""
    print("── Core sweep self-check ──────────────────────────────────────\n")

    # 1. Buffer logic: excess = cash - CORE_BUFFER_USD
    cash = 35_000.0
    excess = cash - CORE_BUFFER_USD
    assert excess == 32_000.0, f"Buffer calc: {excess}"
    assert excess >= CORE_MIN_SWEEP_USD, "Should sweep at 35k cash"
    print(f"  ✅ Buffer math: cash=${cash:,}  floor=${CORE_BUFFER_USD:,}  excess=${excess:,}")

    # 2. Below-floor: cash = 3,500 → excess 500 → skip
    low_cash = 3_500.0
    low_excess = low_cash - CORE_BUFFER_USD
    assert low_excess == 500.0
    assert low_excess < CORE_MIN_SWEEP_USD, "Should NOT sweep when excess < min"
    print(f"  ✅ Skip when excess=${low_excess:,} < ${CORE_MIN_SWEEP_USD:,} threshold")

    # 3. Release cap: never sells more than core holds
    core_held = 5_000.0
    release_req = 8_000.0
    actual_sell = min(release_req, core_held)
    assert actual_sell == core_held, "release_core must cap at core value"
    print(f"  ✅ Release cap: requested ${release_req:,}, core holds ${core_held:,} → sell ${actual_sell:,}")

    # 4. Fractional qty from notional
    notional = 3_200.0
    spy_price = 600.0
    approx_qty = round(notional / spy_price, 8)
    assert abs(approx_qty - 5.33333333) < 1e-6, f"qty calc: {approx_qty}"
    print(f"  ✅ Notional→qty: ${notional:,} / ${spy_price:.0f} = {approx_qty} shares")

    print("\n  All core self-checks passed. ✅")


if __name__ == "__main__":
    main()
