#!/usr/bin/env python3
"""
trading_covered_calls.py — Premium Desk v2: CSP-first wheel trader for the
Olive Tree Trading Desk.

RETIRED as a strategy (2026-07-15) — the orchestrator only runs Suna v3
(trading_suna.py) now. This module stays because trading_suna.py imports its
order/fill/position primitives (_two_stage_sell, _submit_limit, TradingCCPosition,
etc). Running this file's --once/--loop directly still works but nothing
schedules it anymore.

Pure rules, NO LLM calls (except the opt-in AI event-screen pass in the
screener). One run = one idempotent manage cycle:
  1. SYNC   — reconcile Alpaca positions with DB
  2. MANAGE — profit-close / 21-DTE roll (ITM up-and-out, OTM to next monthly)
  3. COVER  — sell calls against any naked 100-share lots
  4. ENTER  — CSP-first: sell cash-secured puts on screener-ranked candidates
  5. WHEEL  — sell CSP on assigned underlyings (re-enter after assignment)

Entries are CSP-first (scripts/trading_screener.py ranks candidates by IV
richness after price/spread/earnings filters) — new capital deploys via
0.25Δ cash-secured puts, not by buying shares outright. Share-buy + cover
still runs for existing lots and immediately after assignment (never below
cost basis).

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
from scripts.trading_screener import (
    screen_candidates, SECTOR as SCREENER_SECTOR, CANDIDATE_UNIVERSE,
    earnings_max_expiry, get_next_earnings, SCR_DTE_FLOOR,
)

_PAPER = True  # hard-coded — never flip without explicit Brian approval

# ── Config: book + sizing ─────────────────────────────────────────────────────
CC_BOOK_USD         = 50_000
CC_MAX_UNDERLYINGS  = 12          # raised from 8 (2026-07-15): 8x$10k cap already covered the
                                   # full $47.5k deployable, real blocker was legacy 1-lot v2
                                   # positions occupying slots; more slots let full-sized v3
                                   # entries open alongside them instead of waiting them out
CC_MAX_POSITION_USD = 10_000      # <=20% of book per underlying (100sh lot <= $100/share)
CC_MAX_PER_SECTOR   = 2           # max underlyings per SECTOR bucket (see trading_screener.SECTOR)
CC_CASH_BUFFER      = 0.05        # keep >=5% of book in cash

# ── Config: option selection ──────────────────────────────────────────────────
CC_TARGET_DELTA     = 0.30        # covered calls target 0.30Δ (accept 0.25–0.35)
CC_DELTA_BAND       = (0.25, 0.35)
CSP_TARGET_DELTA    = 0.25        # cash-secured puts target 0.25Δ (accept 0.20–0.30)
CSP_DELTA_BAND      = (0.20, 0.30)

# ── Config: DTE window + management ───────────────────────────────────────────
CC_DTE_MIN          = 30           # monthly-ish options: 30–45 DTE at entry
CC_DTE_MAX          = 45
CC_MANAGE_DTE       = 21           # manage at 21 DTE: ITM roll out(+up), or OTM roll if <60% captured
CC_PROFIT_CLOSE     = 0.60         # buy back when 60% of premium captured
CC_MIN_ANNUAL_YIELD = 0.10         # skip entries yielding < 10% annualized
CC_LADDER_SPREAD_DAYS = 7          # spread new-position expiries across ~weekly buckets

# ── Config: universe (legacy fallback if the screener is unreachable) ─────────
CC_UNIVERSE = CANDIDATE_UNIVERSE

# ── Config: reporting ──────────────────────────────────────────────────────────
CC_WEEKLY_TARGET_USD  = 1_000.0                          # primary goal: $1k/week premium (Suna weekly cadence)
CC_MONTHLY_TARGET_USD = CC_WEEKLY_TARGET_USD * 52 / 12   # ≈ $4,333/mo, ~104% annualized on the $50k book

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


def _get_option_snapshots(underlying: str, opt_type: str = "call",
                          dte_min: int = CC_DTE_MIN) -> list[dict]:
    """
    Option snapshots (greeks + quotes) for an underlying, server-filtered to the
    CC DTE window. Put callers pass dte_min=SCR_DTE_FLOOR so _pick_put can duck
    under an earnings date. Returns list of snapshot dicts (with "symbol" key).
    [] on error.
    """
    today = date.today()
    base = (
        f"{_DATA_BASE}/snapshots/{underlying}"
        f"?feed=opra&limit=1000&type={opt_type}"
        f"&expiration_date_gte={today + timedelta(days=dte_min)}"
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
    """(bid, ask, mid) for a single contract from the latest OPRA quote. Zeros on error."""
    try:
        data = _http_get(f"{_DATA_BASE}/quotes/latest?symbols={occ}&feed=opra",
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
      1. Filter to calls in the 30–45 DTE window
      2. Rank by delta closest to CC_TARGET_DELTA (CC_DELTA_BAND: 0.25–0.35)
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
    lo, hi = CC_DELTA_BAND
    band = [c for c in calls if c["delta"] is not None and lo <= c["delta"] <= hi]
    if band:
        return min(band, key=lambda c: abs(c["delta"] - CC_TARGET_DELTA))
    # Fallback: no greeks in band → nearest 4% OTM above basis
    best = min(calls, key=lambda c: abs(c["strike"] - avg_cost * 1.04))
    return {**best, "_fallback": True}


def _ladder_pick(band: list[dict], used_expiries: list[str], target_delta: float,
                 spread_days: int = CC_LADDER_SPREAD_DAYS) -> dict:
    """
    Expiry laddering: among a delta-band, prefer a contract whose expiry is NOT
    within spread_days of any expiry already used this cycle, so multiple entries
    don't stack onto one date. Falls back to pure delta-closeness if every
    candidate collides with an already-used week (small band, or single expiry).
    """
    def collides(c):
        return any(abs((date.fromisoformat(c["expiry"]) - date.fromisoformat(u)).days) < spread_days
                   for u in used_expiries)
    pool = [c for c in band if not collides(c)] or band
    return min(pool, key=lambda c: abs(c["delta"] - target_delta))


def _pick_put(snaps: list[dict], max_strike: float,
             used_expiries: Optional[list[str]] = None,
             max_expiry: Optional[date] = None) -> Optional[dict]:
    """
    Pure selection: filter snapshots to sellable puts (DTE window, quote present,
    strike <= max_strike so the CSP fits available cash), pick delta closest to
    CSP_TARGET_DELTA in CSP_DELTA_BAND (laddered against used_expiries when given),
    falling back to nearest 4% OTM below spot. Mirrors _pick_call's structure —
    used for CSP entries and the wheel re-entry leg.

    max_expiry = pre-earnings cutoff (earnings - 2d). When it cuts below the
    normal 30-DTE floor, the floor relaxes to SCR_DTE_FLOOR (14) so we sell the
    expiry BEFORE earnings instead of skipping the name; if nothing >= 14 DTE
    clears the cutoff, returns None (caller skips).
    """
    dte_floor = CC_DTE_MIN
    if max_expiry and (max_expiry - date.today()).days < CC_DTE_MIN:
        dte_floor = SCR_DTE_FLOOR
    puts = []
    for snap in snaps:
        parsed = _parse_occ(snap.get("symbol", ""))
        if not parsed:
            continue
        option_type, exp_str, strike = parsed
        if option_type != "put":
            continue
        dte = _dte(exp_str)
        if not (dte_floor <= dte <= CC_DTE_MAX):
            continue
        if max_expiry and date.fromisoformat(exp_str) > max_expiry:
            continue  # expiry would cross earnings
        if strike <= 0 or strike > max_strike:
            continue
        greeks = snap.get("greeks", {}) or {}
        delta  = greeks.get("delta", None)
        delta  = abs(delta) if delta is not None else None  # puts carry negative delta
        quote  = snap.get("latestQuote", {}) or {}
        bid = float(quote.get("bp", 0) or 0)
        ask = float(quote.get("ap", 0) or 0)
        mid = (bid + ask) / 2 if (bid or ask) else 0
        if mid <= 0:
            continue
        puts.append({"symbol": snap["symbol"], "strike": strike, "expiry": exp_str,
                     "dte": dte, "delta": delta, "premium": mid})

    if not puts:
        return None
    lo, hi = CSP_DELTA_BAND
    band = [p for p in puts if p["delta"] is not None and lo <= p["delta"] <= hi]
    if band:
        if used_expiries:
            return _ladder_pick(band, used_expiries, CSP_TARGET_DELTA)
        return min(band, key=lambda p: abs(p["delta"] - CSP_TARGET_DELTA))
    best = min(puts, key=lambda p: abs(p["strike"] - max_strike * 0.96))
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
        print(f"  ⏳ Order {alpaca_id[:8]} unfilled after {timeout}s — cancelled")
    except Exception:
        # Cancel may have raced a fill — check one last time before giving up
        try:
            o = client.get_order_by_id(alpaca_id)
            if o.filled_avg_price:
                return float(o.filled_avg_price)
        except Exception:
            pass
    return None


def _premium_floor(strike: float, dte: int) -> float:
    """
    Minimum acceptable sell premium: annualized yield must stay >= CC_MIN_ANNUAL_YIELD.
    premium_floor = strike * CC_MIN_ANNUAL_YIELD * (DTE / 365)
    ponytail: per-share floor; the yield gate in _annualized_yield uses the same formula inverted.
    """
    if strike <= 0 or dte <= 0:
        return 0.0
    return strike * CC_MIN_ANNUAL_YIELD * (dte / 365)


def _two_stage_sell(client, symbol: str, bid: float, ask: float, mid: float,
                    strike: float, dte: int, qty: int = 1, dry_run: bool = False,
                    label: str = "") -> Optional[float]:
    """
    Two-stage sell for option contracts:
      Stage 1: limit at mid, wait 45s.
      Stage 2: if unfilled, resubmit at BID but never below premium_floor.
               If bid < floor, skip — don't sell garbage premium.
               Wait another 45s; if still unfilled, cancel and return None.
    Returns fill price or None (leave naked for next cycle).
    """
    floor = _premium_floor(strike, dte)

    # Stage 1: mid
    oid = _submit_limit(client, symbol, qty, OrderSide.SELL, mid, dry_run=dry_run,
                        label=f"{label} [stage1 mid=${mid:.2f}]")
    if dry_run:
        print(f"    [DRY RUN] Stage 2 would try bid=${bid:.2f} (floor=${floor:.2f})")
        return None  # dry-run: don't simulate a fill

    fill = _fill_or_cancel(client, oid, timeout=45)
    if fill is not None:
        return fill

    # Stage 2: just under the bid so it's marketable even if our snapshot quote
    # is a tick stale (orders AT the bid sat unfilled — sim fills off the live book),
    # but never below the yield floor.
    stage2 = max(floor, round(bid * 0.97, 2))
    if stage2 > bid:  # floor above bid → selling would breach the yield gate
        print(f"  ⏭  {symbol}: bid ${bid:.2f} < floor ${floor:.2f} (yield gate) — "
              f"leaving naked for next cycle")
        return None
    oid2 = _submit_limit(client, symbol, qty, OrderSide.SELL, stage2, dry_run=False,
                         label=f"{label} [stage2 ${stage2:.2f} (bid−3%)]")
    fill2 = _fill_or_cancel(client, oid2, timeout=45)
    if fill2 is None:
        print(f"  ⏳ {symbol}: unfilled after both stages — naked, retries next cycle")
    return fill2


def _two_stage_buy(client, symbol: str, bid: float, ask: float, mid: float,
                   qty: int = 1, dry_run: bool = False, label: str = "") -> Optional[float]:
    """
    Two-stage buy-to-close for option contracts:
      Stage 1: limit at mid, wait 45s.
      Stage 2: if unfilled, resubmit at ASK (more aggressive to close winners).
    Returns fill price or None.
    """
    oid = _submit_limit(client, symbol, qty, OrderSide.BUY, mid, dry_run=dry_run,
                        label=f"{label} [stage1 mid=${mid:.2f}]")
    if dry_run:
        print(f"    [DRY RUN] Stage 2 would try ask=${ask:.2f}")
        return None

    fill = _fill_or_cancel(client, oid, timeout=45)
    if fill is not None:
        return fill

    # Mirror of the sell path: a touch over the ask so a stale snapshot can't strand us.
    stage2 = round(ask * 1.03, 2)
    oid2 = _submit_limit(client, symbol, qty, OrderSide.BUY, stage2, dry_run=False,
                         label=f"{label} [stage2 ${stage2:.2f} (ask+3%)]")
    fill2 = _fill_or_cancel(client, oid2, timeout=45)
    if fill2 is None:
        print(f"  ⏳ {symbol}: buy-to-close unfilled after both stages — retries next cycle")
    return fill2


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
                    pnl = (row.premium_received or 0) + ((row.strike or 0) - (row.avg_cost or 0)) * (row.shares_qty or 100)
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
    """
    Manage rules (30-45 DTE entries, monthly-ish cadence):
      - Profit-close at CC_PROFIT_CLOSE (60%) captured — two-stage buy, checked first.
      - At CC_MANAGE_DTE (21) DTE, if not already profit-closed:
          ITM  → roll out (and up, via _select_call's basis-anchored band) for net credit.
          OTM  → roll to the next monthly-ish expiry for net credit (< 60% captured).
        Debit rolls are skipped — let it ride to the next cycle instead.
    """
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
            premium_total = row.premium_received or 0
            buyback_total = mid * 100
            dte           = _dte(row.expiry or "")

            # Profit-close: buyback cost <= (1 - CC_PROFIT_CLOSE) of premium received
            if _should_profit_close(premium_total, buyback_total):
                captured = (premium_total - buyback_total) / premium_total
                print(f"  💰 {row.underlying}: profit-close {row.option_symbol} "
                      f"(buyback ~${buyback_total:,.0f}, captured {captured:.0%})")
                buy_fill = _two_stage_buy(client, row.option_symbol, bid, ask, mid,
                                          dry_run=dry_run, label="profit-close")
                if buy_fill is None and not dry_run:
                    continue  # nothing closed, DB untouched — retry next cycle
                if not dry_run:
                    row.realized_pnl = (row.realized_pnl or 0) + (premium_total - buy_fill * 100)
                    row.option_symbol = None
                    row.option_type   = None
                    row.strike        = 0
                    row.expiry        = None
                    row.premium_received = 0
                    s.commit()  # buyback booked before the next leg — each leg recoverable
                    # Sell a fresh call right away; on non-fill lot stays naked, COVER fixes it.
                    new_sym, new_strike, new_prem, new_exp = _select_call(row.underlying, row.avg_cost, dry_run)
                    if new_sym:
                        new_bid, new_ask, _ = _option_quote(new_sym)
                        new_dte = _dte(new_exp)
                        sell_fill = _two_stage_sell(client, new_sym, new_bid, new_ask, new_prem,
                                                    new_strike, new_dte, dry_run=False,
                                                    label="new call after profit-close")
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

            # 21-DTE management: profit-close above already caught the >=60%-captured
            # case, so reaching here means <60% captured. Roll for credit either way —
            # ITM rolls out (and up, since _select_call never sells below basis and
            # targets the fresh 30-45 DTE window at the 0.30Δ band), OTM rolls to the
            # next monthly-ish expiry rather than riding it out. Debit rolls are skipped.
            if dte <= CC_MANAGE_DTE:
                try:
                    from scripts.trading_data import get_quote
                    q = get_quote(row.underlying)
                    spot = q.get("last") or q.get("ask") or 0
                except Exception:
                    spot = 0
                itm = spot > (row.strike or 0) and spot > 0
                new_sym, new_strike, new_prem, new_exp = _select_call(row.underlying, row.avg_cost, dry_run)
                if not new_sym:
                    print(f"  ⏭  {row.underlying}: DTE={dte} but no roll candidate ≥ basis — letting ride")
                    continue
                roll_credit = (new_prem - mid) * 100
                if roll_credit < 0:
                    print(f"  ⏭  {row.underlying}: roll would be a debit (${roll_credit:,.0f}) — letting ride")
                    continue
                tag = "ITM" if itm else "OTM, <60% captured"
                print(f"  🔄 {row.underlying}: {tag} at DTE={dte}, rolling {row.option_symbol} → "
                      f"{new_sym} for ~${roll_credit:,.0f} credit")
                if dry_run:
                    _submit_limit(client, row.option_symbol, 1, OrderSide.BUY, ask or mid,
                                  dry_run=True, label="roll buy-back")
                    _submit_limit(client, new_sym, 1, OrderSide.SELL, new_prem,
                                  dry_run=True, label="roll new call")
                    continue
                buy_fill = _two_stage_buy(client, row.option_symbol, bid, ask, mid,
                                          dry_run=False, label="roll buy-back")
                if buy_fill is None:
                    continue  # buyback didn't fill — still short old call, retry next cycle
                row.realized_pnl  = (row.realized_pnl or 0) + (premium_total - buy_fill * 100)
                row.option_symbol = None
                row.option_type   = None
                row.strike        = 0
                row.expiry        = None
                row.premium_received = 0
                s.commit()
                new_bid, new_ask, _ = _option_quote(new_sym)
                new_dte = _dte(new_exp)
                sell_fill = _two_stage_sell(client, new_sym, new_bid, new_ask, new_prem,
                                            new_strike, new_dte, dry_run=False,
                                            label="roll new call")
                if sell_fill:
                    row.option_symbol    = new_sym
                    row.option_type      = "call"
                    row.strike           = new_strike
                    row.expiry           = new_exp
                    row.premium_received = sell_fill * 100
                    send_alert("CC Desk — Roll",
                               f"{row.underlying}: rolled ITM to {new_exp} ${new_strike:g} call, "
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
            bid, ask, mid = _option_quote(sym)
            if mid <= 0:
                mid = premium  # fallback to chain's cached mid
            fill = _two_stage_sell(client, sym, bid, ask, mid, strike, dte,
                                   dry_run=dry_run, label="cover")
            if fill is not None and not dry_run:
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


def _sector_of(ticker: str) -> str:
    return SCREENER_SECTOR.get(ticker, "Unknown")


# ── Step 4: ENTER (CSP-first) ──────────────────────────────────────────────────
def _enter(client, dry_run: bool = False):
    """
    CSP-first entry: new capital deploys by selling ~0.25Δ cash-secured puts on
    screener-ranked candidates (richest IV first, after price/spread/earnings
    filters — see trading_screener.py), not by buying shares outright. Share-buy
    + cover still happens for existing lots (COVER step) and after assignment
    (WHEEL step). Sector caps (max CC_MAX_PER_SECTOR per SECTOR bucket) and
    expiry laddering (spread across weeks, not stacked on one date) apply here.
    """
    print("\n  [CC 4/5] Enter new positions (CSP-first)...")
    s = Session()
    try:
        open_rows = s.query(TradingCCPosition).filter_by(status="open").all()
        held      = {r.underlying for r in open_rows}
        slots     = CC_MAX_UNDERLYINGS - len(held)
        if slots <= 0:
            print(f"  ⏭  At max {CC_MAX_UNDERLYINGS} underlyings — no new entries")
            return

        from collections import Counter
        sector_counts = Counter(_sector_of(u) for u in held)

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

        # Screen: IV-richest candidates first, already filtered on price/spread/
        # earnings. AI event-screen runs during live entry cycles (ai=True).
        try:
            candidates = screen_candidates(CC_DTE_MIN, CC_DTE_MAX, ai=True)
        except Exception as e:
            print(f"  ⚠️  Screener failed ({e}) — no entries this cycle")
            candidates = []

        entered, used_expiries = 0, []
        for c in candidates:
            if entered >= slots:
                break
            ticker = c["symbol"]
            if ticker in held or ticker in live_syms:
                continue
            sector = c.get("sector") or _sector_of(ticker)
            if sector_counts[sector] >= CC_MAX_PER_SECTOR:
                print(f"  ⏭  {ticker}: {sector} already at {CC_MAX_PER_SECTOR}-underlying cap — skip")
                continue

            max_strike = min(c["price"], CC_MAX_POSITION_USD / 100)
            # Pre-earnings cutoff from the screener's earnings date; fetch down to
            # the 14-DTE floor so _pick_put can duck under earnings if needed.
            earn_dt = date.fromisoformat(c["earnings_date"]) if c.get("earnings_date") else None
            max_exp = earnings_max_expiry(earn_dt)
            snaps = _get_option_snapshots(ticker, opt_type="put", dte_min=SCR_DTE_FLOOR)
            best = _pick_put(snaps, max_strike, used_expiries=used_expiries, max_expiry=max_exp)
            if not best:
                print(f"  ⚠️  {ticker}: no acceptable CSP clears the delta band/DTE window"
                      f"{f'/earnings {earn_dt}' if earn_dt else ''} — skip")
                continue
            cost = best["strike"] * 100
            if cost > avail - min_cash:
                print(f"  ⏭  {ticker} CSP ${cost:,.0f} secured would breach cash buffer — skip")
                continue
            yld = _annualized_yield(best["premium"], best["strike"], best["dte"])
            if yld < CC_MIN_ANNUAL_YIELD:
                print(f"  ⏭  {ticker}: CSP yield {yld:.1%}/yr below {CC_MIN_ANNUAL_YIELD:.0%} floor — skip")
                continue

            print(f"  🛒 CSP entry {ticker}: sell {best['symbol']} exp {best['expiry']} "
                  f"DTE={best['dte']} strike=${best['strike']:.2f} "
                  f"premium=${best['premium']*100:,.0f} yield={yld:.1%}/yr [{sector}]")

            # Cash-secured put reserves strike*100; release core SPY if account cash is tight
            try:
                from scripts.trading_data import get_account as _get_acct
                acct_cash = _get_acct().get("cash", 0)
                slack = CC_BOOK_USD * CC_CASH_BUFFER
                shortfall = cost - (acct_cash - slack)
                if shortfall > 0 and not dry_run:
                    from scripts.trading_core import release_core
                    print(f"  [core] releasing ${shortfall:,.0f} to secure the {ticker} CSP")
                    release_core(shortfall)
            except Exception as _ce:
                print(f"  ⚠️  [core] release check failed ({_ce}) — proceeding anyway")

            bid, ask, mid = _option_quote(best["symbol"])
            if mid <= 0:
                mid = best["premium"]
            fill = _two_stage_sell(client, best["symbol"], bid, ask, mid,
                                   best["strike"], best["dte"], dry_run=dry_run,
                                   label="CSP entry")
            if dry_run:
                sector_counts[sector] += 1
                used_expiries.append(best["expiry"])
                avail -= cost
                entered += 1
                continue
            if fill is None:
                print(f"  ⏳ {ticker}: CSP unfilled — retries next cycle")
                continue

            row = TradingCCPosition(
                underlying=ticker, shares_qty=0, avg_cost=0,
                option_symbol=best["symbol"], option_type="put",
                strike=best["strike"], expiry=best["expiry"],
                premium_received=fill * 100,
                status="open", opened_at=datetime.now(timezone.utc).isoformat(),
            )
            s.add(row)
            s.commit()
            send_alert("CC Desk — CSP Entry",
                       f"🧾 CC: sold {ticker} {best['expiry']} ${best['strike']:g} CSP "
                       f"for ${fill*100:,.0f} ({yld:.1%} annualized) [{sector}]")
            sector_counts[sector] += 1
            used_expiries.append(best["expiry"])
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
        from scripts.trading_data import get_quote, get_account
        used_expiries = []  # ladder across multiple same-cycle assignments
        try:
            free_cash = get_account().get("cash", 0) - CC_BOOK_USD * CC_CASH_BUFFER
        except Exception as e:
            print(f"  ⚠️  Wheel: account cash fetch failed ({e}) — skipping wheel this cycle")
            assigned = []
            free_cash = 0.0
        for row in assigned:
            try:
                q = get_quote(row.underlying)
                price = q.get("last") or q.get("ask") or 0
            except Exception as e:
                print(f"  ⚠️  {row.underlying}: quote failed ({e}) — skipping wheel this cycle")
                continue
            if not price:
                continue
            # Find ~0.25Δ put in the 30–45 DTE window, strike fitting available cash
            max_strike = min(price, CC_MAX_POSITION_USD / 100, CC_BOOK_USD * (1 - CC_CASH_BUFFER) / 100)
            # ponytail: unknown earnings on a wheel re-entry → no cutoff (we already
            # own the name's risk story); the screener's fail-safe skip is for NEW names.
            max_exp = earnings_max_expiry(get_next_earnings(row.underlying))
            snaps = _get_option_snapshots(row.underlying, opt_type="put", dte_min=SCR_DTE_FLOOR)
            best = _pick_put(snaps, max_strike, used_expiries=used_expiries, max_expiry=max_exp)
            if not best:
                print(f"  ⚠️  {row.underlying}: no put contracts in DTE window for CSP")
                continue
            if best["strike"] * 100 > free_cash:
                print(f"  ⏭  {row.underlying}: CSP needs ${best['strike'] * 100:,.0f} secured "
                      f"but only ${free_cash:,.0f} free above the cash buffer — skip")
                continue

            print(f"  🎡 Wheel {row.underlying}: sell put {best['symbol']} "
                  f"exp {best['expiry']} strike=${best['strike']:.2f} prem=${best['premium']*100:,.0f}")
            p_bid, p_ask, p_mid = _option_quote(best["symbol"])
            if p_mid <= 0:
                p_bid, p_ask, p_mid = 0.0, 0.0, best["premium"]
            fill = _two_stage_sell(client, best["symbol"], p_bid, p_ask, p_mid,
                                   best["strike"], best["dte"], dry_run=dry_run,
                                   label="CSP wheel")
            if fill is not None and not dry_run:
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
                used_expiries.append(best["expiry"])
                free_cash -= best["strike"] * 100  # collateral now reserved
        s.commit()
    finally:
        s.close()


# ── Public API ────────────────────────────────────────────────────────────────
def run_cc_cycle(dry_run: bool = False):
    """One full idempotent CC manage cycle. Called by orchestrator every 1h."""
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
            # Covered call: profit-close trigger + 21-DTE manage action
            prem = row.premium_received or 0
            buyback_trigger = round(prem * (1 - CC_PROFIT_CLOSE), 2)  # buy back ≤ this → 60% captured
            dte = _dte(row.expiry or "")
            expiry_note = ""
            if row.expiry:
                if dte <= CC_MANAGE_DTE:
                    expiry_note = (
                        f"; expires {row.expiry} — at {CC_MANAGE_DTE} DTE it rolls (ITM out-and-up, "
                        f"or OTM to the next monthly-ish expiry) for net credit only; a debit roll "
                        f"is skipped and left to ride"
                    )
                else:
                    expiry_note = f"; expires {row.expiry}"
            lines.append(
                f"{sym} ${row.strike:.2f} call exp {row.expiry} (DTE {dte}) — "
                f"profit-close triggers if buyback ≤ ${buyback_trigger:.2f}/contract"
                f"{expiry_note}"
            )
        else:
            # Naked lot — waiting for a call to be sold
            lines.append(f"{sym} — will retry selling a call next cycle (naked lot)")
    return lines


def _print_status():
    """Print CC book positions + premium vs the $1,000/week target + annualized yield-on-book."""
    s = Session()
    try:
        today     = date.today().isoformat()
        mtd_start = today[:7] + "-01"
        wtd_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()  # Monday
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

    # ponytail: opened_at is an ISO string, so >= "YYYY-MM-01" compares correctly;
    # a position rolled across a month boundary undercounts (its premium lives in
    # realized_pnl) — acceptable until premium gets its own ledger table.
    premium_mtd  = sum((r.premium_received or 0) for r in open_rows
                       if (r.opened_at or "") >= mtd_start) + \
                   sum((r.premium_received or 0) for r in closed)
    realized_pnl = sum((r.realized_pnl or 0) for r in closed)
    # WTD ⊂ MTD, so re-filter the already-loaded rows by the Monday cutoff.
    premium_wtd  = sum((r.premium_received or 0) for r in open_rows
                       if (r.opened_at or "") >= wtd_start) + \
                   sum((r.premium_received or 0) for r in closed
                       if (r.closed_at or "") >= wtd_start)
    wk_pct  = premium_wtd / CC_WEEKLY_TARGET_USD if CC_WEEKLY_TARGET_USD else 0
    mo_pct  = premium_mtd / CC_MONTHLY_TARGET_USD if CC_MONTHLY_TARGET_USD else 0
    days_elapsed = date.today().day  # mtd_start is always the 1st
    annualized_yield = (premium_mtd / CC_BOOK_USD) * (365 / days_elapsed) if days_elapsed else 0
    print(f"\n  Premium WTD: ${premium_wtd:.2f} / ${CC_WEEKLY_TARGET_USD:.0f} weekly target ({wk_pct:.0%})")
    print(f"  Premium MTD: ${premium_mtd:.2f} / ${CC_MONTHLY_TARGET_USD:.0f} ({mo_pct:.0%})")
    print(f"  Annualized yield-on-book: {annualized_yield:.1%} (target ~104%)")
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
    """Stub-driven tests: profit-close / never-below-basis / call+CSP delta bands /
    OCC parse / bid-floor math / 30-45 DTE window / 21-DTE management trigger /
    CSP-first entry decision / expiry laddering."""
    print("── CC self-check ──────────────────────────────────────────────────\n")

    # 1. Profit-close: boundary at 60% captured (CC_PROFIT_CLOSE = 0.60)
    #    buyback_total <= premium * (1 - 0.60) = premium * 0.40
    #    premium=200 → threshold=$80; at exactly 80 → triggers
    assert _should_profit_close(200.0, 80.0),      "must trigger at exactly 60% captured (buyback=80)"
    assert _should_profit_close(200.0, 60.0),      "must trigger past 60% captured"
    assert not _should_profit_close(200.0, 90.0),  "must NOT trigger at 55% captured (buyback=90 > 80)"
    assert not _should_profit_close(0.0, 0.0),     "no premium → never trigger"
    print("  ✅ profit-close rule: triggers at 60% captured (buyback ≤ $80 on $200 premium), not before")

    # 2. OCC symbol parsing
    assert _parse_occ("AAPL260814C00270000") == ("call", "2026-08-14", 270.0)
    assert _parse_occ("F260918P00011500")    == ("put",  "2026-09-18", 11.5)
    assert _parse_occ("garbage") is None
    print("  ✅ OCC parse: type/expiry/strike from symbol")

    # 3. Monthly DTE window: CC_DTE_MIN=30, CC_DTE_MAX=45, manage at 21
    assert CC_DTE_MIN == 30, f"DTE_MIN should be 30, got {CC_DTE_MIN}"
    assert CC_DTE_MAX == 45, f"DTE_MAX should be 45, got {CC_DTE_MAX}"
    assert CC_MANAGE_DTE == 21, f"manage DTE should be 21, got {CC_MANAGE_DTE}"
    exp_monthly = (date.today() + timedelta(days=35)).strftime("%y%m%d")  # 35 DTE → IN window
    exp_weekly  = (date.today() + timedelta(days=7)).strftime("%y%m%d")   # 7 DTE  → OUT of window
    def stub_call(strike: float, delta, exp_code=exp_monthly, bid=1.0, ask=1.2):
        s = {"symbol": f"AAPL{exp_code}C{int(strike*1000):08d}",
             "latestQuote": {"bp": bid, "ap": ask}}
        if delta is not None:
            s["greeks"] = {"delta": delta}
        return s
    def stub_put(strike: float, delta, exp_code=exp_monthly, bid=1.0, ask=1.2):
        s = {"symbol": f"AAPL{exp_code}P{int(strike*1000):08d}",
             "latestQuote": {"bp": bid, "ap": ask}}
        if delta is not None:
            s["greeks"] = {"delta": delta}  # puts carry negative delta on the wire
        return s
    # Weekly (7 DTE) contract rejected by the 30-45 window; monthly (35 DTE) accepted
    best = _pick_call([stub_call(160, 0.30, exp_weekly), stub_call(160, 0.30, exp_monthly)], avg_cost=150.0)
    assert best is not None, "35-DTE monthly contract should be accepted"
    assert CC_DTE_MIN <= _dte(best["expiry"]) <= CC_DTE_MAX, \
        f"selected expiry {best['expiry']} is outside the 30-45 DTE window"
    print("  ✅ 30-45 DTE window: 7-DTE weekly rejected, 35-DTE monthly accepted")

    # 4. Never-below-basis (calls)
    best = _pick_call([stub_call(148, 0.30), stub_call(160, 0.32), stub_call(165, 0.40)], avg_cost=150.0)
    assert best and best["strike"] == 160, f"expected $160 (only in-band strike ≥ basis), got {best}"
    print(f"  ✅ never-below-basis: $148 @ Δ0.30 rejected, picked ${best['strike']:g}")

    # 5. Call delta band CC_DELTA_BAND = (0.25, 0.35), target 0.30
    best = _pick_call([stub_call(155, 0.29), stub_call(160, 0.35), stub_call(165, 0.25)], avg_cost=150.0)
    assert best and best["strike"] == 155, f"0.29 (closest to 0.30) should win, got {best}"
    best = _pick_call([stub_call(150, 0.45), stub_call(156, 0.10), stub_call(170, None)], avg_cost=150.0)
    assert best and best["strike"] == 156 and best.get("_fallback"), f"4% OTM fallback broken: {best}"
    assert _pick_call([stub_call(140, 0.30), stub_call(145, 0.30)], avg_cost=150.0) is None
    print("  ✅ call delta band (0.25-0.35, target 0.30): closest wins; no-band → 4% OTM; none ≥ basis → None")

    # 6. CSP delta band CSP_DELTA_BAND = (0.20, 0.30), target 0.25 — mirrors calls via _pick_put
    best = _pick_put([stub_put(95, 0.24), stub_put(90, 0.30), stub_put(85, 0.20)], max_strike=100.0)
    assert best and best["strike"] == 95, f"0.24 (closest to 0.25) should win, got {best}"
    best = _pick_put([stub_put(105, 0.24)], max_strike=100.0)  # strike above cash cap
    assert best is None, "strike over max_strike must be excluded from CSP selection"
    print("  ✅ CSP delta band (0.20-0.30, target 0.25): closest wins; over-cash strikes excluded")

    # 6b. max_expiry threading (pre-earnings cutoff) + 14-DTE floor fallback
    exp_18d = (date.today() + timedelta(days=18)).strftime("%y%m%d")  # ducks under earnings
    chain = [stub_put(95, 0.25, exp_18d), stub_put(95, 0.25, exp_monthly)]
    # Earnings 25d out → cutoff 23d < 30-DTE floor → floor relaxes to 14, 18-DTE expiry chosen
    cutoff = date.today() + timedelta(days=23)
    best = _pick_put(chain, max_strike=100.0, max_expiry=cutoff)
    assert best and _dte(best["expiry"]) == 18, f"should duck under earnings via 18-DTE expiry: {best}"
    # No constraint → normal 30-45 window, 14-29 DTE contracts stay excluded
    best = _pick_put(chain, max_strike=100.0)
    assert best and _dte(best["expiry"]) == 35, f"unconstrained pick must stay in 30-45 DTE: {best}"
    # Earnings 10d out → cutoff 8d < 14-DTE floor → nothing clears → None (skip name)
    best = _pick_put(chain, max_strike=100.0, max_expiry=date.today() + timedelta(days=8))
    assert best is None, "no expiry >= 14 DTE clears earnings → None"
    print("  ✅ max_expiry threading: ducks under earnings to 14-DTE floor, skips when nothing clears")

    # 7. Expiry laddering: prefer a non-colliding week over a slightly-better delta
    exp_a = (date.today() + timedelta(days=32)).isoformat()
    exp_b = (date.today() + timedelta(days=40)).isoformat()  # >7d from exp_a → non-colliding
    band = [{"symbol": "A", "strike": 90, "expiry": exp_a, "dte": 32, "delta": 0.25, "premium": 1.0},
           {"symbol": "B", "strike": 91, "expiry": exp_b, "dte": 40, "delta": 0.24, "premium": 1.0}]
    picked = _ladder_pick(band, used_expiries=[exp_a], target_delta=0.25)
    assert picked["symbol"] == "B", f"should avoid the used week even though A's delta is closer: {picked}"
    # No non-colliding option → falls back to closest-delta
    picked2 = _ladder_pick(band, used_expiries=[exp_a, exp_b], target_delta=0.25)
    assert picked2["symbol"] == "A", f"all weeks collide → fall back to delta-closeness: {picked2}"
    print("  ✅ expiry laddering: avoids already-used weeks, falls back to delta-closeness when boxed in")

    # 8. Annualized yield gate (unchanged — 10% floor)
    yld = _annualized_yield(1.50, 150.00, 35)
    assert yld >= CC_MIN_ANNUAL_YIELD, f"10%+ yield should pass gate: {yld:.2%}"
    low_yld = _annualized_yield(0.50, 150.00, 35)
    assert low_yld < CC_MIN_ANNUAL_YIELD, f"3.5% should fail gate: {low_yld:.2%}"
    print(f"  ✅ yield gate: {yld:.1%} passes, {low_yld:.1%} fails")

    # 9. Bid-floor math: premium_floor = strike × CC_MIN_ANNUAL_YIELD × (DTE/365)
    #    $190 strike, 35 DTE, 10% yield → floor = 190 * 0.10 * (35/365) = $1.822.../share
    floor = _premium_floor(190.0, 35)
    expected = 190.0 * 0.10 * (35 / 365)
    assert abs(floor - expected) < 1e-9, f"floor math wrong: {floor:.6f} != {expected:.6f}"
    assert _premium_floor(0.0, 35)  == 0.0, "zero strike → zero floor"
    assert _premium_floor(190.0, 0) == 0.0, "zero DTE → zero floor"
    print(f"  ✅ bid-floor: $190 strike 35 DTE → floor=${floor:.4f}/share")

    # 10. 21-DTE management trigger + CSP-first sizing constants
    assert CC_MANAGE_DTE == 21, "manage gate must be 21 DTE"
    # Profit-close is checked FIRST in _manage — a position at dte<=21 with 60%
    # captured takes the profit-close branch, not the roll branch.
    assert _should_profit_close(100.0, 40.0),  "dte<=21, 60% captured → profit-close should trigger"
    assert not _should_profit_close(100.0, 50.0), "dte<=21, 50% captured → falls through to roll-for-credit"
    assert CC_MAX_POSITION_USD == 10_000 and CC_MAX_UNDERLYINGS == 12 and CC_MAX_PER_SECTOR == 2
    print("  ✅ 21-DTE trigger: profit-close checked first, roll-for-credit otherwise; sizing constants set")

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
