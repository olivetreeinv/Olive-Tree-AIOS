#!/usr/bin/env python3
"""
trading_covered_calls.py — Covered-call (wheel) trader for the Olive Tree Trading Desk.

Pure rules, NO LLM calls. One run = one idempotent manage cycle:
  1. SYNC   — reconcile Alpaca positions with DB
  2. MANAGE — profit-close / roll open short calls
  3. COVER  — sell calls against any naked 100-share lots
  4. ENTER  — buy new underlyings from CC_UNIVERSE if slots available
  5. WHEEL  — sell CSP on assigned underlyings

Usage:
  python3 scripts/trading_covered_calls.py --once           # one full cycle
  python3 scripts/trading_covered_calls.py --dry-run --once # print actions, no orders
  python3 scripts/trading_covered_calls.py --status         # positions + MTD premium

Everything stays paper (PAPER=True). No real money until Brian explicitly approves.
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.connection import Session
from db.schema import TradingCCPosition
from scripts.trading_report import send_alert
from scripts.trading_data import _get as _http_get, _alpaca_headers

_PAPER = True  # hard-coded — never flip without explicit Brian approval

# ── Config ────────────────────────────────────────────────────────────────────
CC_BOOK_USD         = 50_000
CC_MAX_UNDERLYINGS  = 3
CC_MAX_POSITION_USD = 25_000      # 100 shares must cost <= this
CC_TARGET_DELTA     = 0.25        # accept 0.20–0.30
CC_DTE_MIN          = 30
CC_DTE_MAX          = 45
CC_ROLL_DTE         = 21          # roll when DTE <= this
CC_PROFIT_CLOSE     = 0.70        # buy back when 70% of premium captured
CC_MIN_ANNUAL_YIELD = 0.10        # skip entries yielding < 10% annualized
CC_CASH_BUFFER      = 0.10        # keep >=10% of book in cash
CC_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "AMZN",
    "XOM", "JPM", "KO", "CSCO", "INTC", "VZ", "T",
    "PFE", "F", "WMT", "CVX", "MRK", "ORCL", "QCOM",
]

# ── Alpaca client ─────────────────────────────────────────────────────────────
def _client() -> TradingClient:
    key    = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        raise EnvironmentError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env")
    return TradingClient(key, secret, paper=_PAPER)


# ── Option chain helpers (Alpaca data API) ────────────────────────────────────
_DATA_BASE = "https://data.alpaca.markets/v1beta1/options"


def _parse_occ(sym: str) -> Optional[tuple[str, str, float]]:
    """
    Parse an OCC option symbol → (type, expiry_iso, strike).
    e.g. AAPL260814C00270000 → ("call", "2026-08-14", 270.0)
    The snapshots payload carries no contract metadata — the symbol IS the metadata.
    """
    try:
        strike = int(sym[-8:]) / 1000.0
        opt_type = {"C": "call", "P": "put"}[sym[-9]]
        expiry = datetime.strptime(sym[-15:-9], "%y%m%d").date().isoformat()
        return opt_type, expiry, strike
    except Exception:
        return None


def _get_option_snapshots(underlying: str, opt_type: str = "call") -> list[dict]:
    """
    Option snapshots (greeks + quotes) for an underlying, server-filtered to the
    CC DTE window. Returns list of snapshot dicts (with "symbol" key). [] on error.
    ponytail: indicative feed; fine for paper/CC sizing. Live feed = upgrade to opra.
    """
    today = date.today()
    base = (
        f"{_DATA_BASE}/snapshots/{underlying}"
        f"?feed=indicative&limit=1000&type={opt_type}"
        f"&expiration_date_gte={today + timedelta(days=CC_DTE_MIN)}"
        f"&expiration_date_lte={today + timedelta(days=CC_DTE_MAX)}"
    )
    out, token, page = [], None, 0
    while page < 5:  # ponytail: 5×1000 contracts max — plenty inside a 15-day expiry window
        url = base + (f"&page_token={token}" if token else "")
        try:
            data = _http_get(url, _alpaca_headers())
        except Exception as e:
            print(f"  ⚠️  option snapshots failed for {underlying}: {e}")
            break
        for sym, snap in (data.get("snapshots") or {}).items():
            out.append({"symbol": sym, **snap})
        token = data.get("next_page_token")
        page += 1
        if not token:
            break
    return out


def _option_quote(occ: str) -> tuple[float, float, float]:
    """(bid, ask, mid) for a single contract from the latest indicative quote. Zeros on error."""
    try:
        data = _http_get(f"{_DATA_BASE}/quotes/latest?symbols={occ}&feed=indicative",
                         _alpaca_headers())
        q = (data.get("quotes") or {}).get(occ) or {}
        bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
        mid = (bid + ask) / 2 if (bid or ask) else 0.0
        return bid, ask, mid
    except Exception:
        return 0.0, 0.0, 0.0


def _dte(expiry_str: str) -> int:
    """Days to expiration from today."""
    try:
        exp = date.fromisoformat(expiry_str)
        return (exp - date.today()).days
    except Exception:
        return -1


def _select_call(underlying: str, avg_cost: float, dry_run: bool = False
                 ) -> tuple[Optional[str], float, float, str]:
    """
    Select best call to sell against a long stock lot.
    Returns (occ_symbol, strike, premium, expiry) or (None, 0, 0, "").

    Selection logic:
      1. Filter to calls in DTE window
      2. Rank by delta closest to CC_TARGET_DELTA (0.20–0.30 band)
      3. HARD RULE: never sell below avg_cost basis
      4. Fallback: if no greeks, pick strike nearest 4% OTM in DTE window
    """
    snaps = _get_option_snapshots(underlying, opt_type="call")
    best = _pick_call(snaps, avg_cost)
    if not best:
        print(f"  ⚠️  {underlying}: no valid call ≥ basis ${avg_cost:.2f} in DTE window")
        return None, 0, 0, ""
    if best.get("_fallback"):
        print(f"  ℹ️  {underlying}: no delta in band, using 4% OTM fallback (strike ${best['strike']:.2f})")
    return best["symbol"], best["strike"], best["premium"], best["expiry"]


def _pick_call(snaps: list[dict], avg_cost: float) -> Optional[dict]:
    """
    Pure selection: filter snapshots to sellable calls (DTE window, quote present,
    strike >= basis — HARD RULE), then pick delta closest to CC_TARGET_DELTA in
    the [0.20, 0.30] band, falling back to nearest 4% OTM when greeks are missing.
    Pure so the self-check can drive it with stubbed snapshots.
    """
    calls = []
    for snap in snaps:
        parsed = _parse_occ(snap.get("symbol", ""))
        if not parsed:
            continue
        option_type, exp_str, strike = parsed
        if option_type != "call":
            continue
        dte = _dte(exp_str)
        if not (CC_DTE_MIN <= dte <= CC_DTE_MAX):
            continue
        if strike <= 0 or strike < avg_cost:
            continue  # HARD RULE: never sell a call below the lot's cost basis
        greeks = snap.get("greeks", {}) or {}
        delta  = greeks.get("delta", None)
        quote  = snap.get("latestQuote", {}) or {}
        bid = float(quote.get("bp", 0) or 0)
        ask = float(quote.get("ap", 0) or 0)
        mid = (bid + ask) / 2 if (bid or ask) else 0
        if mid <= 0:
            continue  # no live quote — can't price the sale
        calls.append({"symbol": snap["symbol"], "strike": strike, "expiry": exp_str,
                      "dte": dte, "delta": delta, "premium": mid})

    if not calls:
        return None
    band = [c for c in calls if c["delta"] is not None and 0.20 <= c["delta"] <= 0.30]
    if band:
        return min(band, key=lambda c: abs(c["delta"] - CC_TARGET_DELTA))
    # Fallback: no greeks in band → nearest 4% OTM above basis
    best = min(calls, key=lambda c: abs(c["strike"] - avg_cost * 1.04))
    return {**best, "_fallback": True}


def _should_profit_close(premium_total: float, buyback_total: float) -> bool:
    """True when >= CC_PROFIT_CLOSE of the premium has been captured."""
    return premium_total > 0 and buyback_total <= premium_total * (1 - CC_PROFIT_CLOSE)


def _annualized_yield(premium: float, strike: float, dte: int) -> float:
    if strike <= 0 or dte <= 0:
        return 0.0
    return (premium / strike) * (365 / dte)


# ── DB helpers ────────────────────────────────────────────────────────────────
def _open_cc_positions() -> list:
    s = Session()
    try:
        return s.query(TradingCCPosition).filter_by(status="open").all()
    finally:
        s.close()


def cc_held_symbols() -> set:
    """Return set of underlying tickers currently held in the CC book."""
    return {pos.underlying for pos in _open_cc_positions()}


def _close_cc_pos(s, row: TradingCCPosition, pnl: float, status: str = "closed"):
    row.status       = status
    row.closed_at    = datetime.now(timezone.utc).isoformat()
    row.realized_pnl = (row.realized_pnl or 0) + pnl


# ── Order helpers ─────────────────────────────────────────────────────────────
def _submit_limit(client, symbol: str, qty: float, side: OrderSide, limit_price: float,
                  dry_run: bool = False, label: str = "") -> Optional[str]:
    """Submit a DAY limit order at mid. Returns alpaca order ID or None."""
    tag = f"[DRY RUN] Would " if dry_run else ""
    print(f"  {tag}{'BUY' if side == OrderSide.BUY else 'SELL'} {qty}x {symbol} @ ${limit_price:.2f}  {label}")
    if dry_run:
        return "dry-run"
    try:
        order = client.submit_order(LimitOrderRequest(
            symbol=symbol, qty=qty, side=side,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit_price, 2),
        ))
        return str(order.id)
    except Exception as e:
        print(f"  ⚠️  Order failed ({symbol}): {e}")
        return None


def _submit_market(client, symbol: str, qty: float, side: OrderSide,
                   dry_run: bool = False, label: str = "") -> Optional[str]:
    tag = f"[DRY RUN] Would " if dry_run else ""
    print(f"  {tag}{'BUY' if side == OrderSide.BUY else 'SELL'} {qty}x {symbol} @ market  {label}")
    if dry_run:
        return "dry-run"
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=symbol, qty=qty, side=side, time_in_force=TimeInForce.DAY,
        ))
        return str(order.id)
    except Exception as e:
        print(f"  ⚠️  Market order failed ({symbol}): {e}")
        return None


def _wait_fill(client, alpaca_id: str, timeout: int = 30) -> Optional[float]:
    """Poll for a fill price. Returns avg fill price or None on timeout."""
    # ponytail: polls every 3s up to timeout; fine for paper. Live = websocket stream.
    if alpaca_id == "dry-run":
        return 0.0
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            order = client.get_order_by_id(alpaca_id)
            if order.filled_avg_price:
                return float(order.filled_avg_price)
        except Exception:
            pass
        time.sleep(3)
    return None


def _fill_or_cancel(client, alpaca_id: Optional[str], timeout: int = 45) -> Optional[float]:
    """
    Wait for a fill; on timeout CANCEL the order and return None.
    DB writes must only happen on a confirmed fill — an unfilled DAY limit left
    resting while the DB claims the position exists is how books go wrong.
    Returns the actual avg fill price, or None (order cancelled / failed).
    """
    if not alpaca_id or alpaca_id == "dry-run":
        return None
    fill = _wait_fill(client, alpaca_id, timeout=timeout)
    if fill is not None:
        return fill
    try:
        client.cancel_order_by_id(alpaca_id)
        print(f"  ⏳ Order {alpaca_id[:8]} unfilled after {timeout}s — cancelled; retry next cycle")
    except Exception:
        # Cancel may have raced a fill — check one last time before giving up
        try:
            o = client.get_order_by_id(alpaca_id)
            if o.filled_avg_price:
                return float(o.filled_avg_price)
        except Exception:
            pass
    return None


# ── Step 1: SYNC ──────────────────────────────────────────────────────────────
def _sync(client, dry_run: bool = False):
    """
    Reconcile Alpaca positions + orders with DB.
    Detects:
      - Assignment: 100-share lot gone + short call gone before profit-close
      - Expiry: short call disappeared at/after expiration date
    """
    print("\n  [CC 1/5] Sync...")
    try:
        alpaca_positions = {p.symbol: p for p in client.get_all_positions()}
    except Exception as e:
        print(f"  ⚠️  Sync: could not fetch Alpaca positions: {e}")
        return

    s = Session()
    try:
        open_rows = s.query(TradingCCPosition).filter_by(status="open").all()
        for row in open_rows:
            # Check if stock lot still exists in Alpaca
            shares_in_alpaca = row.underlying in alpaca_positions
            option_in_alpaca = row.option_symbol and (row.option_symbol in alpaca_positions)

            # ── Short put (CSP wheel leg) ─────────────────────────────────────
            if row.option_type == "put" and row.option_symbol and not option_in_alpaca:
                if shares_in_alpaca:
                    # Put assigned → 100 shares arrived at strike. Becomes a normal
                    # CC lot; the COVER step sells a call against it next.
                    print(f"  🔔 {row.underlying}: PUT ASSIGNED — 100 shares in at ${row.strike:.2f}")
                    row.realized_pnl = (row.realized_pnl or 0) + (row.premium_received or 0)
                    row.shares_qty = 100
                    # ponytail: basis = strike; effective basis is strike − premium, but
                    # keeping raw strike makes the never-below-basis rule conservative.
                    row.avg_cost   = row.strike
                    row.option_symbol = None
                    row.option_type   = None
                    row.strike        = 0
                    row.expiry        = None
                    row.premium_received = 0
                    send_alert("CC Desk — Put Assigned",
                               f"{row.underlying} 100sh in via CSP — will cover next cycle")
                elif row.expiry and _dte(row.expiry) <= 0:
                    print(f"  ✅ {row.underlying}: put EXPIRED worthless — premium kept")
                    _close_cc_pos(s, row, pnl=(row.premium_received or 0), status="expired")
                    send_alert("CC Desk — Expiry", f"{row.underlying} put expired, keeping premium")
                continue

            # ── Covered-call lot ──────────────────────────────────────────────
            if not shares_in_alpaca and row.shares_qty:
                # Shares are gone — either assigned or manually sold
                if row.option_symbol and not option_in_alpaca:
                    # Both gone → assignment (call exercised)
                    pnl = (row.premium_received or 0) + ((row.strike or 0) - (row.avg_cost or 0)) * 100
                    print(f"  🔔 {row.underlying}: ASSIGNED — shares called away @ ${row.strike:.2f}  P&L ${pnl:+,.0f}")
                    _close_cc_pos(s, row, pnl=pnl, status="assigned")
                    send_alert("CC Desk — Assignment",
                               f"{row.underlying} called away @ ${row.strike:.2f} — P&L ${pnl:+,.0f}")
            elif row.option_symbol and not option_in_alpaca:
                # Short call is gone but shares remain — check if expired worthless
                if row.expiry and _dte(row.expiry) <= 0:
                    kept = row.premium_received or 0
                    print(f"  ✅ {row.underlying}: call EXPIRED worthless — kept ${kept:,.0f} premium")
                    # Bank the premium, clear option fields, leave shares open for next cover
                    row.realized_pnl  = (row.realized_pnl or 0) + kept
                    row.option_symbol = None
                    row.option_type   = None
                    row.strike        = 0
                    row.expiry        = None
                    row.premium_received = 0
                    send_alert("CC Desk — Expiry", f"{row.underlying} call expired, kept ${kept:,.0f}")
        s.commit()
    finally:
        s.close()


# ── Step 2: MANAGE ────────────────────────────────────────────────────────────
def _manage(client, dry_run: bool = False):
    """Profit-close (70% captured) or roll (DTE <= 21, only if credit)."""
    print("\n  [CC 2/5] Manage open calls...")
    s = Session()
    try:
        open_rows = s.query(TradingCCPosition).filter_by(status="open").all()
        for row in open_rows:
            if not row.option_symbol or row.option_type != "call":
                continue
            bid, ask, mid = _option_quote(row.option_symbol)
            if mid <= 0:
                continue  # no live quote — nothing safe to decide on
            premium_total = row.premium_received or 0   # total $ collected for this leg
            buyback_total = mid * 100                   # est. cost to close (limit lands at ask)
            dte           = _dte(row.expiry or "")

            # Profit-close: buyback cost <= 30% of premium received
            if _should_profit_close(premium_total, buyback_total):
                captured = (premium_total - buyback_total) / premium_total
                print(f"  💰 {row.underlying}: profit-close {row.option_symbol} "
                      f"(buyback ~${buyback_total:,.0f}, captured {captured:.0%})")
                oid = _submit_limit(client, row.option_symbol, 1, OrderSide.BUY, ask or mid,
                                    dry_run=dry_run, label="profit-close")
                if oid and not dry_run:
                    buy_fill = _fill_or_cancel(client, oid)
                    if buy_fill is None:
                        continue  # nothing closed, DB untouched — retry next cycle
                    row.realized_pnl = (row.realized_pnl or 0) + (premium_total - buy_fill * 100)
                    row.option_symbol = None
                    row.option_type   = None
                    row.strike        = 0
                    row.expiry        = None
                    row.premium_received = 0
                    s.commit()  # buyback booked before the next leg — each leg recoverable
                    # Sell a fresh call right away; on non-fill the lot stays naked and
                    # COVER re-sells next cycle.
                    new_sym, new_strike, new_prem, new_exp = _select_call(row.underlying, row.avg_cost, dry_run)
                    if new_sym:
                        sell_oid  = _submit_limit(client, new_sym, 1, OrderSide.SELL,
                                                  new_prem, dry_run=dry_run, label="new call after profit-close")
                        sell_fill = _fill_or_cancel(client, sell_oid)
                        if sell_fill:
                            row.option_symbol    = new_sym
                            row.option_type      = "call"
                            row.strike           = new_strike
                            row.expiry           = new_exp
                            row.premium_received = sell_fill * 100
                            send_alert("CC Desk — Rolled after profit-close",
                                       f"{row.underlying}: closed for ${buy_fill*100:,.0f}, "
                                       f"sold {new_exp} ${new_strike:g} call for ${sell_fill*100:,.0f}")
                    s.commit()
                continue

            # Roll: DTE <= CC_ROLL_DTE, only if the roll nets a credit
            if dte <= CC_ROLL_DTE:
                new_sym, new_strike, new_prem, new_exp = _select_call(row.underlying, row.avg_cost, dry_run)
                if not new_sym:
                    print(f"  ⏭  {row.underlying}: DTE={dte} but no roll candidate ≥ basis — letting ride")
                    continue
                roll_credit = (new_prem - mid) * 100  # $ credit if positive
                if roll_credit < 0:
                    print(f"  ⏭  {row.underlying}: roll would be a debit (${roll_credit:,.0f}) — letting ride to expiry/assignment")
                    continue
                print(f"  🔄 {row.underlying}: rolling {row.option_symbol} → {new_sym} for ~${roll_credit:,.0f} credit")
                buy_oid = _submit_limit(client, row.option_symbol, 1, OrderSide.BUY, ask or mid,
                                        dry_run=dry_run, label="roll buy-back")
                if dry_run:
                    _submit_limit(client, new_sym, 1, OrderSide.SELL,
                                  new_prem, dry_run=True, label="roll new call")
                    continue
                buy_fill = _fill_or_cancel(client, buy_oid)
                if buy_fill is None:
                    continue  # buyback didn't fill — still short the old call, retry next cycle
                row.realized_pnl  = (row.realized_pnl or 0) + (premium_total - buy_fill * 100)
                row.option_symbol = None
                row.option_type   = None
                row.strike        = 0
                row.expiry        = None
                row.premium_received = 0
                s.commit()
                sell_oid  = _submit_limit(client, new_sym, 1, OrderSide.SELL,
                                          new_prem, dry_run=False, label="roll new call")
                sell_fill = _fill_or_cancel(client, sell_oid)
                if sell_fill:
                    row.option_symbol    = new_sym
                    row.option_type      = "call"
                    row.strike           = new_strike
                    row.expiry           = new_exp
                    row.premium_received = sell_fill * 100
                    send_alert("CC Desk — Roll",
                               f"{row.underlying}: rolled to {new_exp} ${new_strike:g} call, "
                               f"${sell_fill*100 - buy_fill*100:+,.0f} net vs buyback")
                # else: naked — COVER re-sells next cycle
                s.commit()
        s.commit()
    finally:
        s.close()


# ── Step 3: COVER ─────────────────────────────────────────────────────────────
def _cover(client, dry_run: bool = False):
    """Sell a call against any naked 100-share lot."""
    print("\n  [CC 3/5] Cover naked lots...")
    s = Session()
    try:
        open_rows = s.query(TradingCCPosition).filter_by(status="open").all()
        for row in open_rows:
            if row.option_symbol or not row.shares_qty:
                continue  # already covered, or a CSP row (no shares to cover)
            sym, strike, premium, expiry = _select_call(row.underlying, row.avg_cost, dry_run)
            if not sym:
                print(f"  ⚠️  {row.underlying}: no acceptable call ≥ basis ${row.avg_cost:.2f} "
                      f"in the delta band/DTE window — holding uncovered this cycle")
                continue
            dte = _dte(expiry)
            yld = _annualized_yield(premium, strike, dte)
            print(f"  📤 Cover {row.underlying}: sell {sym} exp {expiry} DTE={dte} "
                  f"strike=${strike:.2f} premium=${premium*100:,.0f} yield={yld:.1%}/yr")
            oid = _submit_limit(client, sym, 1, OrderSide.SELL, premium,
                                dry_run=dry_run, label="cover")
            if oid and not dry_run:
                fill = _fill_or_cancel(client, oid)
                if fill is None:
                    print(f"  ⏳ {row.underlying}: call sell unfilled — staying naked, COVER retries next cycle")
                    continue
                row.option_symbol    = sym
                row.option_type      = "call"
                row.strike           = strike
                row.expiry           = expiry
                row.premium_received = fill * 100
                s.commit()
                yld = _annualized_yield(fill, strike, dte)
                send_alert("CC Desk — Covered",
                           f"🧾 CC: sold {row.underlying} {expiry} ${strike:g} call "
                           f"for ${fill*100:,.0f} premium ({yld:.1%} annualized)")
        s.commit()
    finally:
        s.close()


# ── Step 4: ENTER ─────────────────────────────────────────────────────────────
def _enter(client, dry_run: bool = False):
    """Buy new underlyings from CC_UNIVERSE if slots + cash allow."""
    print("\n  [CC 4/5] Enter new positions...")
    s = Session()
    try:
        open_rows = s.query(TradingCCPosition).filter_by(status="open").all()
        held      = {r.underlying for r in open_rows}
        slots     = CC_MAX_UNDERLYINGS - len(held)
        if slots <= 0:
            print(f"  ⏭  At max {CC_MAX_UNDERLYINGS} underlyings — no new entries")
            return

        # Estimate book cash: CC_BOOK_USD minus cost of open lots + cash reserved for CSPs
        # ponytail: cost-basis proxy, not marked-to-market; Alpaca account cash is shared
        # with the momentum book so it can't be read directly.
        deployed = sum((r.avg_cost or 0) * (r.shares_qty or 0) for r in open_rows) + \
                   sum((r.strike or 0) * 100 for r in open_rows
                       if r.option_type == "put" and not r.shares_qty)
        avail    = CC_BOOK_USD - deployed
        min_cash = CC_BOOK_USD * CC_CASH_BUFFER
        if avail < min_cash + CC_MAX_POSITION_USD * 0.5:
            print(f"  ⏭  Cash buffer too low (${avail:,.0f} available) — skipping entry")
            return

        # Symbols with ANY live Alpaca position or open order are off-limits: Alpaca
        # nets same-symbol lots into one position (breaks assignment detection), and
        # a momentum order submitted moments ago must not collide with a CC entry.
        # Fail-closed: can't see the account → don't enter.
        try:
            live_syms = {p.symbol for p in client.get_all_positions()}
            for o in client.get_orders():  # default filter = open orders
                live_syms.add(o.symbol)
                if _parse_occ(o.symbol):
                    live_syms.add(o.symbol[:-15])  # option order → block its underlying too
        except Exception as e:
            print(f"  ⚠️  Could not fetch live positions/orders ({e}) — skipping entries this cycle")
            return
        try:
            from scripts.trading_execution import get_open_positions
            live_syms |= {p["symbol"] for p in get_open_positions()}  # momentum book (local DB)
        except Exception:
            pass

        # Cap book math by real account buying power (paper account is shared).
        try:
            from scripts.trading_data import get_account
            avail = min(avail, get_account().get("buying_power", 0))
        except Exception as e:
            print(f"  ⚠️  Could not fetch account buying power ({e}) — skipping entries this cycle")
            return

        # Screen universe: price × 100 <= CC_MAX_POSITION_USD, chain has DTE-window contracts
        candidates = []
        from scripts.trading_data import get_quote
        for ticker in CC_UNIVERSE:
            if ticker in held or ticker in live_syms:
                continue
            try:
                q = get_quote(ticker)
                price = q.get("ask") or q.get("last") or 0
                if price <= 0 or price * 100 > CC_MAX_POSITION_USD:
                    continue
                sym, strike, premium, expiry = _select_call(ticker, price)
                if not sym or premium <= 0:
                    continue
                dte = _dte(expiry)
                yld = _annualized_yield(premium, strike, dte)
                if yld < CC_MIN_ANNUAL_YIELD:
                    continue
                candidates.append({"ticker": ticker, "price": price, "sym": sym,
                                   "strike": strike, "premium": premium,
                                   "expiry": expiry, "dte": dte, "yield": yld})
            except Exception as e:
                print(f"  ⚠️  Screen {ticker}: {e}")

        candidates.sort(key=lambda c: c["yield"], reverse=True)
        entered = 0
        for c in candidates:
            if entered >= slots:
                break
            cost = c["price"] * 100
            if cost > avail - min_cash:
                print(f"  ⏭  {c['ticker']} ${cost:,.0f} would breach cash buffer — skip")
                continue
            print(f"  🛒 Enter {c['ticker']}: buy 100 shares @ ${c['price']:.2f} "
                  f"then sell {c['sym']} exp {c['expiry']} yield={c['yield']:.1%}/yr")
            oid = _submit_market(client, c["ticker"], 100, OrderSide.BUY,
                                 dry_run=dry_run, label="buy 100 shares")
            if not oid:
                continue
            if dry_run:
                _submit_limit(client, c["sym"], 1, OrderSide.SELL, c["premium"],
                              dry_run=True, label="sell call after entry")
                avail -= cost
                entered += 1
                continue

            fill = _fill_or_cancel(client, oid, timeout=30)
            if fill is None:
                # No confirmed fill → record NOTHING. If a fill raced the cancel, the
                # live-position guard above blocks a re-buy next cycle.
                print(f"  ⚠️  {c['ticker']} buy not confirmed — recording nothing, reconcile next cycle")
                continue

            # Write the lot row on the STOCK fill, before the option leg — a crash
            # between legs must not orphan 100 shares (each leg individually recoverable).
            row = TradingCCPosition(
                underlying=c["ticker"], shares_qty=100, avg_cost=fill,
                option_symbol=None, option_type=None, strike=0, expiry=None,
                premium_received=0,
                status="open", opened_at=datetime.now(timezone.utc).isoformat(),
            )
            s.add(row)
            s.commit()

            # Sell the call; on non-fill keep the shares — next COVER step fixes it
            call_oid  = _submit_limit(client, c["sym"], 1, OrderSide.SELL, c["premium"],
                                      dry_run=False, label="sell call after entry")
            call_fill = _fill_or_cancel(client, call_oid)
            if call_fill:
                row.option_symbol    = c["sym"]
                row.option_type      = "call"
                row.strike           = c["strike"]
                row.expiry           = c["expiry"]
                row.premium_received = call_fill * 100
                s.commit()
                send_alert("CC Desk — Entry",
                           f"🧾 CC: bought 100 {c['ticker']} @ ${fill:.2f}, sold {c['expiry']} "
                           f"${c['strike']:g} call for ${call_fill*100:,.0f} ({c['yield']:.1%} annualized)")
            else:
                print(f"  ⏳ {c['ticker']}: call sell unfilled — lot recorded naked, COVER retries next cycle")
                send_alert("CC Desk — Entry (naked)",
                           f"🧾 CC: bought 100 {c['ticker']} @ ${fill:.2f} — call sell pending next cycle")
            avail -= cost
            entered += 1
        s.commit()
        if entered == 0:
            print("  No new entries passed all filters.")
    finally:
        s.close()


# ── Step 5: WHEEL on assignment ───────────────────────────────────────────────
def _wheel(client, dry_run: bool = False):
    """Sell a cash-secured put on recently assigned underlyings to re-enter."""
    print("\n  [CC 5/5] Wheel (sell CSP on assigned)...")
    s = Session()
    try:
        assigned = s.query(TradingCCPosition).filter_by(status="assigned").all()
        from scripts.trading_data import get_quote
        for row in assigned:
            q = get_quote(row.underlying)
            price = q.get("last") or q.get("ask") or 0
            if not price:
                continue
            # Find ~0.25 delta put in DTE window
            snaps = _get_option_snapshots(row.underlying, opt_type="put")
            puts = []
            for snap in snaps:
                parsed = _parse_occ(snap.get("symbol", ""))
                if not parsed:
                    continue
                opt_type, exp_str, strike = parsed
                if opt_type != "put":
                    continue
                dte = _dte(exp_str)
                if not (CC_DTE_MIN <= dte <= CC_DTE_MAX):
                    continue
                if strike <= 0 or strike > price or strike * 100 > CC_BOOK_USD * (1 - CC_CASH_BUFFER):
                    continue  # OTM only, and the CSP must fit in available book cash
                greeks = snap.get("greeks", {}) or {}
                delta  = abs(greeks.get("delta", 0) or 0)  # puts have negative delta
                quote  = snap.get("latestQuote", {}) or {}
                mid    = ((float(quote.get("bp", 0) or 0)) + (float(quote.get("ap", 0) or 0))) / 2
                if mid <= 0:
                    continue
                puts.append({"symbol": snap.get("symbol"), "strike": strike,
                             "expiry": exp_str, "dte": dte, "delta": delta, "premium": mid})

            if not puts:
                print(f"  ⚠️  {row.underlying}: no put contracts in DTE window for CSP")
                continue

            band = [p for p in puts if 0.20 <= p["delta"] <= 0.30]
            best = (min(band, key=lambda p: abs(p["delta"] - 0.25)) if band
                    else min(puts, key=lambda p: abs(p["strike"] - price * 0.96)))

            print(f"  🎡 Wheel {row.underlying}: sell put {best['symbol']} "
                  f"exp {best['expiry']} strike=${best['strike']:.2f} prem=${best['premium']*100:,.0f}")
            oid = _submit_limit(client, best["symbol"], 1, OrderSide.SELL, best["premium"],
                                dry_run=dry_run, label="CSP wheel")
            if oid and not dry_run:
                fill = _fill_or_cancel(client, oid)
                if fill is None:
                    print(f"  ⏳ {row.underlying}: CSP sell unfilled — wheel retries next cycle")
                    continue
                # Re-open a CC row as a put position (will become shares if assigned)
                new_row = TradingCCPosition(
                    underlying=row.underlying, shares_qty=0, avg_cost=0,
                    option_symbol=best["symbol"], option_type="put",
                    strike=best["strike"], expiry=best["expiry"],
                    premium_received=fill * 100,
                    status="open", opened_at=datetime.now(timezone.utc).isoformat(),
                )
                s.add(new_row)
                row.status = "wheeled"  # mark original assignment as handled
                s.commit()
                send_alert("CC Desk — Wheel",
                           f"🎡 CC: sold {row.underlying} {best['expiry']} ${best['strike']:g} CSP "
                           f"for ${fill*100:,.0f} to re-enter")
        s.commit()
    finally:
        s.close()


# ── Public API ────────────────────────────────────────────────────────────────
def run_cc_cycle(dry_run: bool = False):
    """One full idempotent CC manage cycle. Called by orchestrator every 4h."""
    print(f"\n  {'─'*60}")
    print(f"  Covered-Call Cycle {'[DRY RUN] ' if dry_run else ''}— {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  {'─'*60}")
    client = _client()
    _sync(client, dry_run)

    from scripts.trading_data import is_market_open
    if not is_market_open():
        # Options only trade in the regular session — quotes are stale and DAY
        # limit orders would queue at bad prices. Sync above still reconciled.
        print("\n  Market closed — sync done; skipping manage/cover/enter/wheel.")
        return

    _manage(client, dry_run)
    _cover(client, dry_run)
    _enter(client, dry_run)
    _wheel(client, dry_run)
    print(f"\n  CC cycle complete.")


def cc_next_actions() -> list[str]:
    """
    Deterministic next-action lines for each open CC position.
    Used in --status output and the daily scorecard email.
    """
    rows = _open_cc_positions()
    lines = []
    today = date.today()
    for row in rows:
        sym = row.underlying
        if row.option_type == "put" and not row.shares_qty:
            # Wheel / CSP leg
            exp_str = row.expiry or "?"
            lines.append(
                f"{sym} ${row.strike:.2f} put exp {exp_str} — awaiting expiry/assignment"
            )
        elif row.option_symbol and row.option_type == "call":
            # Covered call: show profit-close trigger and roll window
            prem = row.premium_received or 0
            buyback_trigger = round(prem * (1 - CC_PROFIT_CLOSE), 2)  # buy back ≤ this → 70% captured
            dte = _dte(row.expiry or "")
            roll_date = ""
            if row.expiry:
                try:
                    exp = date.fromisoformat(row.expiry)
                    roll_open = exp - timedelta(days=CC_ROLL_DTE)
                    if roll_open >= today:
                        roll_date = f"; roll window opens {roll_open.isoformat()}"
                    else:
                        roll_date = f"; roll window OPEN now (DTE={dte})"
                except Exception:
                    pass
            lines.append(
                f"{sym} ${row.strike:.2f} call exp {row.expiry} (DTE {dte}) — "
                f"profit-close triggers if buyback ≤ ${buyback_trigger:.2f}/contract"
                f"{roll_date}"
            )
        else:
            # Naked lot — waiting for a call to be sold
            lines.append(f"{sym} — will retry selling a call next cycle (naked lot)")
    return lines


def _print_status():
    """Print CC book positions + MTD premium vs $500 target."""
    s = Session()
    try:
        today     = date.today().isoformat()
        mtd_start = today[:7] + "-01"
        open_rows = s.query(TradingCCPosition).filter_by(status="open").all()
        closed    = s.query(TradingCCPosition).filter(
            TradingCCPosition.status.in_(("closed", "assigned", "expired", "wheeled")),
            TradingCCPosition.closed_at >= mtd_start,
        ).all()
    finally:
        s.close()

    print(f"\n  ── CC Book Status ──────────────────────────────────")
    if not open_rows:
        print("  No open CC positions.")
    for row in open_rows:
        if row.option_type == "put" and not row.shares_qty:
            lot = "CSP   "
        else:
            lot = f"{row.shares_qty or 0}sh @ ${row.avg_cost or 0:.2f}"
        opt_info = (f"{row.option_symbol} exp {row.expiry} strike=${row.strike:.2f}"
                    if row.option_symbol else "UNCOVERED")
        print(f"  {row.underlying:6s}  {lot}  |  {opt_info}  "
              f"prem_rcvd=${row.premium_received or 0:,.0f}")

    premium_mtd  = sum((r.premium_received or 0) for r in open_rows) + \
                   sum((r.premium_received or 0) for r in closed)
    realized_pnl = sum((r.realized_pnl or 0) for r in closed)
    target = 500.0
    pct = premium_mtd / target if target else 0
    print(f"\n  Premium MTD: ${premium_mtd:.2f} / ${target:.0f} target ({pct:.0%})")
    print(f"  Realized P&L MTD: ${realized_pnl:+.2f}")
    from scripts.trading_data import get_quote
    book_value = 0.0
    for row in open_rows:
        try:
            q = get_quote(row.underlying)
            price = q.get("last") or q.get("ask") or 0
            book_value += price * (row.shares_qty or 0)
        except Exception:
            pass
    print(f"  Book market value: ~${book_value:,.0f}")

    actions = cc_next_actions()
    if actions:
        print(f"\n  ── Planned Moves ───────────────────────────────────")
        for a in actions:
            print(f"  • {a}")


# ── Self-check: CC decision logic ─────────────────────────────────────────────
def _self_check():
    """Stub-driven test of profit-close / never-below-basis / delta-band / OCC parse."""
    print("── CC self-check ──────────────────────────────────────────────────\n")

    # 1. Profit-close: exact boundary at 70% captured
    assert _should_profit_close(200.0, 60.0),      "must trigger at exactly 70% captured"
    assert _should_profit_close(200.0, 45.0),      "must trigger past 70% captured"
    assert not _should_profit_close(200.0, 70.0),  "must NOT trigger at 65% captured"
    assert not _should_profit_close(0.0, 0.0),     "no premium → never trigger"
    print("  ✅ profit-close rule: triggers at 70% captured, not before")

    # 2. OCC symbol parsing (snapshots carry no metadata — the symbol is the metadata)
    assert _parse_occ("AAPL260814C00270000") == ("call", "2026-08-14", 270.0)
    assert _parse_occ("F260918P00011500")    == ("put",  "2026-09-18", 11.5)
    assert _parse_occ("garbage") is None
    print("  ✅ OCC parse: type/expiry/strike from symbol")

    # 3. _pick_call on stubbed snapshots: never-below-basis + delta band
    exp = (date.today() + timedelta(days=35)).strftime("%y%m%d")
    def stub(strike: float, delta, bid=1.0, ask=1.2):
        s = {"symbol": f"AAPL{exp}C{int(strike*1000):08d}",
             "latestQuote": {"bp": bid, "ap": ask}}
        if delta is not None:
            s["greeks"] = {"delta": delta}
        return s

    # Below-basis strike has the perfect delta — must still be rejected
    best = _pick_call([stub(148, 0.25), stub(160, 0.28), stub(165, 0.35)], avg_cost=150.0)
    assert best and best["strike"] == 160, f"expected $160 (only in-band strike ≥ basis), got {best}"
    assert best["strike"] >= 150.0, "HARD RULE broken: strike below basis selected"
    print(f"  ✅ never-below-basis: $148 @ Δ0.25 rejected, picked ${best['strike']:g}")

    # Delta closest to 0.25 wins inside the band
    best = _pick_call([stub(155, 0.24), stub(160, 0.30), stub(165, 0.20)], avg_cost=150.0)
    assert best and best["strike"] == 155, f"expected Δ0.24 strike 155, got {best}"
    # Out-of-band deltas (0.45, 0.10) → fall back to 4% OTM
    best = _pick_call([stub(150, 0.45), stub(156, 0.10), stub(170, None)], avg_cost=150.0)
    assert best and best["strike"] == 156 and best.get("_fallback"), f"4% OTM fallback broken: {best}"
    # Nothing above basis → hold uncovered (None)
    assert _pick_call([stub(140, 0.25), stub(145, 0.25)], avg_cost=150.0) is None
    print("  ✅ delta band: 0.24 beats 0.30/0.20; no-band → 4% OTM; none ≥ basis → None")

    # 4. Annualized yield gate
    yld = _annualized_yield(1.50, 150.00, 35)       # 10.4% → passes
    assert yld >= CC_MIN_ANNUAL_YIELD, f"10%+ yield should pass gate: {yld:.2%}"
    low_yld = _annualized_yield(0.50, 150.00, 35)   # 3.5% → fails
    assert low_yld < CC_MIN_ANNUAL_YIELD, f"3.5% should fail gate: {low_yld:.2%}"
    print(f"  ✅ yield gate: {yld:.1%} passes, {low_yld:.1%} fails")

    print("\n  All CC self-checks passed. ✅")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Covered-call trader — Olive Tree Trading Desk")
    ap.add_argument("--once",     action="store_true", help="Run one full CC manage cycle")
    ap.add_argument("--dry-run",  action="store_true", help="Print actions; no orders submitted")
    ap.add_argument("--status",   action="store_true", help="Show CC book + MTD premium")
    ap.add_argument("--test",     action="store_true", help="Run self-check (no network)")
    args = ap.parse_args()

    if args.test:
        _self_check()
        return
    if args.status:
        _print_status()
        return
    if args.once:
        run_cc_cycle(dry_run=args.dry_run)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
