#!/usr/bin/env python3
"""
trading_data.py — shared data layer for the Olive Tree Trading Desk.

Provides:
  - UNIVERSE: ~25 liquid US large-caps/ETFs + BTC/ETH for overnight
  - get_bars()          : historical OHLCV, all from Alpaca (equities: SIP feed, crypto: crypto/us)
  - get_quote()         : latest bid/ask/last from Alpaca
  - get_account()       : Alpaca paper account summary
  - get_snapshot()      : intraday change%, VWAP, volume from Alpaca snapshot
  - get_news()          : recent headlines from Alpaca news API
  - get_technicals()    : RSI + MACD computed locally from Alpaca daily bars
  - get_fear_greed()    : Crypto Fear & Greed index (alternative.me, free)
  - get_top_movers()    : filter universe to top N by absolute 5d move
  - is_market_open()    : NYSE market hours check (no API call)

Equities use ALPACA_DATA_FEED (default "sip") — set to "iex" if the account
lacks the SIP add-on. Alpaca is the sole market-data source (see
archives/data-compare-2026-07/ for the retired-vendor comparison writeup).

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
_SP500_FILE = Path(__file__).parent.parent / "data" / "sp500.txt"

def _load_sp500() -> list[str]:
    # SPY + QQQ are ETFs (not S&P 500 members) but kept as market anchors
    anchors = ["SPY", "QQQ"]
    if _SP500_FILE.exists():
        sp500 = [l.strip() for l in _SP500_FILE.read_text().splitlines() if l.strip()]
        return anchors + [s for s in sp500 if s not in anchors]
    # ponytail: fallback to legacy list if file missing; run scripts/trading_data.py --refresh-sp500
    return anchors + [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
        "BRK.B", "JPM", "V", "UNH", "XOM", "AMD", "NFLX", "CRM", "ADBE",
        "IWM", "GLD", "TLT",
    ]

EQUITY_UNIVERSE = _load_sp500()  # S&P 500 constituents + SPY/QQQ anchors; refresh with --refresh-sp500

# ── Top-rated ETFs — always evaluated alongside the day's S&P movers ─────────
# Only the 6 that clear the walk-forward gate on a 730d window (verified 2026-07-01):
# small-cap (IWM), broad (VTI), dividend (SCHD), growth (VUG), tech (XLK), gold (GLD).
# ETFs need the 730d window in the orchestrator — at 365d they fire too few trades.
# SPY removed: core sweep module owns SPY going forward (idle-cash benchmark position).
ETF_UNIVERSE = ["IWM", "VTI", "SCHD", "VUG", "XLK", "GLD"]

# ── Crypto universe (traded 24/7, active overnight when equities are closed) ─
CRYPTO_UNIVERSE = ["BTC/USD", "ETH/USD"]  # SOL removed; overnight crypto session retired

UNIVERSE = EQUITY_UNIVERSE + CRYPTO_UNIVERSE

# ── Alpaca REST helpers (stdlib only — no alpaca-py dep here so scripts can
#    import this module without the full SDK installed in restricted envs) ────
_ALPACA_BASE  = "https://paper-api.alpaca.markets"
_ALPACA_DATA  = "https://data.alpaca.markets"


def _data_feed() -> str:
    return os.getenv("ALPACA_DATA_FEED", "sip")

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
    # ponytail: 3 attempts, 2s/4s backoff — one slow response shouldn't kill a trade cycle
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=_SSL, timeout=15) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def get_account() -> dict:
    """Return Alpaca paper account fields as a dict."""
    data = _get(f"{_ALPACA_BASE}/v2/account", _alpaca_headers())
    return {
        "status":        data.get("status"),
        "equity":        float(data.get("equity", 0)),
        "last_equity":   float(data.get("last_equity", data.get("equity", 0))),
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
    Return OHLCV bars as list of dicts with keys: t (ISO string), o, h, l, c, v.
    All from Alpaca — equities via the SIP feed (ALPACA_DATA_FEED), crypto via crypto/us.
    """
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days + 10)   # buffer for weekends/holidays

    if "/" in symbol:
        # Crypto — paginate; one page caps at 1000 bars (hourly over weeks exceeds that)
        sym_enc = symbol.replace("/", "%2F")
        base = (
            f"{_ALPACA_DATA}/v1beta3/crypto/us/bars"
            f"?symbols={sym_enc}&timeframe={timeframe}"
            f"&start={start}&end={end}&limit=1000"
        )
    else:
        base = (
            f"{_ALPACA_DATA}/v2/stocks/bars"
            f"?symbols={symbol}&timeframe={timeframe}"
            f"&start={start}&end={end}&limit=10000&feed={_data_feed()}&adjustment=raw"
        )

    raw, page_token, page = [], None, 0
    while page < 20:  # ponytail: 20 pages guard against a runaway loop
        url = base + (f"&page_token={page_token}" if page_token else "")
        data = _get(url, _alpaca_headers())
        raw.extend(data.get("bars", {}).get(symbol, []))
        page_token = data.get("next_page_token")
        page += 1
        if not page_token:
            break
    return [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]} for b in raw]


def _alpaca_snapshots(symbols: list[str]) -> dict:
    """Bulk stock snapshots from Alpaca, chunked to stay well under URL length limits."""
    out = {}
    syms = sorted(symbols)
    for i in range(0, len(syms), 100):
        chunk = syms[i:i + 100]
        url = f"{_ALPACA_DATA}/v2/stocks/snapshots?symbols={','.join(chunk)}&feed={_data_feed()}"
        data = _get(url, _alpaca_headers()) or {}
        out.update(data)
    return out


def get_intraday_bars(symbol: str, minutes: int = 5, limit: int = 20) -> list[dict]:
    """
    Fetch intraday OHLCV bars for current/last session from Alpaca.
    Returns list of dicts: {t (ISO string), o, h, l, c, v}, most recent first.
    minutes: candle size (1 or 5 recommended).
    Only for equities — use get_bars() with a short window for crypto.
    """
    from datetime import date, timedelta
    today = date.today().isoformat()
    since = (date.today() - timedelta(days=1)).isoformat()
    try:
        url = (
            f"{_ALPACA_DATA}/v2/stocks/bars?symbols={symbol}&timeframe={minutes}Min"
            f"&start={since}&end={today}&limit={limit}&feed={_data_feed()}&sort=desc"
        )
        data = _get(url, _alpaca_headers())
        results = data.get("bars", {}).get(symbol, []) or []
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
        raw  = _get(f"{_ALPACA_DATA}/v2/stocks/{symbol}/snapshot?feed={_data_feed()}", _alpaca_headers())
        day  = raw.get("dailyBar") or {}
        prev = raw.get("prevDailyBar") or {}
        lt   = raw.get("latestTrade") or {}
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
        data = _get(f"{_ALPACA_DATA}/v2/stocks/{symbol}/snapshot?feed={_data_feed()}", _alpaca_headers())
        day  = data.get("dailyBar") or {}
        prev = data.get("prevDailyBar") or {}
        c, pc = day.get("c"), prev.get("c")
        return {
            "symbol":     symbol,
            "change_pct": round((c - pc) / pc * 100, 2) if c and pc else 0,
            "vwap":       day.get("vw"),
            "volume":     day.get("v"),
            "open":       day.get("o"),
            "high":       day.get("h"),
            "low":        day.get("l"),
            "close":      c,
            "prev_close": pc,
        }
    except Exception:
        return {"symbol": symbol}


def get_news(symbol: str, limit: int = 5) -> list[dict]:
    """
    Recent news headlines for a symbol from Alpaca's news API.
    Returns list of {title, published, desc} dicts.
    """
    try:
        url = f"{_ALPACA_DATA}/v1beta1/news?symbols={symbol}&limit={limit}&sort=desc"
        data    = _get(url, _alpaca_headers())
        results = data.get("news", [])
        return [
            {
                "title":     a.get("headline", ""),
                "published": (a.get("created_at") or "")[:16],
                "desc":      (a.get("summary") or "")[:200],
            }
            for a in results
        ]
    except Exception:
        return []


def _ema_series(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def get_technicals(symbol: str) -> dict:
    """
    RSI(14) and MACD(12,26,9), computed locally from Alpaca daily closes
    (Alpaca has no indicators endpoint). Returns {} on error / thin history.
    """
    out = {}
    try:
        closes = [b["c"] for b in get_bars(symbol, days=90)]
        if len(closes) < 27:
            return {}

        # RSI(14), Wilder smoothing
        deltas   = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains    = [max(d, 0) for d in deltas]
        losses   = [max(-d, 0) for d in deltas]
        avg_gain = sum(gains[:14]) / 14
        avg_loss = sum(losses[:14]) / 14
        for g, l in zip(gains[14:], losses[14:]):
            avg_gain = (avg_gain * 13 + g) / 14
            avg_loss = (avg_loss * 13 + l) / 14
        rs = avg_gain / avg_loss if avg_loss else float("inf")
        out["rsi"] = round(100 - (100 / (1 + rs)), 1)

        # MACD(12,26,9)
        macd_line   = [a - b for a, b in zip(_ema_series(closes, 12), _ema_series(closes, 26))]
        signal_line = _ema_series(macd_line, 9)
        out["macd"]      = round(macd_line[-1], 3)
        out["macd_sig"]  = round(signal_line[-1], 3)
        out["macd_hist"] = round(macd_line[-1] - signal_line[-1], 3)
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


def get_top_movers(symbols: list[str], n: int = 15, days: int = 5) -> list[str]:
    """
    Return the top N symbols by absolute 1d price move using Alpaca's bulk
    snapshot endpoint (chunked at 100 symbols/call) instead of one call per
    symbol. Always includes SPY and QQQ as macro anchors.
    """
    anchors = [s for s in ["SPY", "QQQ"] if s in symbols]
    sym_set = set(symbols) - set(anchors)

    try:
        snaps = _alpaca_snapshots(list(sym_set))
        moves = {}
        for sym, snap in snaps.items():
            day  = (snap or {}).get("dailyBar") or {}
            prev = (snap or {}).get("prevDailyBar") or {}
            c, pc = day.get("c"), prev.get("c")
            if c and pc:
                moves[sym] = abs(c / pc - 1)
    except Exception:
        # ponytail: fallback to legacy per-symbol scan if snapshot call fails
        moves = {}
        for sym in sym_set:
            try:
                bars = get_bars(sym, days=days + 5)
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


def is_extended_hours() -> bool:
    """True if current time is in the after-hours window: 4:00pm–8:00pm ET, Mon–Fri."""
    now_et = datetime.now(_ET_TZ)
    if now_et.weekday() >= 5:
        return False
    ah_start = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    ah_end   = now_et.replace(hour=20, minute=0, second=0, microsecond=0)
    return ah_start <= now_et < ah_end


def get_afterhours_movers(symbols: list[str], n: int = 15) -> list[str]:
    """
    Return top N S&P 500 stocks by absolute after-hours price move via Alpaca's
    bulk snapshot endpoint. Compares latestTrade.price vs dailyBar.close — the
    gap is the after-hours move.
    """
    anchors = [s for s in ["SPY", "QQQ"] if s in symbols]
    sym_set = set(symbols) - set(anchors)
    try:
        snaps = _alpaca_snapshots(list(sym_set))
        moves = {}
        for sym, snap in snaps.items():
            day_close = ((snap or {}).get("dailyBar") or {}).get("c", 0)
            ah_price  = ((snap or {}).get("latestTrade") or {}).get("p", 0)
            if day_close and ah_price:
                moves[sym] = abs(ah_price / day_close - 1)
        top = sorted(moves, key=moves.get, reverse=True)[: max(0, n - len(anchors))]
        return anchors + top
    except Exception:
        return get_top_movers(symbols, n=n)  # ponytail: fallback if snapshot fails


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
