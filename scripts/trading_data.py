#!/usr/bin/env python3
"""
trading_data.py — shared data layer for the Olive Tree Trading Desk.

Provides:
  - UNIVERSE: ~25 liquid US large-caps/ETFs + BTC/ETH for overnight
  - get_bars()          : historical OHLCV from Polygon (equities) or Alpaca (crypto)
  - get_quote()         : latest bid/ask/last from Alpaca
  - get_account()       : Alpaca paper account summary
  - get_snapshot()      : intraday change%, VWAP, volume from Polygon
  - get_news()          : recent headlines from Polygon news API
  - get_technicals()    : RSI + MACD from Polygon indicators
  - get_fear_greed()    : Crypto Fear & Greed index (alternative.me, free)
  - get_top_movers()    : filter universe to top N by absolute 5d move
  - is_market_open()    : NYSE market hours check (no API call)

Usage:
  python3 scripts/trading_data.py               # smoke test all data paths
  python3 scripts/trading_data.py --symbol AAPL --days 30
"""

import argparse
import os
import sys
import json
import time
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Equity + ETF universe (NYSE/NASDAQ, traded during market hours) ─────────
EQUITY_UNIVERSE = [
    "SPY", "QQQ",                                    # broad market ETFs / benchmark
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "BRK.B", "JPM", "V", "UNH", "XOM",
    "AMD", "NFLX", "CRM", "ADBE",
    "IWM", "GLD", "TLT",                             # small-cap, gold, long-bond ETFs
]

# ── Crypto universe (traded 24/7, active overnight when equities are closed) ─
CRYPTO_UNIVERSE = ["BTC/USD", "ETH/USD", "SOL/USD"]

UNIVERSE = EQUITY_UNIVERSE + CRYPTO_UNIVERSE

# ── Alpaca REST helpers (stdlib only — no alpaca-py dep here so scripts can
#    import this module without the full SDK installed in restricted envs) ────
_ALPACA_BASE  = "https://paper-api.alpaca.markets"
_ALPACA_DATA  = "https://data.alpaca.markets"
_POLY_BASE    = "https://api.polygon.io"

_SSL = ssl.create_default_context()
try:
    import certifi
    _SSL.load_verify_locations(cafile=certifi.where())
except Exception:
    pass


def _alpaca_headers() -> dict:
    key    = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        raise EnvironmentError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=_SSL, timeout=15) as r:
        return json.loads(r.read())


def get_account() -> dict:
    """Return Alpaca paper account fields as a dict."""
    data = _get(f"{_ALPACA_BASE}/v2/account", _alpaca_headers())
    return {
        "status":        data.get("status"),
        "equity":        float(data.get("equity", 0)),
        "cash":          float(data.get("cash", 0)),
        "buying_power":  float(data.get("buying_power", 0)),
        "portfolio_value": float(data.get("portfolio_value", data.get("equity", 0))),
    }


def get_open_position_count() -> int:
    """Return number of open positions from Alpaca (cloud-safe; no local DB needed)."""
    try:
        positions = _get(f"{_ALPACA_BASE}/v2/positions", _alpaca_headers())
        return len(positions) if isinstance(positions, list) else 0
    except Exception:
        return 0


def get_quote(symbol: str) -> dict:
    """Latest trade + bid/ask for a symbol from Alpaca data API."""
    is_crypto = "/" in symbol
    if is_crypto:
        sym_enc = symbol.replace("/", "%2F")
        url = f"{_ALPACA_DATA}/v1beta3/crypto/us/latest/quotes?symbols={sym_enc}"
        data = _get(url, _alpaca_headers())
        q = data.get("quotes", {}).get(symbol, {})
        return {"symbol": symbol, "bid": q.get("bp", 0), "ask": q.get("ap", 0), "last": (q.get("bp", 0) + q.get("ap", 0)) / 2}
    else:
        url = f"{_ALPACA_DATA}/v2/stocks/{symbol}/quotes/latest"
        data = _get(url, _alpaca_headers())
        q = data.get("quote", {})
        return {"symbol": symbol, "bid": q.get("bp", 0), "ask": q.get("ap", 0), "last": q.get("ap", 0)}


def get_bars(symbol: str, days: int = 60, timeframe: str = "1Day") -> list[dict]:
    """
    Return OHLCV bars as list of dicts with keys: t, o, h, l, c, v.
    Uses Polygon for equities (more history on free tier), Alpaca for crypto.
    """
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days + 10)   # buffer for weekends/holidays

    if "/" in symbol:
        # Crypto via Alpaca — paginate; one page caps at 1000 bars (hourly over weeks exceeds that)
        sym_enc = symbol.replace("/", "%2F")
        base = (
            f"{_ALPACA_DATA}/v1beta3/crypto/us/bars"
            f"?symbols={sym_enc}&timeframe={timeframe}"
            f"&start={start}&end={end}&limit=1000"
        )
        raw, page_token = [], None
        while True:
            url = base + (f"&page_token={page_token}" if page_token else "")
            data = _get(url, _alpaca_headers())
            raw.extend(data.get("bars", {}).get(symbol, []))
            page_token = data.get("next_page_token")
            if not page_token:
                break
        return [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]} for b in raw]
    else:
        # Equities via Polygon — key passed via params dict, never embedded in URL
        data = _poly(f"/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
                     {"adjusted": "true", "sort": "asc", "limit": 500})
        raw = data.get("results", [])
        return [{"t": r["t"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]} for r in raw]


def _poly(path: str, params: dict | None = None) -> dict:
    """GET a Polygon endpoint with API key injected. Stocks Advanced = ~9 req/s, no delay needed.

    Retries transient network failures (timeout / connection reset) up to 3 times
    with 2s, 4s backoff so one slow response doesn't kill a whole trade cycle.
    """
    poly_key = os.getenv("POLYGON_API_KEY", "")
    p = dict(params or {})
    p["apiKey"] = poly_key
    url = f"{_POLY_BASE}{path}"
    for attempt in range(3):
        try:
            resp = requests.get(url, params=p, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))  # 2s, then 4s


def get_intraday_bars(symbol: str, minutes: int = 5, limit: int = 20) -> list[dict]:
    """
    Fetch intraday OHLCV bars for current/last session from Polygon.
    Returns list of dicts: {t (epoch-ms), o, h, l, c, v}.
    minutes: candle size (1 or 5 recommended).
    Only for equities — use get_bars() with a short window for crypto.
    """
    from datetime import date, timedelta
    today = date.today().isoformat()
    since = (date.today() - timedelta(days=1)).isoformat()
    try:
        data = _poly(
            f"/v2/aggs/ticker/{symbol}/range/{minutes}/minute/{since}/{today}",
            {"adjusted": "true", "sort": "desc", "limit": limit},
        )
        results = data.get("results") or []
        return [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]}
                for b in results]
    except Exception:
        return []


def get_vwap_context(symbol: str) -> dict:
    """
    Returns current price vs session VWAP plus recent 5-min momentum.
    Used by execution agent for entry timing.
    Falls back to prevDay VWAP + lastTrade price pre-market / after-hours.
    {vwap, last_price, price_vs_vwap_pct, trend_5m, above_vwap, session}
    """
    try:
        raw  = _poly(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
        t    = raw.get("ticker", {})
        day  = t.get("day", {})
        prev = t.get("prevDay", {})
        lt   = t.get("lastTrade", {})
    except Exception:
        return {}

    # VWAP: use session VWAP if available, else previous session VWAP as proxy
    vwap    = day.get("vw") or 0
    session = "regular"
    if not vwap or vwap == 0:
        vwap    = prev.get("vw") or 0
        session = "pre/after-market"

    # Price: session close → lastTrade → prevDay close
    last = day.get("c") or lt.get("p") or prev.get("c")

    if not vwap or not last:
        return {}

    pct_vs_vwap = (last - vwap) / vwap * 100

    # 5-min candle trend: last 3 candles
    bars = get_intraday_bars(symbol, minutes=5, limit=4)
    trend = "neutral"
    if len(bars) >= 3:
        closes = [b["c"] for b in reversed(bars[:3])]   # oldest → newest
        if closes[-1] > closes[0]:
            trend = "up"
        elif closes[-1] < closes[0]:
            trend = "down"

    return {
        "vwap":              round(vwap, 2),
        "last_price":        round(last, 2),
        "price_vs_vwap_pct": round(pct_vs_vwap, 2),
        "above_vwap":        last >= vwap,
        "trend_5m":          trend,
        "session":           session,
    }


def get_snapshot(symbol: str) -> dict:
    """
    Intraday snapshot for an equity: change%, VWAP, volume, prevClose.
    Returns {} on error (market closed / no data yet).
    """
    try:
        data = _poly(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
        t    = data.get("ticker", {})
        day  = t.get("day", {})
        return {
            "symbol":     symbol,
            "change_pct": round(t.get("todaysChangePerc", 0), 2),
            "vwap":       day.get("vw"),
            "volume":     day.get("v"),
            "open":       day.get("o"),
            "high":       day.get("h"),
            "low":        day.get("l"),
            "close":      day.get("c"),
            "prev_close": t.get("prevDay", {}).get("c"),
        }
    except Exception:
        return {"symbol": symbol}


def get_news(symbol: str, limit: int = 5) -> list[dict]:
    """
    Recent news headlines for a symbol from Polygon.
    Returns list of {title, published_utc, description} dicts.
    """
    try:
        data    = _poly("/v2/reference/news", {"ticker": symbol, "limit": limit, "order": "desc"})
        results = data.get("results", [])
        return [
            {
                "title":     a.get("title", ""),
                "published": a.get("published_utc", "")[:16],
                "desc":      (a.get("description") or "")[:200],
            }
            for a in results
        ]
    except Exception:
        return []


def get_technicals(symbol: str) -> dict:
    """
    RSI(14) and MACD(12,26,9) from Polygon indicators — most recent daily value.
    Returns {} on error.
    """
    out = {}
    try:
        r   = _poly(f"/v1/indicators/rsi/{symbol}", {"timespan": "day", "window": 14, "limit": 1})
        vals = r.get("results", {}).get("values", [])
        if vals:
            out["rsi"] = round(vals[0]["value"], 1)
    except Exception:
        pass
    try:
        r    = _poly(f"/v1/indicators/macd/{symbol}", {"timespan": "day", "limit": 1})
        vals = r.get("results", {}).get("values", [])
        if vals:
            v = vals[0]
            out["macd"]      = round(v.get("value", 0), 3)
            out["macd_sig"]  = round(v.get("signal", 0), 3)
            out["macd_hist"] = round(v.get("histogram", 0), 3)
    except Exception:
        pass
    return out


def get_fear_greed() -> dict:
    """
    Crypto Fear & Greed index from alternative.me (free, no key).
    Returns {value: int, label: str}. Falls back gracefully on error.
    """
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()
        d = r["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except Exception:
        return {}


def get_top_movers(symbols: list[str], n: int = 8, days: int = 5) -> list[str]:
    """
    Return the top N symbols by absolute 5d price move (biggest movers — long or short).
    Always includes SPY and QQQ as macro anchors. Respects rate limits.
    """
    anchors = [s for s in ["SPY", "QQQ"] if s in symbols]
    rest    = [s for s in symbols if s not in anchors]

    moves = {}
    for sym in rest:
        try:
            bars = get_bars(sym, days=days + 5)
            if len(bars) >= 2:
                moves[sym] = abs(bars[-1]["c"] / bars[-5]["c"] - 1) if len(bars) >= 5 else 0
        except Exception:
            moves[sym] = 0

    top = sorted(moves, key=moves.get, reverse=True)[: max(0, n - len(anchors))]
    return anchors + top


_ET_TZ = timezone(timedelta(hours=-4), "ET")  # EDT fixed offset; sufficient for market-hours check


def _is_market_open_heuristic() -> bool:
    """Mon–Fri 09:30–16:00 ET. No holiday awareness — fallback only."""
    now_et = datetime.now(_ET_TZ)
    if now_et.weekday() >= 5:
        return False
    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now_et < market_close


def is_market_open() -> bool:
    """
    True if NYSE is currently open, per Alpaca's clock (knows holidays + half-days).
    Falls back to the weekday-window heuristic if the API is unreachable, so a
    network blip can't wedge the session selector.
    """
    try:
        return bool(_get(f"{_ALPACA_BASE}/v2/clock", _alpaca_headers()).get("is_open", False))
    except Exception:
        return _is_market_open_heuristic()


# ── CLI smoke test ────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Trading data layer smoke test")
    ap.add_argument("--symbol", default=None, help="Single symbol to test bars for")
    ap.add_argument("--days",   type=int, default=10)
    args = ap.parse_args()

    print("── Alpaca paper account ─────────────────────")
    acct = get_account()
    for k, v in acct.items():
        print(f"  {k:20s}: {v}")

    print(f"\n── Market open: {is_market_open()} ──────────────────────")

    symbols = [args.symbol] if args.symbol else ["SPY", "BTC/USD"]
    for sym in symbols:
        print(f"\n── {sym} bars (last {args.days}d) ───────────────────")
        try:
            bars = get_bars(sym, days=args.days)
            if bars:
                latest = bars[-1]
                print(f"  {len(bars)} bars   last close: {latest['c']}   ({latest['t']})")
            else:
                print("  ⚠️  No bars returned")
        except Exception as e:
            print(f"  ❌ {e}")

        print(f"\n── {sym} quote ──────────────────────────────")
        try:
            q = get_quote(sym)
            print(f"  bid={q['bid']}  ask={q['ask']}")
        except Exception as e:
            print(f"  ❌ {e}")


if __name__ == "__main__":
    main()
