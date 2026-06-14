class CandleAggregator:
    """Aggregates trades into fixed-interval OHLCV candles."""

    def __init__(self, interval_sec, history_max=5000):
        self.interval = interval_sec
        self.history_max = history_max
        self.current = None   # open (unclosed) candle dict or None
        self.history = []     # closed candles, oldest -> newest

    def add(self, ts, price, size):
        """Feed one trade. Returns the just-closed candle on bucket rollover, else None."""
        bucket = int(ts // self.interval) * self.interval
        closed = None
        if self.current is not None and bucket > self.current["ts"]:
            closed = self.current
            self.history.append(closed)
            if len(self.history) > self.history_max:
                del self.history[: len(self.history) - self.history_max]
            self.current = None
        if self.current is None:
            self.current = {"ts": bucket, "o": price, "h": price, "l": price, "c": price, "v": 0}
        c = self.current
        c["h"] = max(c["h"], price)
        c["l"] = min(c["l"], price)
        c["c"] = price
        c["v"] += size
        return closed
