#!/usr/bin/env python3
"""
trading_movers.py — Suna-style weekly stock discovery for Premium Desk v3.

Replaces the frozen 38-name blue-chip universe with a pool rebuilt each week from
real market movers, mirroring Kenneth Suna's CNBC-movers hunt — but sourced
natively from Alpaca (our existing data provider, free tier).

Three sources: top gainers/losers, most-actives, and the S&P 500 + MidCap 400
constituents inside the price band (the screener universe — see _index_inband).

Discovery only, and deliberately wide — this module applies just symbol/price
filters. All of Suna's actual selection happens in trading_suna.py: the stock
screener (single-name only, beta, short interest) in stock_filters_ok(), then
the option side (premium band, liquidity floor, delta pick). Do not add quality
filters here; a name rejected at this layer never reaches the screener that is
supposed to judge it.

    from scripts.trading_movers import discover
    pool = discover(top=60)   # -> [{"symbol","price","pct_change","source"}, ...]

    python3 scripts/trading_movers.py            # live pool, printed
    python3 scripts/trading_movers.py --test     # offline parse self-check
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data import _get, _alpaca_headers, _ALPACA_DATA, EQUITY_UNIVERSE  # noqa: E402

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


_SP400_FILE = Path(__file__).parent.parent / "data" / "sp400.txt"


def _midcap_universe() -> list[str]:
    """S&P MidCap 400 constituents. Frozen snapshot, same one-ticker-per-line
    pattern as data/sp500.txt. Empty list if the file is missing — the S&P 500
    source still carries the pool."""
    try:
        return [l.strip() for l in _SP400_FILE.read_text().splitlines() if l.strip()]
    except OSError:
        return []


def _index_inband() -> list[dict]:
    """Index constituents inside the price band — the desk's *screener universe*.

    Suna works two sources: CNBC movers (the hunt) and a Schwab screener over a
    broad optionable universe that he narrows by sector/price/beta/short-interest
    down to ~9 names. `_movers`/`_most_actives` above are the first; this is a
    cheap stand-in for the second. It is NOT a quality signal on its own — the
    selecting is done by stock_filters_ok() in trading_suna, which is what makes
    a broad universe safe to pour in here.

    Two indexes, because he explicitly shops mid-cap and away from the mega-caps:
    "I went on Seeking Alpha, I typed in mid-cap growth ... cherry-pick their list
    of top 10 holdings" (kenneth-suna/_transcripts/JCTs4QXTIwI.txt). He names no
    ETF ticker anywhere in the corpus, so the S&P MidCap 400 stands in for the
    segment. Measured 2026-07-31, the S&P 500 alone supplied 175 of 238 pool
    names — a large-cap index doing the work of a mid-cap screen.

    Cost: one bulk price call per 200 symbols; the per-name walk in
    trading_suna._enter is self-limiting — it stops once the book is full.
    """
    seen, syms = set(), []
    for source, universe in (("sp500", EQUITY_UNIVERSE), ("sp400", _midcap_universe())):
        for s in universe:
            if "." not in s and s not in _DENY and s not in seen:
                seen.add(s)
                syms.append((s, source))
    out = []
    for i in range(0, len(syms), 200):
        chunk = syms[i:i + 200]
        src = dict(chunk)
        try:
            data = _get(f"{_ALPACA_DATA}/v2/stocks/trades/latest?symbols="
                        + ",".join(s for s, _ in chunk), _alpaca_headers()) or {}
        except Exception as e:
            print(f"  ⚠️  index price fetch failed ({e}) — movers-only pool this cycle")
            continue  # fail-open: degrade to the movers-only pool, never block discovery
        for sym, trade in (data.get("trades") or {}).items():
            price = _f(trade.get("p"))
            if price and MOVERS_PRICE_MIN <= price <= MOVERS_PRICE_MAX:
                out.append({"symbol": sym.upper(), "price": price,
                            "pct_change": None, "source": src.get(sym.upper(), "index")})
    return out


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


def _pool_rank(r: dict) -> tuple:
    """Sort key for the candidate pool: BIGGEST DROPPERS FIRST.

    Entry slots are finite, so this decides what actually gets bought — and Suna
    shops the downside: "Companies that have been in a downtrend are the kinds of
    stocks that I like to then buy when they're way down ... I look for stocks
    that have been in a downtrend" (kenneth-suna/_transcripts/8fyt8c4_uEQ.txt).
    This used to be abs(pct_change) descending, which put the biggest GAINER at
    the head of the queue — names already_ripped() then rejected one by one.

    Unknown %chg (most-actives, index rows) sinks below every real mover.
    """
    return (r["pct_change"] is None, r["pct_change"] or 0)


def _price_ok(price) -> bool:
    # Unknown price (most-actives rows) passes here; trading_suna resolves + re-checks it.
    return price is None or (MOVERS_PRICE_MIN <= price <= MOVERS_PRICE_MAX)


def discover(top: int = 60, include_actives: bool = True) -> list[dict]:
    """Weekly candidate pool from Alpaca movers (+ most-actives). Applies only the
    cheap symbol/price filters; option-based screening happens in trading_suna."""
    rows = _movers(top)
    if include_actives:
        rows += _most_actives(top)
    rows += _index_inband()   # appended last → sorts behind the movers (pct_change=None)
    rows = _dedup_priority(rows)
    pool = [r for r in rows
            if r["symbol"] not in _DENY
            and "." not in r["symbol"]          # skip preferreds/warrants (BRK.B etc.)
            and _price_ok(r["price"])]
    pool.sort(key=_pool_rank)   # biggest droppers first — see _pool_rank
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

    # Index breadth source: ranks BEHIND the movers (pct_change=None sinks to the
    # bottom), and a mover row wins dedup so source/pct_change survive for the
    # structural-drop screen in trading_suna._enter.
    mixed = _dedup_priority([
        {"symbol": "HIMS", "price": 56.0, "pct_change": -9.0, "source": "losers"},
        {"symbol": "NKE",  "price": 41.0, "pct_change": None, "source": "active"},
        {"symbol": "HIMS", "price": 56.0, "pct_change": None, "source": "sp500"},  # dup, loses
        {"symbol": "SLB",  "price": 49.0, "pct_change": None, "source": "sp400"},
    ])
    mixed.sort(key=_pool_rank)   # the SAME key discover() uses, not a copy of it
    assert mixed[0]["symbol"] == "HIMS", "movers must rank ahead of the index breadth source"
    assert mixed[0]["source"] == "losers", "dedup dropped the mover row's source/pct_change"
    assert [r["symbol"] for r in mixed[1:]] == ["NKE", "SLB"], "insertion order not preserved"

    # Downtrend-first: a big GAINER must rank behind every dropper, and behind a
    # smaller dropper too. The old abs() key put +18% at the head of the queue.
    ranked = sorted([
        {"symbol": "RIPPER", "price": 40.0, "pct_change": 18.0, "source": "gainers"},
        {"symbol": "SMALLDIP", "price": 30.0, "pct_change": -2.0, "source": "losers"},
        {"symbol": "BIGDIP", "price": 20.0, "pct_change": -11.0, "source": "losers"},
        {"symbol": "IDX", "price": 25.0, "pct_change": None, "source": "sp400"},
    ], key=_pool_rank)
    assert [r["symbol"] for r in ranked] == ["BIGDIP", "SMALLDIP", "RIPPER", "IDX"], \
        f"downtrend-first sort wrong: {[r['symbol'] for r in ranked]}"

    # Mid-cap universe loads and is disjoint from the S&P 500 (no dedup waste).
    mid = _midcap_universe()
    assert len(mid) > 300, f"sp400 list looks short: {len(mid)}"
    assert not (set(mid) & set(EQUITY_UNIVERSE)), "sp400 overlaps sp500"
    print("✅ trading_movers self-check passed")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        for r in discover():
            pc = f"{r['pct_change']:+.1f}%" if r["pct_change"] is not None else "  n/a"
            pr = f"${r['price']:.2f}" if r["price"] is not None else "   n/a"
            print(f"  {r['symbol']:6s} {pr:>9s} {pc:>7s}  [{r['source']}]")
