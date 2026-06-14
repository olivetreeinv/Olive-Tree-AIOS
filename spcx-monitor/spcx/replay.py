"""Replay eval — re-run the exact live signal logic over a recorded session and
score each signal against realized local maxima.

Usage:
  python -m spcx.replay --db data/spcx.db [--forward 60] [--drop 1.5]
                        [--thr-candle 0.7] [--thr-book 0.7] [--thr-composite 0.75]

A "realized peak" is a candle high that is the max of its +/-3-candle
neighborhood AND is followed by a >= --drop % decline within --forward seconds.

Scoring (decision-relevant — exhaustion signals confirm tops, so they often
fire just AFTER the absolute high, which is still exactly when you want the
alert):
  precision — fires where price actually fell >= --drop % from the FIRE price
              within --forward seconds (the alert was worth acting on).
  recall    — peaks that had a fire within +/- --forward seconds.
  mean lead — peak ts minus fire ts for fires near a peak; NEGATIVE lead means
              the signal confirmed after the top (typical for candle signals).

Candle / book / composite are scored separately; book is evaluated only for
FULL-mode sessions.
"""
import argparse
import json
import sqlite3

from . import config
from .candles import CandleAggregator
from .signals import BookSignalState, candle_exhaustion, composite_score


def load(db_path):
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT mode FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    mode = row[0] if row else "DEGRADED"
    trades = con.execute("SELECT ts, price, size FROM trades ORDER BY ts").fetchall()
    snaps = con.execute("SELECT ts, bids, asks FROM book_snaps ORDER BY ts").fetchall()
    con.close()
    return mode, trades, snaps


def build_scores(mode, trades, snaps):
    """Mirror the live engine: candle score at each 10s close, book score at each
    1s snapshot, composite at every evaluation point. Returns (series, candles)."""
    agg = CandleAggregator(config.FAST_CANDLE_SEC, history_max=100000)
    book_state = BookSignalState()
    events = [(ts, 0, (price, size)) for ts, price, size in trades]
    events += [(ts, 1, (b, a)) for ts, b, a in snaps]
    events.sort(key=lambda e: (e[0], e[1]))
    series = {"candle": [], "book": [], "composite": []}
    candle_s, book_s, last_price = 0.0, None, None
    for ts, etype, payload in events:
        if etype == 0:  # trade
            price, size = payload
            last_price = price
            closed = agg.add(ts, price, size)
            if closed:
                candle_s, _ = candle_exhaustion(agg.history)
                series["candle"].append((ts, candle_s, price))
                series["composite"].append(
                    (ts, composite_score(candle_s, book_s, mode), price))
        elif mode == "FULL":  # book snapshot
            bids = [tuple(x) for x in json.loads(payload[0])]
            asks = [tuple(x) for x in json.loads(payload[1])]
            book_s, _ = book_state.update(ts, bids, asks, last_price)
            if last_price is not None:
                series["book"].append((ts, book_s, last_price))
                series["composite"].append(
                    (ts, composite_score(candle_s, book_s, mode), last_price))
    return series, agg.history


def extract_fires(series, thr, cooldown=config.SIGNAL_COOLDOWN_SEC):
    """Same dedupe as the live AlertManager: fire when score >= thr, then hold
    the cooldown regardless of score path."""
    fires, last = [], None
    for ts, score, price in series:
        if score >= thr and (last is None or ts - last >= cooldown):
            fires.append((ts, score, price))
            last = ts
    return fires


def find_peaks(candles, forward_sec, drop_pct, w=3):
    peaks = []
    for i in range(w, len(candles) - 1):
        c = candles[i]
        lo, hi = max(0, i - w), min(len(candles), i + w + 1)
        if c["h"] < max(x["h"] for x in candles[lo:hi]):
            continue
        future = [x for x in candles[i + 1:] if x["ts"] <= c["ts"] + forward_sec]
        if not future or min(x["l"] for x in future) > c["h"] * (1 - drop_pct / 100):
            continue
        # collapse peaks closer than 2w candles, keep the higher one
        if peaks and c["ts"] - peaks[-1]["ts"] < 2 * w * config.FAST_CANDLE_SEC:
            if c["h"] > peaks[-1]["price"]:
                peaks[-1] = {"ts": c["ts"], "price": c["h"]}
            continue
        peaks.append({"ts": c["ts"], "price": c["h"]})
    return peaks


def score_fires(fires, peaks, candles, forward_sec, drop_pct):
    tp, leads = 0, []
    for ts, _score, price in fires:
        lows = [c["l"] for c in candles if ts < c["ts"] <= ts + forward_sec]
        if lows and min(lows) <= price * (1 - drop_pct / 100):
            tp += 1
        near = [p for p in peaks if abs(p["ts"] - ts) <= forward_sec]
        if near:
            leads.append(min(near, key=lambda p: abs(p["ts"] - ts))["ts"] - ts)
    matched = sum(1 for p in peaks
                  if any(abs(p["ts"] - f[0]) <= forward_sec for f in fires))
    return {
        "fires": len(fires),
        "tp": tp,
        "precision": tp / len(fires) if fires else None,
        "recall": matched / len(peaks) if peaks else None,
        "mean_lead_sec": sum(leads) / len(leads) if leads else None,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Replay a recorded SPCX session and score the signals.")
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--forward", type=float, default=60,
                    help="forward window in seconds for peak matching (default 60)")
    ap.add_argument("--drop", type=float, default=1.5,
                    help="min %% drop after a high to count as a peak (default 1.5)")
    ap.add_argument("--thr-candle", type=float, default=config.CANDLE_THRESHOLD)
    ap.add_argument("--thr-book", type=float, default=config.BOOK_THRESHOLD)
    ap.add_argument("--thr-composite", type=float,
                    default=config.COMPOSITE_ALERT_THRESHOLD)
    args = ap.parse_args()

    mode, trades, snaps = load(args.db)
    if not trades:
        print("No trades recorded — nothing to replay.")
        return
    series, candles = build_scores(mode, trades, snaps)
    peaks = find_peaks(candles, args.forward, args.drop)

    print(f"SPCX replay — session mode {mode}: {len(trades)} trades, "
          f"{len(candles)} closed 10s candles, {len(peaks)} realized peaks")
    print(f"peak = local max (+/-3 candles) that drops >= {args.drop}% "
          f"within {args.forward:.0f}s\n")
    print(f"{'signal':<11}{'fires':>6}{'TP':>5}{'precision':>11}{'recall':>8}{'mean lead':>11}")

    def cell(v, suffix=""):
        return "-" if v is None else f"{v:.2f}{suffix}"

    for kind, thr in (("candle", args.thr_candle), ("book", args.thr_book),
                      ("composite", args.thr_composite)):
        if kind == "book" and (mode != "FULL" or not snaps):
            print(f"{kind:<11}skipped — DEGRADED session, no book data recorded")
            continue
        r = score_fires(extract_fires(series[kind], thr), peaks, candles,
                        args.forward, args.drop)
        lead = "-" if r["mean_lead_sec"] is None else f"{r['mean_lead_sec']:.1f}s"
        print(f"{kind:<11}{r['fires']:>6}{r['tp']:>5}"
              f"{cell(r['precision']):>11}{cell(r['recall']):>8}{lead:>11}")


if __name__ == "__main__":
    main()
