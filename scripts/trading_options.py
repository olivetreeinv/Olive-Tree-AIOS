#!/usr/bin/env python3
"""
trading_options.py — Options contract selection + order submission for the Trading Desk.

Finds near-ATM equity options (calls for LONG, puts for SHORT) and submits
paper market orders via Alpaca. Always paper=True.

Usage:
  python3 scripts/trading_options.py --symbol NVDA --direction long  # test lookup
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import ContractType, OrderSide, TimeInForce
from alpaca.trading.requests import GetOptionContractsRequest, MarketOrderRequest

# ── Config ────────────────────────────────────────────────────────────────────
_PAPER          = True
DTE_MIN         = 21    # minimum days to expiration
DTE_MAX         = 45    # maximum days to expiration
STRIKE_BAND_PCT = 0.05  # look for strikes within ±5% of current price
MIN_OPEN_INT    = 5     # skip illiquid contracts with fewer open interest contracts

# Options budget: 2% of equity per trade (smaller than equity 5% — options can go to zero)
OPTION_POSITION_PCT = 0.02


def _client() -> TradingClient:
    return TradingClient(
        os.getenv("ALPACA_API_KEY", ""),
        os.getenv("ALPACA_SECRET_KEY", ""),
        paper=_PAPER,
    )


def find_contract(symbol: str, direction: str, quote_price: float) -> tuple[str, float]:
    """
    Find the best near-ATM option contract for a directional thesis.
    direction: 'long' → call | 'short' → put
    Returns: (occ_symbol, estimated_premium) or ("", 0.0) if none found.

    Contract selection: nearest-to-ATM strike, ≥ DTE_MIN open interest, in DTE window.
    premium is close_price (yesterday's settle). Used only for paper-mode sizing.
    """
    contract_type = ContractType.CALL if direction == "long" else ContractType.PUT
    today   = date.today()
    exp_min = today + timedelta(days=DTE_MIN)
    exp_max = today + timedelta(days=DTE_MAX)

    strike_lo = str(round(quote_price * (1 - STRIKE_BAND_PCT), 2))
    strike_hi = str(round(quote_price * (1 + STRIKE_BAND_PCT), 2))

    try:
        resp = _client().get_option_contracts(GetOptionContractsRequest(
            underlying_symbols=[symbol],
            type=contract_type,
            expiration_date_gte=exp_min,
            expiration_date_lte=exp_max,
            strike_price_gte=strike_lo,
            strike_price_lte=strike_hi,
            limit=20,
        ))
    except Exception as e:
        print(f"  ⚠️  Options contract lookup failed for {symbol}: {e}", file=sys.stderr)
        return "", 0.0

    contracts = resp.option_contracts or []

    # Filter: tradable + minimum liquidity
    tradable = [c for c in contracts if c.tradable and int(c.open_interest or 0) >= MIN_OPEN_INT]
    if not tradable:
        # Relax liquidity floor if nothing passes
        tradable = [c for c in contracts if c.tradable]
    if not tradable:
        return "", 0.0

    # Pick nearest-to-ATM strike
    best = min(tradable, key=lambda c: abs(float(c.strike_price) - quote_price))
    premium = float(best.close_price) if best.close_price else quote_price * 0.02

    return best.symbol, premium


def size_contracts(equity: float, premium: float) -> int:
    """How many contracts to buy given portfolio equity and option premium per share."""
    budget    = equity * OPTION_POSITION_PCT
    per_contract = premium * 100  # 1 contract = 100 shares
    if per_contract <= 0:
        return 0
    return max(1, int(budget / per_contract))


def submit_option_order(contract_symbol: str, n_contracts: int) -> dict:
    """
    Buy N option contracts (market order, paper only).
    Always BUY — we only buy calls/puts, never write.
    Returns order summary dict.
    """
    if n_contracts <= 0:
        return {"submitted": False, "reason": "zero contracts sized"}

    try:
        order = _client().submit_order(MarketOrderRequest(
            symbol=contract_symbol,
            qty=n_contracts,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        ))
        print(f"  📤 Options order: BUY {n_contracts}x {contract_symbol}")
        print(f"     Alpaca ID: {order.id}")
        return {
            "submitted":       True,
            "contract_symbol": contract_symbol,
            "contracts":       n_contracts,
            "alpaca_id":       str(order.id),
            "status":          str(order.status),
        }
    except Exception as e:
        print(f"  ⚠️  Options order failed ({contract_symbol}): {e}", file=sys.stderr)
        return {"submitted": False, "reason": str(e)}


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Options contract lookup test")
    ap.add_argument("--symbol",    required=True)
    ap.add_argument("--direction", default="long", choices=["long", "short"])
    ap.add_argument("--price",     type=float, default=0,
                    help="Override quote price (default: fetch live)")
    args = ap.parse_args()

    price = args.price
    if not price:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.trading_data import get_quote
        q     = get_quote(args.symbol)
        price = q.get("ask") or q.get("last") or 0
        print(f"Live quote for {args.symbol}: ${price}")

    contract, premium = find_contract(args.symbol, args.direction, price)
    if contract:
        equity    = 100_000
        n         = size_contracts(equity, premium)
        notional  = n * premium * 100
        print(f"Best contract: {contract}")
        print(f"Premium (close): ${premium:.2f}  →  {n} contract(s)  ≈ ${notional:,.0f}")
    else:
        print(f"No contract found for {args.symbol} {args.direction}")
