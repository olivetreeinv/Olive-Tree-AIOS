#!/usr/bin/env python3
"""Compact tape read for the 5-minute analyst loop.

Usage: python3 watch.py [db_path]
Prints session stats, VWAP, exhaustion scores, recent fires, and the last
15 one-minute candles — everything needed to judge a top/downtrend at a glance.
"""
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spcx import config
from spcx.candles import CandleAggregator
from spcx.signals import BookSignalState, candle_exhaustion, composite_score

ET = ZoneInfo("America/New_York")


def hhmm(ts):
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else config.DB_PATH
    con = sqlite3.connect(db)
    row = con.execute("SELECT mode FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    mode = row[0] if row else "DEGRADED"
    trades = con.execute("SELECT ts, price, size FROM trades ORDER BY ts").fetchall()
    if not trades:
        print(f"NO TRADES RECORDED YET ({db}, mode {mode})")
        return

    first_ts, open_px, _ = trades[0]
    last_ts, last_px, _ = trades[-1]
    hi_ts, hi_px = max(((t, p) for t, p, _ in trades), key=lambda x: x[1])
    lo_px = min(p for _, p, _ in trades)
    vol_notional = sum(p * s for _, p, s in trades)
    vol_shares = sum(s for _, _, s in trades) or 1
    vwap = vol_notional / vol_shares
    off_high = (last_px / hi_px - 1) * 100
    off_ref = (last_px / config.IPO_REF_PRICE - 1) * 100

    fast = CandleAggregator(config.FAST_CANDLE_SEC, history_max=100000)
    slow = CandleAggregator(config.SLOW_CANDLE_SEC, history_max=100000)
    for ts, p, s in trades:
        fast.add(ts, p, s)
        slow.add(ts, p, s)
    candle_s, inputs = candle_exhaustion(fast.history)

    book_s = None
    if mode == "FULL":
        snaps = con.execute(
            "SELECT ts, bids, asks FROM book_snaps ORDER BY ts DESC LIMIT 40").fetchall()
        st = BookSignalState()
        px = last_px
        for ts, b, a in reversed(snaps):
            book_s, _ = st.update(ts, [tuple(x) for x in json.loads(b)],
                                  [tuple(x) for x in json.loads(a)], px)
    comp = composite_score(candle_s, book_s, mode)

    cutoff = last_ts - 20 * 60
    fires = con.execute(
        "SELECT ts, kind, score, price FROM signals WHERE ts >= ? ORDER BY ts",
        (cutoff,)).fetchall()
    con.close()

    age = time.time() - last_ts
    print(f"{config.SYMBOL}  last {last_px:.2f} ({age:.0f}s ago)  "
          f"ref {config.IPO_REF_PRICE:g} ({off_ref:+.1f}%)  VWAP {vwap:.2f} "
          f"({'above' if last_px >= vwap else 'BELOW'})  mode {mode}")
    print(f"session: open {open_px:.2f}@{hhmm(first_ts)}  "
          f"high {hi_px:.2f}@{hhmm(hi_ts)} ({off_high:+.1f}% off high)  low {lo_px:.2f}")
    print(f"scores: candle {candle_s:.2f}  "
          f"book {'-' if book_s is None else f'{book_s:.2f}'}  composite {comp:.2f}")
    print(f"components: {inputs}")
    if fires:
        print("fires last 20m:")
        for ts, kind, score, price in fires:
            sc = "-" if score is None else f"{score:.2f}"
            print(f"  {hhmm(ts)}  {kind:<10} {sc}  @ {price:.2f}")
    else:
        print("fires last 20m: none")
    print("1m candles (last 15):")
    for c in slow.history[-15:]:
        d = "+" if c["c"] >= c["o"] else "-"
        print(f"  {hhmm(c['ts'])}  o{c['o']:.2f} h{c['h']:.2f} l{c['l']:.2f} "
              f"c{c['c']:.2f} v{c['v']:,} {d}")


if __name__ == "__main__":
    main()
