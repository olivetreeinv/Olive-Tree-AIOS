#!/usr/bin/env python3
"""
trading_movers.py — Suna-style weekly stock discovery for Premium Desk v3.

Replaces the frozen 38-name blue-chip universe with a pool rebuilt each week from
real market movers, mirroring Kenneth Suna's CNBC-movers hunt — but sourced
natively from Alpaca (our existing data provider, free tier).

Discovery only. Option-based filtering (premium band, liquidity floor, delta pick)
lives in trading_suna.py, which consumes this module's raw candidate pool.

    from scripts.trading_movers import discover
    pool = discover(top=60)   # -> [{"symbol","price","pct_change","source"}, ...]

    python3 scripts/trading_movers.py            # live pool, printed
    python3 scripts/trading_movers.py --test     # offline parse self-check
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data import _get, _alpaca_headers, _ALPACA_DATA  # noqa: E402

# Suna trades $10–$100 names (100-share lot ≤ the $10k position cap). Wider than a
# single strategy needs so the premium/liquidity filters downstream do the real work.
MOVERS_PRICE_MIN = 10.0
MOVERS_PRICE_MAX = 100.0

# Well-known ETFs/leveraged products that show up in movers but aren't single-name
# covered-call candidates Suna would trade. Cheap denylist; extend as needed.
_DENY = {
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "TQQQ", "SQQQ", "SOXL", "SOXS",
    "UVXY", "VXX", "SVXY", "TNA", "TZA", "SPXL", "SPXS", "UPRO", "SDOW",
    "TSLL", "NVDL", "TSLQ", "BOIL", "KOLD", "USO", "UNG", "GLD", "SLV",
}


MOVERS_TOP_MAX = 50   # Alpaca hard cap on the movers endpoint


def _movers(top: int) -> list[dict]:
    """Alpaca screener: top gainers AND losers (Suna hunts droppers too).
    Each item carries symbol, price, and percent_change."""
    url = f"{_ALPACA_DATA}/v1beta1/screener/stocks/movers?top={min(top, MOVERS_TOP_MAX)}"
    data = _get(url, _alpaca_headers()) or {}
    out = []
    for bucket in ("gainers", "losers"):
        for row in data.get(bucket, []) or []:
            out.append({
                "symbol": row.get("symbol", "").upper(),
                "price": _f(row.get("price")),
                "pct_change": _f(row.get("percent_change")),
                "source": bucket,
            })
    return out


def _most_actives(top: int) -> list[dict]:
    """Alpaca screener: highest-volume names. No price/%chg in the payload —
    price is resolved later by the caller; here we just surface the symbols."""
    url = f"{_ALPACA_DATA}/v1beta1/screener/stocks/most-actives?top={top}"
    data = _get(url, _alpaca_headers()) or {}
    return [{"symbol": (r.get("symbol") or "").upper(), "price": None,
             "pct_change": None, "source": "active"}
            for r in (data.get("most_actives") or [])]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dedup_priority(rows: list[dict]) -> list[dict]:
    """One row per symbol. Prefer a row that carries price/%chg (movers) over a
    bare most-actives row, so downstream doesn't need an extra price lookup."""
    best: dict[str, dict] = {}
    for r in rows:
        sym = r["symbol"]
        if not sym:
            continue
        prev = best.get(sym)
        if prev is None or (prev.get("price") is None and r.get("price") is not None):
            best[sym] = r
    return list(best.values())


def _price_ok(price) -> bool:
    # Unknown price (most-actives rows) passes here; trading_suna resolves + re-checks it.
    return price is None or (MOVERS_PRICE_MIN <= price <= MOVERS_PRICE_MAX)


def discover(top: int = 60, include_actives: bool = True) -> list[dict]:
    """Weekly candidate pool from Alpaca movers (+ most-actives). Applies only the
    cheap symbol/price filters; option-based screening happens in trading_suna."""
    rows = _movers(top)
    if include_actives:
        rows += _most_actives(top)
    rows = _dedup_priority(rows)
    pool = [r for r in rows
            if r["symbol"] not in _DENY
            and "." not in r["symbol"]          # skip preferreds/warrants (BRK.B etc.)
            and _price_ok(r["price"])]
    # Biggest movers first (unknown %chg — most-actives — sinks to the bottom).
    pool.sort(key=lambda r: abs(r["pct_change"]) if r["pct_change"] is not None else -1,
              reverse=True)
    return pool


# ── self-check ────────────────────────────────────────────────────────────────
def _test():
    # Offline: drive the pure filters/dedup with a stubbed screener payload.
    rows = [
        {"symbol": "HIMS", "price": 56.0, "pct_change": -9.0, "source": "losers"},
        {"symbol": "HIMS", "price": None, "pct_change": None, "source": "active"},  # dup, worse
        {"symbol": "SPY",  "price": 55.0, "pct_change": 3.0, "source": "gainers"},  # denylisted
        {"symbol": "BRK.B", "price": 60.0, "pct_change": 4.0, "source": "gainers"}, # dotted
        {"symbol": "AAPL", "price": 500.0, "pct_change": 2.0, "source": "gainers"}, # too pricey
        {"symbol": "F",    "price": 12.0, "pct_change": 6.0, "source": "gainers"},
        {"symbol": "MSFT", "price": None, "pct_change": None, "source": "active"},  # price TBD
    ]
    pool = _dedup_priority(rows)
    pool = [r for r in pool if r["symbol"] not in _DENY and "." not in r["symbol"]
            and _price_ok(r["price"])]
    syms = {r["symbol"] for r in pool}
    assert "SPY" not in syms, "denylist failed"
    assert "BRK.B" not in syms, "dotted-symbol filter failed"
    assert "AAPL" not in syms, "price-max filter failed"
    assert syms == {"HIMS", "F", "MSFT"}, f"unexpected pool: {syms}"
    # dedup kept the priced HIMS row, not the bare active one
    hims = next(r for r in pool if r["symbol"] == "HIMS")
    assert hims["price"] == 56.0, "dedup dropped the priced row"
    # MSFT (unknown price) survives for downstream price resolution
    assert _price_ok(None) is True
    assert _price_ok(9.0) is False and _price_ok(150.0) is False
    print("✅ trading_movers self-check passed")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        for r in discover():
            pc = f"{r['pct_change']:+.1f}%" if r["pct_change"] is not None else "  n/a"
            pr = f"${r['price']:.2f}" if r["price"] is not None else "   n/a"
            print(f"  {r['symbol']:6s} {pr:>9s} {pc:>7s}  [{r['source']}]")
