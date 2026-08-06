"""Aggregated price-level order book built from Databento XNAS.ITCH MBO records.

Thread-safe: the Databento feed thread applies records while the asyncio loop
reads levels() once a second."""
import threading


class OrderBook:
    def __init__(self):
        self.lock = threading.Lock()
        self.orders = {}  # order_id -> (side, price, size)
        self.bids = {}    # price -> aggregate size
        self.asks = {}

    def _add(self, side, price, size):
        book = self.bids if side == "B" else self.asks
        book[price] = book.get(price, 0) + size

    def _remove(self, side, price, size):
        book = self.bids if side == "B" else self.asks
        rem = book.get(price, 0) - size
        if rem > 0:
            book[price] = rem
        else:
            book.pop(price, None)

    def apply(self, action, side, order_id, price, size):
        """MBO actions: A add, C cancel, M modify (cancel-replace), F fill,
        T trade (aggressor, no resting change), R clear."""
        if action != "R" and side not in ("B", "A"):
            return
        with self.lock:
            if action == "R":
                self.orders.clear()
                self.bids.clear()
                self.asks.clear()
            elif action == "A":
                self.orders[order_id] = (side, price, size)
                self._add(side, price, size)
            elif action in ("C", "F"):
                o = self.orders.get(order_id)
                if not o:
                    return
                s, p, sz = o
                take = min(size, sz)
                self._remove(s, p, take)
                if sz - take > 0:
                    self.orders[order_id] = (s, p, sz - take)
                else:
                    self.orders.pop(order_id, None)
            elif action == "M":
                old = self.orders.pop(order_id, None)
                if old:
                    self._remove(old[0], old[1], old[2])
                self.orders[order_id] = (side, price, size)
                self._add(side, price, size)

    def levels(self, n=10):
        """Top n aggregated levels: (bids best-first, asks best-first)."""
        with self.lock:
            bids = sorted(self.bids.items(), key=lambda x: -x[0])[:n]
            asks = sorted(self.asks.items(), key=lambda x: x[0])[:n]
        return bids, asks
