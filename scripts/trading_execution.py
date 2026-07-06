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


def submit_order(decision: RiskDecision, signal_id: int | None = None, session: str = "equities") -> dict:
    """
    Submit an order for an approved RiskDecision.
    Extended hours: limit order (whole shares, extended_hours=True). Regular/crypto: market order.
    Records the order + a new open Position in SQLite.
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
    is_crypto = "/" in decision.symbol
    is_ext    = session == "extended" and not is_crypto

    if is_ext:
        # Extended hours: limit at ask (long) or bid (short); whole shares; extended_hours flag required.
        # entry_price comes from the ask — a short limit priced at the ask sits above the
        # market and never fills, so re-quote the bid for shorts.
        limit = decision.entry_price
        if decision.side == "short":
            try:
                from scripts.trading_data import get_quote
                limit = get_quote(decision.symbol).get("bid") or limit
            except Exception:
                pass  # keep entry_price — worst case the order rests unfilled, as before
        req = LimitOrderRequest(
            symbol=decision.symbol,
            qty=decision.qty,
            side=side,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit, 2),
            extended_hours=True,
        )
    else:
        # Regular session or crypto: market order.
        tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY
        req = MarketOrderRequest(
            symbol=decision.symbol,
            qty=decision.qty,
            side=side,
            time_in_force=tif,
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
            initial_stop_distance=decision.initial_stop_dist if decision.initial_stop_dist else None,
            high_water_price=decision.entry_price,
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


def _compute_pnl(side: str, entry: float, exit_price: float, qty: float) -> tuple[float, float]:
    """Realized P&L ($) and P&L % for a closed position. Pure — testable in isolation."""
    direction = 1 if side == "long" else -1
    pnl = direction * (exit_price - entry) * qty
    cost = entry * qty
    pnl_pct = (pnl / cost * 100) if cost else 0.0
    return round(pnl, 2), round(pnl_pct, 4)


def _close_position(s, pos, exit_price: float, exit_time: str | None, status: str = "stopped") -> None:
    """Mark a position closed and record realized P&L from a stop/exit fill."""
    pos.exit_price = exit_price
    pos.exit_time  = exit_time or datetime.now(timezone.utc).isoformat()
    pos.pnl, pos.pnl_pct = _compute_pnl(pos.side, pos.entry_price or 0, exit_price, pos.qty)
    pos.status = status
    print(f"  🔒 Closed {pos.symbol} {pos.side} exit=${exit_price:.2f} "
          f"pnl=${pos.pnl:+,.2f} ({pos.pnl_pct:+.2f}%)")


def check_stops(session: str = "equities") -> list[dict]:
    """
    Monitor-based stop-loss for ALL open positions, checked once per cycle.
    Extended hours: uses limit orders (extended_hours=True) for whole-share positions;
    fractional positions (entered during regular hours) are deferred to market open.
    Crypto: GTC market exit as before.

    Also handles breakeven + trailing ratchet:
      - When unrealized gain >= 1R (initial_stop_distance): move stop to entry (breakeven)
      - After that: trail at high_water_price - initial_stop_distance (longs)
        or low_water_price + initial_stop_distance (shorts)
    Stops never move backwards (long only ratchets up, short only down).

    ponytail: protection is per-cycle (~5 min) and only while the desk is running.
    A gap between cycles, or the Mac asleep, leaves a position unguarded until the
    next check. Upgrade path = tighter interval or a separate always-on watcher.
    """
    from scripts.trading_data import get_quote
    client = _client()
    fired = []
    s = Session()
    is_ext = session == "extended"
    try:
        positions = s.query(TradingPosition).filter_by(status="open").all()
        for pos in positions:
            if pos.side == "core":
                continue  # ponytail: core SPY has no stop by design — it IS the benchmark
            if not pos.stop_price:
                continue
            # Idempotent: a pending exit already submitted for this position.
            if s.query(TradingOrder).filter_by(position_id=pos.id, order_type="stop").first():
                continue
            price = get_quote(pos.symbol).get("last", 0)
            if not price:
                continue

            # ── Breakeven + trailing ratchet ──────────────────────────────────
            if pos.initial_stop_distance and pos.entry_price:
                trail_dist = pos.initial_stop_distance
                # Update high-water mark (long) / low-water mark (short)
                if pos.side == "long":
                    hwp = max(pos.high_water_price or pos.entry_price, price)
                    if hwp != pos.high_water_price:
                        pos.high_water_price = hwp
                else:
                    hwp = min(pos.high_water_price or pos.entry_price, price)
                    if hwp != pos.high_water_price:
                        pos.high_water_price = hwp

                unrealized = (price - pos.entry_price) if pos.side == "long" else (pos.entry_price - price)
                if unrealized >= trail_dist:
                    # At or past 1R — trail from high-water
                    if pos.side == "long":
                        new_stop = round(hwp - trail_dist, 4)
                        if new_stop > pos.stop_price:  # never ratchet down
                            pos.stop_price = new_stop
                            print(f"  🔼 Trail up {pos.symbol}: stop=${new_stop:.2f} (hwp=${hwp:.2f})")
                    else:
                        new_stop = round(hwp + trail_dist, 4)
                        if new_stop < pos.stop_price:  # never ratchet up for shorts
                            pos.stop_price = new_stop
                            print(f"  🔽 Trail dn {pos.symbol}: stop=${new_stop:.2f} (lwp=${hwp:.2f})")

            breached = ((pos.side == "long"  and price <= pos.stop_price) or
                        (pos.side == "short" and price >= pos.stop_price))
            if not breached:
                continue
            exit_side = OrderSide.SELL if pos.side == "long" else OrderSide.BUY
            is_crypto = "/" in pos.symbol
            is_whole  = pos.qty == int(pos.qty)

            # Extended hours: fractional equity positions can't exit until open — skip.
            if is_ext and not is_crypto and not is_whole:
                print(f"  ⏳ {pos.symbol} stop breached but fractional qty — queued for market open")
                continue

            try:
                if is_ext and not is_crypto:
                    ex = client.submit_order(LimitOrderRequest(
                        symbol=pos.symbol, qty=pos.qty, side=exit_side,
                        time_in_force=TimeInForce.DAY,
                        limit_price=round(pos.stop_price, 2),
                        extended_hours=True,
                    ))
                else:
                    ex = client.submit_order(MarketOrderRequest(
                        symbol=pos.symbol, qty=pos.qty, side=exit_side,
                        time_in_force=TimeInForce.GTC if is_crypto else TimeInForce.DAY))
            except Exception as e:
                print(f"  ⚠️  Stop exit failed for {pos.symbol} (pos {pos.id}): {e}")
                continue
            s.add(TradingOrder(
                alpaca_id=str(ex.id), symbol=pos.symbol,
                side="sell" if exit_side == OrderSide.SELL else "buy",
                qty=pos.qty, order_type="stop", stop_price=pos.stop_price,
                status=str(ex.status), submitted_at=datetime.now(timezone.utc).isoformat(),
                position_id=pos.id))
            print(f"  🛡  Stop breached — market exit {pos.symbol} @ ~${price:.2f} (stop ${pos.stop_price:.2f})")
            fired.append({"symbol": pos.symbol, "price": price, "stop": pos.stop_price})
        s.commit()
    finally:
        s.close()
    return fired


def sync_fills() -> list[dict]:
    """
    Pull recent filled orders from Alpaca and update SQLite records.
    Call once per cycle to reconcile.
    """
    client = _client()
    # status=ALL so fully-filled (now-closed) market orders are still returned —
    # the default open-only list drops them before we ever see the fill price.
    orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.ALL, limit=200))
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
            if o.filled_avg_price and row.position_id:
                pos = s.query(TradingPosition).filter_by(id=row.position_id).first()
                fill = float(o.filled_avg_price)
                if pos and row.order_type == "market" and pos.status == "open":
                    # Entry fill: derive the ATR stop from the actual fill. Re-derive while
                    # a partial fill's avg price is still moving; once the order is FILLED
                    # and a stop exists, leave it alone — the breakeven/trail ratchet in
                    # check_stops() owns stop_price from then on, and recomputing here
                    # every sync would drag a trailed stop backwards.
                    # Core rows never get a stop — skip ATR derivation for them.
                    pos.entry_price = fill
                    if pos.side != "core" and (pos.stop_price is None or o.status != OrderStatus.FILLED):
                        from scripts.trading_risk import atr_stop
                        sp, dist = atr_stop(fill, pos.side, pos.symbol)
                        pos.stop_price = sp
                        pos.initial_stop_distance = dist
                        pos.high_water_price = pos.high_water_price or fill
                elif pos and row.order_type == "stop" and pos.status == "open" \
                        and o.status == OrderStatus.FILLED:
                    # Stop fill (equity resting stop or crypto synthetic exit): close it.
                    _close_position(s, pos, fill, row.filled_at, status="stopped")
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
    ap.add_argument("--check-pnl",  action="store_true", help="Self-check P&L math (no network)")
    args = ap.parse_args()

    if args.check_pnl:
        # Long loss: V #5 — entry 350, exit 342, qty 14.28225 → −114.26 / −2.29%
        pnl, pct = _compute_pnl("long", 350.0, 342.0, 14.28225)
        assert pnl == -114.26 and abs(pct - (-2.2857)) < 1e-3, (pnl, pct)
        # Long win symmetric
        assert _compute_pnl("long", 100.0, 101.0, 10.0) == (10.0, 1.0)
        # Short wins when price falls
        assert _compute_pnl("short", 100.0, 99.0, 10.0) == (10.0, 1.0)
        assert _compute_pnl("short", 100.0, 101.0, 10.0) == (-10.0, -1.0)
        print("  ✅ _compute_pnl self-check passed.")
        return

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
