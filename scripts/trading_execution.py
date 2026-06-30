#!/usr/bin/env python3
"""
trading_execution.py — Execution agent for the Olive Tree Trading Desk.

Submits paper orders to Alpaca, records fills to SQLite, and handles stop-loss
order placement. Always paper=True — no real money until Brian explicitly approves.

Usage:
  python3 scripts/trading_execution.py --test          # place + cancel a test order
  python3 scripts/trading_execution.py --positions     # show open paper positions
  python3 scripts/trading_execution.py --cancel-all    # cancel all open orders
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
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus, QueryOrderStatus

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import Session
from db.schema import TradingOrder, TradingPosition
from scripts.trading_risk import RiskDecision
from scripts.trading_data import get_vwap_context

_PAPER = True   # hard-coded — never flip without explicit Brian approval

# VWAP entry tolerance — allow entry up to this % above/below VWAP before skipping.
# Longs: skip if price > VWAP + VWAP_BUFFER (chasing). Shorts: skip if price < VWAP - VWAP_BUFFER.
_VWAP_BUFFER_PCT = 0.50   # 0.5% — tight enough to enforce discipline, loose enough for real entries


def vwap_entry_ok(symbol: str, side: str) -> tuple[bool, str]:
    """
    Returns (ok, reason). Only runs for equities (no "/" in symbol) in regular session.
    Skips the check during pre/after-market where VWAP is previous session's.
    """
    if "/" in symbol:
        return True, ""   # crypto — no VWAP filter

    ctx = get_vwap_context(symbol)
    if not ctx or ctx.get("session") != "regular":
        return True, ""   # pre/after-market: don't gate on stale VWAP

    pct = ctx["price_vs_vwap_pct"]  # positive = above VWAP

    if side == "long" and pct > _VWAP_BUFFER_PCT:
        return False, f"Price is {pct:.2f}% above VWAP ({ctx['vwap']}) — waiting for pullback"
    if side == "short" and pct < -_VWAP_BUFFER_PCT:
        return False, f"Price is {abs(pct):.2f}% below VWAP ({ctx['vwap']}) — waiting for bounce"

    return True, ""

def _client() -> TradingClient:
    key    = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        raise EnvironmentError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env")
    return TradingClient(key, secret, paper=_PAPER)


def submit_order(decision: RiskDecision, signal_id: int | None = None) -> dict:
    """
    Submit a market order for an approved RiskDecision.
    Records the order + a new open Position in SQLite.
    Returns a summary dict.
    """
    if not decision.approved:
        return {"submitted": False, "reason": decision.veto_reason}

    # VWAP entry timing filter — skip if price has already moved away from VWAP
    vwap_ok, vwap_reason = vwap_entry_ok(decision.symbol, decision.side)
    if not vwap_ok:
        print(f"  ⏳ VWAP filter: {vwap_reason} — skipping this cycle")
        return {"submitted": False, "reason": vwap_reason}

    client = _client()
    side   = OrderSide.BUY if decision.side == "long" else OrderSide.SELL

    req = MarketOrderRequest(
        symbol=decision.symbol,
        qty=decision.qty,
        side=side,
        time_in_force=TimeInForce.DAY,
    )

    order = client.submit_order(req)
    now   = datetime.now(timezone.utc).isoformat()

    s = Session()
    try:
        # stop_price deferred — will be set from actual fill price in sync_fills()
        pos = TradingPosition(
            symbol=decision.symbol,
            side=decision.side,
            qty=decision.qty,
            entry_price=decision.entry_price,  # pre-order quote; updated by sync_fills()
            stop_price=None,
            entry_time=now,
            status="open",
            signal_id=signal_id,
        )
        s.add(pos)
        s.flush()

        ord_row = TradingOrder(
            alpaca_id=str(order.id),
            symbol=decision.symbol,
            side=decision.side,
            qty=decision.qty,
            order_type="market",
            status=str(order.status),
            submitted_at=now,
            position_id=pos.id,
        )
        s.add(ord_row)
        s.commit()
        pos_id = pos.id
        ord_id = ord_row.id
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

    print(f"  📤 Order submitted: {decision.symbol} {decision.side.upper()} {decision.qty} @ market")
    print(f"     Alpaca ID: {order.id}  stop=${decision.stop_price:.2f}")

    return {
        "submitted":   True,
        "alpaca_id":   str(order.id),
        "symbol":      decision.symbol,
        "side":        decision.side,
        "qty":         decision.qty,
        "stop_price":  decision.stop_price,
        "position_id": pos_id,
        "order_id":    ord_id,
        "status":      str(order.status),
    }


def cancel_order(alpaca_id: str) -> bool:
    """Cancel a pending order by Alpaca order ID."""
    client = _client()
    try:
        client.cancel_order_by_id(alpaca_id)
        s = Session()
        try:
            row = s.query(TradingOrder).filter_by(alpaca_id=alpaca_id).first()
            if row:
                row.status = "cancelled"
                s.commit()
        finally:
            s.close()
        print(f"  🚫 Cancelled order {alpaca_id}")
        return True
    except Exception as e:
        print(f"  ⚠️  Cancel failed for {alpaca_id}: {e}")
        return False


def cancel_all_orders() -> int:
    """Cancel all open paper orders. Returns count cancelled."""
    client = _client()
    cancelled = client.cancel_orders()
    n = len(cancelled) if cancelled else 0
    print(f"  🚫 Cancelled {n} open orders.")
    return n


def sync_fills() -> list[dict]:
    """
    Pull recent filled orders from Alpaca and update SQLite records.
    Call once per cycle to reconcile.
    """
    client = _client()
    # status=ALL so fully-filled (now-closed) market orders are still returned —
    # the default open-only list drops them before we ever see the fill price.
    orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.ALL, limit=200))
    from scripts.trading_risk import stop_price as _stop
    updates = []
    s = Session()
    try:
        for o in orders:
            row = s.query(TradingOrder).filter_by(alpaca_id=str(o.id)).first()
            if not row:
                continue
            row.status      = str(o.status)
            row.filled_qty  = float(o.filled_qty or 0)
            row.filled_price = float(o.filled_avg_price or 0)
            row.filled_at   = o.filled_at.isoformat() if o.filled_at else None
            # Always re-derive entry + stop from the actual fill, every sync —
            # not just on the first status change. A partial fill's avg price
            # keeps moving across cycles; the stop must track it or it goes stale
            # (and on a down-move ends up above entry, an inverted stop).
            if o.filled_avg_price and row.position_id:
                pos = s.query(TradingPosition).filter_by(id=row.position_id).first()
                if pos:
                    fill = float(o.filled_avg_price)
                    pos.entry_price = fill
                    pos.stop_price = round(_stop(fill, pos.side), 4)
            s.commit()
            updates.append({"alpaca_id": str(o.id), "status": row.status})
    finally:
        s.close()
    return updates


def get_open_positions() -> list[dict]:
    """Return open positions from SQLite."""
    s = Session()
    try:
        rows = s.query(TradingPosition).filter_by(status="open").all()
        return [
            {"id": p.id, "symbol": p.symbol, "side": p.side,
             "qty": p.qty, "entry_price": p.entry_price, "stop_price": p.stop_price}
            for p in rows
        ]
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser(description="Execution agent — Alpaca paper trading")
    ap.add_argument("--test",       action="store_true", help="Place then immediately cancel a test order")
    ap.add_argument("--positions",  action="store_true", help="Show open positions in SQLite")
    ap.add_argument("--cancel-all", action="store_true", help="Cancel all open Alpaca orders")
    args = ap.parse_args()

    if args.test:
        print("── Execution agent test ─────────────────────────────────────")
        print("  Submitting a test market order for 1 share of SPY (paper)...")
        from scripts.trading_risk import RiskDecision
        fake_decision = RiskDecision(
            approved=True, veto_reason="", symbol="SPY", side="long",
            qty=1.0, position_usd=734.0, stop_price=726.66, entry_price=734.0,
        )
        result = submit_order(fake_decision, signal_id=None)
        print(f"  Result: {result}")

        if result.get("submitted") and result.get("alpaca_id"):
            time.sleep(2)
            print("  Cancelling test order...")
            cancel_order(result["alpaca_id"])
        print("  ✅ Execution test complete.")

    elif args.positions:
        positions = get_open_positions()
        if not positions:
            print("  No open positions.")
        for p in positions:
            print(f"  {p['symbol']} {p['side'].upper()} qty={p['qty']}  entry={p['entry_price']}  stop={p['stop_price']}")

    elif args.cancel_all:
        cancel_all_orders()

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
