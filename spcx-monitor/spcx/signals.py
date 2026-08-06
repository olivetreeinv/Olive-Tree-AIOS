"""Signal logic shared by the live engine and replay eval — keep them identical."""
from . import config


def _clip01(x):
    return max(0.0, min(1.0, x))


def rsi(closes, period=14):
    """Wilder-smoothed RSI over the whole series; None until period+1 closes."""
    if len(closes) < period + 1:
        return None
    avg_gain = avg_loss = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        avg_gain += max(d, 0.0)
        avg_loss += max(-d, 0.0)
    avg_gain /= period
    avg_loss /= period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _components(candles):
    """Instantaneous exhaustion components for the latest candle close."""
    n = len(candles)
    closes = [c["c"] for c in candles]
    highs = [c["h"] for c in candles]

    r_now = rsi(closes)
    r_prev = rsi(closes[:-1])
    if r_now is None or r_prev is None:
        rsi_c = 0.0
    elif r_prev > 70 and r_now <= 70:
        rsi_c = 1.0          # overbought cross-down
    elif r_now > 70 and r_now < r_prev:
        rsi_c = 0.5          # overbought and rolling
    else:
        rsi_c = 0.0

    k = config.ROC_PERIOD
    rocs = None
    roc_c = 0.0
    if n >= k + 3:
        rocs = [closes[i] / closes[i - k] - 1 for i in (-3, -2, -1)]  # oldest -> newest
        if rocs[0] > 0 and rocs[2] < rocs[1] < rocs[0]:
            roc_c = 1.0      # momentum was positive, two straight declines
        elif rocs[1] > 0 and rocs[2] < rocs[1]:
            roc_c = 0.6

    # "There was a run in the window" — measured peak-vs-start so an unfolding
    # retracement doesn't kill the lower-high component right when it matters.
    run_w = min(config.RUN_WINDOW, n - 1)
    run_gain = max(highs[-run_w:]) / closes[-1 - run_w] - 1
    in_run = run_gain >= config.RUN_MIN_GAIN
    swings = [highs[i] for i in range(1, n - 1)
              if highs[i] >= highs[i - 1] and highs[i] >= highs[i + 1]]
    lower_high = bool(in_run and len(swings) >= 2 and swings[-1] < swings[-2])
    lh_c = 1.0 if lower_high else 0.0

    recent_up = [c["v"] for c in candles[-6:] if c["c"] > c["o"]]
    prior_up = [c["v"] for c in candles[-12:-6] if c["c"] > c["o"]]
    vol_ratio = None
    vol_c = 0.0
    if recent_up and prior_up:
        prior_avg = sum(prior_up) / len(prior_up)
        if prior_avg > 0:
            vol_ratio = (sum(recent_up) / len(recent_up)) / prior_avg
            vol_c = _clip01((1.0 - vol_ratio) / 0.5)  # 30%+ fade maxes out

    comps = {"rsi_c": rsi_c, "roc_c": roc_c, "lh_c": lh_c, "vol_c": vol_c}
    inputs = {
        "rsi": r_now, "rsi_prev": r_prev,
        "roc": rocs,
        "run_gain": round(run_gain, 5), "in_run": in_run,
        "lower_high": lower_high,
        "vol_ratio": None if vol_ratio is None else round(vol_ratio, 3),
    }
    return comps, inputs


def candle_exhaustion(candles):
    """0-1 score that an up-move is exhausting.

    candles: closed candles (dicts with o/h/l/c/v), oldest -> newest.
    Components: RSI>70 cross-down, ROC momentum rollover, lower-high after a
    run, fading volume on up-candles. Each component is one-candle events by
    nature, so it persists as a decayed max over the last COMPONENT_MEMORY
    closes — components that fire within ~a minute of each other stack instead
    of blinking past each other. Stateless (pure function of history), so live
    and replay score identically. Returns (score, raw inputs).
    """
    n = len(candles)
    if n < config.MIN_CANDLES:
        return 0.0, {"warmup": True, "candles": n}
    best = {"rsi_c": 0.0, "roc_c": 0.0, "lh_c": 0.0, "vol_c": 0.0}
    inputs_now = {}
    ages = min(config.COMPONENT_MEMORY, n - config.MIN_CANDLES + 1)
    for age in range(ages):
        comps, inp = _components(candles if age == 0 else candles[: n - age])
        if age == 0:
            inputs_now = inp
        d = config.COMPONENT_DECAY ** age
        for k in best:
            best[k] = max(best[k], comps[k] * d)
    score = _clip01(0.25 * best["rsi_c"] + 0.25 * best["roc_c"]
                    + 0.30 * best["lh_c"] + 0.20 * best["vol_c"])
    inputs_now.update({k: round(v, 3) for k, v in best.items()})
    return score, inputs_now


class BookSignalState:
    """Book-pressure scorer. Holds near-ask depth history for the
    thinning/thickening trend component, so it works identically live and in replay."""

    def __init__(self, window_sec=config.BOOK_TREND_WINDOW_SEC):
        self.window = window_sec
        self.hist = []  # (ts, near-ask depth)

    def update(self, ts, bids, asks, last_price):
        """bids/asks: [(price, size)] best-first. Returns (score, inputs).
        Score 1 = heavy overhead supply (likely cap), 0 = clear sky."""
        if not bids or not asks or not last_price:
            return 0.0, {"empty_book": True}
        bid_d = float(sum(s for _, s in bids))
        ask_d = float(sum(s for _, s in asks))
        imb = ask_d / (bid_d + ask_d)
        imb_c = _clip01((imb - 0.5) * 2)

        near = [(p, s) for p, s in asks if p <= last_price * (1 + config.ASK_WALL_PCT)]
        sizes = sorted(s for _, s in asks)
        med = sizes[len(sizes) // 2]
        wall = max((s for _, s in near), default=0)
        wall_ratio = wall / med if med else 0.0
        wall_c = _clip01((wall_ratio - 2.0) / 4.0)  # 2x median starts scoring, 6x maxes

        near_depth = float(sum(s for _, s in near))
        self.hist.append((ts, near_depth))
        cutoff = ts - self.window
        self.hist = [h for h in self.hist if h[0] >= cutoff]
        base = self.hist[0][1]
        change = (near_depth - base) / base if base > 0 else 0.0
        thick_c = _clip01(change / 0.5) if change > 0 else 0.0  # thickening = cap risk

        score = _clip01(0.4 * imb_c + 0.3 * wall_c + 0.3 * thick_c)
        inputs = {
            "imbalance": round(imb, 4), "imb_c": round(imb_c, 3),
            "wall_ratio": round(wall_ratio, 2), "wall_c": round(wall_c, 3),
            "near_ask_change": round(change, 4), "thick_c": round(thick_c, 3),
            "ask_thinning": change < -0.2,
            "bid_depth": bid_d, "ask_depth": ask_d,
        }
        return score, inputs


def composite_score(candle_s, book_s, mode):
    """FULL: weighted blend. DEGRADED: candle only — an absent book never dilutes."""
    if mode == "FULL" and book_s is not None:
        return _clip01(config.CANDLE_WEIGHT * candle_s + config.BOOK_WEIGHT * book_s)
    return candle_s
