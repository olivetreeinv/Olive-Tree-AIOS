#!/usr/bin/env python3
"""
data_compare.py — Polygon vs Alpaca head-to-head for the trading desk.

Runs LOCALLY (both feeds are blocked in the cloud sandbox). Each capture pulls
the SAME symbols from both Polygon and Alpaca and logs real-time price, VWAP,
and quote spread so we can answer: is Alpaca (Plus/SIP) good enough to replace
Polygon and save $100/mo?

Capture intraday (several times during market hours) for a week, then --report.

Usage:
  python3 scripts/data_compare.py --capture                 # one real-time snapshot of all symbols
  python3 scripts/data_compare.py --capture --gate          # also log gate agreement (slow; run once/day)
  python3 scripts/data_compare.py --report                  # summarize captures → verdict
  python3 scripts/data_compare.py --loop --interval 1800    # capture every 30 min (wrap with caffeinate)
  python3 scripts/data_compare.py --test                    # self-check the diff math

Alpaca feed: set ALPACA_DATA_FEED=sip in .env once Algo Trader Plus is active
(default 'iex' on the free tier). SIP is the apples-to-apples vs Polygon.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.trading_data import _poly, _get, _ALPACA_DATA, _alpaca_headers


def _alpaca_stock_bars(symbol: str, start, end, timeframe: str = "1Day") -> list[dict]:
    """Daily equity bars via Alpaca (self-contained so this runs regardless of branch)."""
    url = (f"{_ALPACA_DATA}/v2/stocks/{symbol}/bars"
           f"?timeframe={timeframe}&start={start}&end={end}&limit=1000&adjustment=split&feed={FEED}")
    raw = _get(url, _alpaca_headers()).get("bars", []) or []
    return [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]} for b in raw]

OUT_DIR  = Path(__file__).parent.parent / "output" / "data_compare"
CAP_CSV  = OUT_DIR / "captures.csv"
GATE_CSV = OUT_DIR / "gate.csv"
FEED     = os.getenv("ALPACA_DATA_FEED", "iex")   # 'sip' once Alpaca Plus is active

# Broad, liquid universe screened each morning to PICK the day's best trades.
BROAD_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "MU", "AMAT", "LRCX", "KLAC", "MRVL",
    "QCOM", "TXN", "ARM", "SMCI", "PLTR", "ORCL", "CRM", "NOW", "PANW", "CRWD",
    "SNOW", "ADBE", "NFLX", "DELL", "AMZN", "GOOGL", "META", "TSLA", "UBER",
    "ABNB", "BKNG", "COST", "WMT", "HD", "MCD", "SBUX", "DIS", "JPM", "GS", "MS",
    "BAC", "V", "MA", "AXP", "LLY", "UNH", "ABBV", "ISRG", "XOM", "CVX", "COP",
    "CAT", "GE", "COIN", "MSTR", "SOFI", "SHOP", "IONQ", "UFO", "SMH", "XLE", "XLF",
]
ANCHORS = ["SPY", "QQQ"]          # always compared (benchmark + macro reference)
TOP_N   = 18                       # cap the day's tradeable set
# Fallback if the morning screen can't run (e.g. data hiccup at open).
DEFAULT_SYMBOLS = ANCHORS + ["NVDA", "AMD", "AMAT", "LRCX", "MU", "AAPL", "MSFT",
                             "META", "JPM", "GS", "UNH", "CAT"]


def _pick_daily_symbols() -> list[str]:
    """The day's best tradeable names: broad gate screen → survivors by Sharpe → top N,
    plus benchmark anchors. Cached once per day so the 30-min captures reuse the set."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = OUT_DIR / f"symbols_{date.today().isoformat()}.json"
    if cache.exists():
        import json
        return json.loads(cache.read_text())
    import json
    # Two-sided: best longs AND best shorts (shared source of truth with daily_scan).
    from scripts.daily_scan import daily_symbols
    try:
        syms = daily_symbols(top=TOP_N // 2, anchors=tuple(ANCHORS))
    except Exception:
        syms = []
    if len(syms) <= len(ANCHORS):       # screen produced nothing usable
        syms = DEFAULT_SYMBOLS
    cache.write_text(json.dumps(syms))
    print(f"  🎯 Day's best tradeable set ({len(syms)}): {', '.join(syms)}")
    return syms

CAP_COLS = ["ts", "symbol", "poly_price", "alp_price", "price_diff_bps",
            "poly_vwap", "alp_vwap", "vwap_diff_bps",
            "poly_spread_bps", "alp_spread_bps", "poly_ok", "alp_ok"]
GATE_COLS = ["ts", "symbol", "poly_pass", "poly_sharpe", "poly_trades",
             "alp_pass", "alp_sharpe", "alp_trades", "agree"]


def _bps(a: float, b: float) -> float:
    """Difference of a vs b in basis points of b. None-safe → ''."""
    if not a or not b:
        return ""
    return round((a - b) / b * 10000, 1)


def _polygon_snapshot(symbol: str) -> dict:
    """Polygon real-time: last price, day VWAP, bid/ask. {} on failure."""
    try:
        t = _poly(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}").get("ticker", {})
        lq = t.get("lastQuote", {})
        bid, ask = lq.get("p"), lq.get("P")   # Polygon: p=bid, P=ask
        return {
            "price":  t.get("lastTrade", {}).get("p") or t.get("day", {}).get("c"),
            "vwap":   t.get("day", {}).get("vw"),
            "spread_bps": _bps(ask, bid) if (bid and ask) else "",
        }
    except Exception:
        return {}


def _alpaca_snapshot(symbol: str) -> dict:
    """Alpaca real-time (feed=iex|sip): last price, daily VWAP, bid/ask. {} on failure."""
    try:
        d = _get(f"{_ALPACA_DATA}/v2/stocks/{symbol}/snapshot?feed={FEED}", _alpaca_headers())
        lq = d.get("latestQuote", {})
        bid, ask = lq.get("bp"), lq.get("ap")
        return {
            "price":  (d.get("latestTrade", {}) or {}).get("p") or (d.get("dailyBar", {}) or {}).get("c"),
            "vwap":   (d.get("dailyBar", {}) or {}).get("vw"),
            "spread_bps": _bps(ask, bid) if (bid and ask) else "",
        }
    except Exception:
        return {}


def capture(symbols: list[str], force: bool = False) -> int:
    if not force:
        from scripts.trading_data import is_market_open
        if not is_market_open():
            print("  Market closed — skipping capture (real-time diffs only matter intraday; use --force to override).")
            return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    new = not CAP_CSV.exists()
    ts = datetime.now(timezone.utc).isoformat()
    n = 0
    with CAP_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CAP_COLS)
        for sym in symbols:
            p = _polygon_snapshot(sym)
            a = _alpaca_snapshot(sym)
            w.writerow([
                ts, sym, p.get("price", ""), a.get("price", ""),
                _bps(p.get("price"), a.get("price")),
                p.get("vwap", ""), a.get("vwap", ""),
                _bps(p.get("vwap"), a.get("vwap")),
                p.get("spread_bps", ""), a.get("spread_bps", ""),
                int(bool(p)), int(bool(a)),
            ])
            n += 1
    print(f"  📸 Captured {n} symbols at {ts}  (Alpaca feed={FEED}) → {CAP_CSV}")
    return n


def capture_gate(symbols: list[str]) -> int:
    """Daily: does the quant gate make the same call on Polygon vs Alpaca bars?"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    if GATE_CSV.exists():
        if any(r.get("ts", "").startswith(today) for r in csv.DictReader(GATE_CSV.open())):
            return 0   # already logged today — skip the backtests
    import scripts.trading_quant as q
    orig = q.get_bars
    end = date.today(); start = end - timedelta(days=375)

    def poly_bars(symbol, days=60, timeframe="1Day"):
        data = _poly(f"/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
                     {"adjusted": "true", "sort": "asc", "limit": 500})
        return [{"t": r["t"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]}
                for r in data.get("results", [])]

    def alp_bars(symbol, days=60, timeframe="1Day"):
        return _alpaca_stock_bars(symbol, start, end, timeframe)

    new = not GATE_CSV.exists()
    ts = datetime.now(timezone.utc).isoformat()
    n = 0
    try:
        with GATE_CSV.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(GATE_COLS)
            for sym in symbols:
                try:
                    q.get_bars = poly_bars
                    rp = q.run_walk_forward(sym, days=365)
                    q.get_bars = alp_bars
                    ra = q.run_walk_forward(sym, days=365)
                except Exception:
                    continue
                op, oa = rp.get("oos", {}), ra.get("oos", {})
                if "n_trades" not in op or "n_trades" not in oa:
                    continue
                pp, pa = rp["passed_gate"], ra["passed_gate"]
                w.writerow([ts, sym, int(pp), round(op["sharpe"], 2), op["n_trades"],
                            int(pa), round(oa["sharpe"], 2), oa["n_trades"], int(pp == pa)])
                n += 1
    finally:
        q.get_bars = orig
    print(f"  🧮 Gate comparison logged for {n} symbols → {GATE_CSV}")
    return n


def _mean(xs):
    xs = [x for x in xs if x != "" and x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def report() -> None:
    if not CAP_CSV.exists():
        print("  No captures yet. Run --capture during market hours first.")
        return
    rows = list(csv.DictReader(CAP_CSV.open()))
    n_caps = len({r["ts"] for r in rows})
    print(f"\n══ Polygon vs Alpaca (feed={FEED}) — {len(rows)} rows across {n_caps} capture(s) ══\n")

    # Per-symbol: avg |price diff|, |vwap diff|, spread each, and data availability
    syms = sorted({r["symbol"] for r in rows})
    print(f'{"SYM":6}{"|price Δ|bps":>13}{"|vwap Δ|bps":>12}{"polySprd":>9}{"alpSprd":>9}{"alp miss":>9}')
    tot_price, tot_vwap = [], []
    for s in syms:
        rs = [r for r in rows if r["symbol"] == s]
        pdiff = _mean([abs(float(r["price_diff_bps"])) for r in rs if r["price_diff_bps"] != ""])
        vdiff = _mean([abs(float(r["vwap_diff_bps"])) for r in rs if r["vwap_diff_bps"] != ""])
        psp = _mean([float(r["poly_spread_bps"]) for r in rs if r["poly_spread_bps"] != ""])
        asp = _mean([float(r["alp_spread_bps"]) for r in rs if r["alp_spread_bps"] != ""])
        miss = sum(1 for r in rs if r["alp_ok"] == "0")
        tot_price.append(pdiff); tot_vwap.append(vdiff)
        print(f"{s:6}{pdiff:>13.1f}{vdiff:>12.1f}{psp:>9.1f}{asp:>9.1f}{miss:>9}")

    print(f"\n  Avg |price diff|: {_mean(tot_price):.1f} bps   Avg |VWAP diff|: {_mean(tot_vwap):.1f} bps")
    print("  (1 bp = 0.01%. Price diff <~5bps and VWAP <~10bps ≈ feeds agree → Alpaca can replace Polygon.)")

    if GATE_CSV.exists():
        g = list(csv.DictReader(GATE_CSV.open()))
        if g:
            agree = sum(int(r["agree"]) for r in g) / len(g) * 100
            print(f"\n  Gate agreement (same buy/skip call): {agree:.0f}%  over {len(g)} symbol-days")
    print()


def _selfcheck():
    assert _bps(101, 100) == 100.0, "1% should be 100 bps"
    assert _bps(100, 100) == 0.0
    assert _bps(0, 100) == "" and _bps(100, 0) == ""   # None-safe
    print("  ✅ data_compare self-check passed.")


def main():
    ap = argparse.ArgumentParser(description="Polygon vs Alpaca data comparison")
    ap.add_argument("--capture", action="store_true", help="One real-time snapshot of all symbols")
    ap.add_argument("--gate", action="store_true", help="Also log gate agreement (use with --capture; slow)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--loop", action="store_true", help="Capture repeatedly (wrap with caffeinate -i)")
    ap.add_argument("--interval", type=int, default=1800, help="Loop seconds (default 1800 = 30 min)")
    ap.add_argument("--symbols", nargs="+", help="Override symbol list")
    ap.add_argument("--force", action="store_true", help="Capture even when market is closed")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    if args.test:
        _selfcheck(); return
    if args.report:
        report(); return

    def _open() -> bool:
        from scripts.trading_data import is_market_open
        return args.force or is_market_open()

    def _do_capture():
        # Pick the day's best names only when actually capturing (avoids running the
        # broad screen off-hours). _pick_daily_symbols caches per day.
        syms = args.symbols or _pick_daily_symbols()
        got = capture(syms, force=args.force)
        if got and args.gate:
            capture_gate(syms)

    if args.loop:
        print(f"  Looping capture every {args.interval}s. Ctrl-C to stop.")
        while True:
            try:
                if _open():
                    _do_capture()
                else:
                    print("  Market closed — skipping capture.")
            except KeyboardInterrupt:
                print("\n  Stopped."); break
            except Exception as e:
                print(f"  ⚠️  {e}")
            time.sleep(args.interval)
        return

    if args.capture:
        if _open():
            _do_capture()
        else:
            print("  Market closed — skipping capture (use --force to override).")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
