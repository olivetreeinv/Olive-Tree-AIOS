"""SPCX IPO-day monitor — live feeds, signal engine, FastAPI + websocket UI.

Run: python -m spcx.server   (then open http://127.0.0.1:8765)
"""
import asyncio
import contextlib
import json
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import config, databento_feed, polygon_feed
from .alerts import AlertManager
from .book import OrderBook
from .candles import CandleAggregator
from .signals import BookSignalState, candle_exhaustion, composite_score
from .storage import Store

STATIC = Path(__file__).resolve().parent.parent / "static"

clients = set()
engine = None
_tasks = []
_db_client = None


async def broadcast(msg):
    data = json.dumps(msg)
    dead = []
    # snapshot — clients can connect/disconnect while we await sends
    for ws in list(clients):
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


class Engine:
    def __init__(self, store, mode, mode_reason):
        self.store = store
        self.mode = mode
        self.mode_reason = mode_reason
        self.alerts = AlertManager(store, broadcast, mode)
        self.fast = CandleAggregator(config.FAST_CANDLE_SEC)
        self.slow = CandleAggregator(config.SLOW_CANDLE_SEC)
        self.book = OrderBook() if mode == "FULL" else None
        self.book_state = BookSignalState()
        self.last_price = None
        self.nbbo = None
        self.feed = None  # set by polygon_feed once a channel subscribes
        self.candle_score, self.candle_inputs = 0.0, {}
        self.book_score, self.book_inputs = None, {}
        self.comp_score = 0.0

    async def on_trade(self, ts, price, size):
        self.store.add_trade(ts, price, size)
        self.last_price = price
        closed = self.fast.add(ts, price, size)
        closed_slow = self.slow.add(ts, price, size)
        if closed_slow:
            await broadcast({"type": "candle", "interval": config.SLOW_CANDLE_SEC,
                             "candle": closed_slow})
        if closed:
            await broadcast({"type": "candle", "interval": config.FAST_CANDLE_SEC,
                             "candle": closed})
            self.candle_score, self.candle_inputs = candle_exhaustion(self.fast.history)
            await self._evaluate(ts)
        await self._check_milestones(ts, price)

    async def on_feed(self, info):
        self.feed = info
        await broadcast(self.state())

    async def on_quote(self, ts, bid, bid_size, ask, ask_size):
        self.store.add_quote(ts, bid, bid_size, ask, ask_size)
        self.nbbo = {"bid": bid, "bid_size": bid_size, "ask": ask, "ask_size": ask_size}

    async def on_book_tick(self, ts):
        """1s cadence in FULL mode: persist the top of book, refresh book score."""
        bids, asks = self.book.levels(config.BOOK_LEVELS)
        self.store.add_book_snap(ts, bids, asks)
        self.book_score, self.book_inputs = self.book_state.update(
            ts, bids, asks, self.last_price)
        await self._evaluate(ts)

    async def _check_milestones(self, ts, price):
        pct = (price / config.IPO_REF_PRICE - 1) * 100
        for m in config.MILESTONES:
            if pct >= m:
                await self.alerts.fire(
                    key=f"milestone+{m}", kind="milestone", ts=ts, price=price,
                    score=None,
                    inputs={"pct_gain": round(pct, 2), "ref": config.IPO_REF_PRICE},
                    message=(f"{config.SYMBOL} +{m}% off IPO ref "
                             f"${config.IPO_REF_PRICE:g} — last {price:.2f}"),
                    sms=True, once=True)

    async def _evaluate(self, ts):
        self.comp_score = composite_score(self.candle_score, self.book_score, self.mode)
        price = self.last_price
        if price is None:
            return
        if self.candle_score >= config.CANDLE_THRESHOLD:
            await self.alerts.fire(
                "sig-candle", "candle", ts, price, self.candle_score,
                self.candle_inputs,
                f"Candle exhaustion {self.candle_score:.2f} @ {price:.2f}")
        if self.mode == "FULL" and (self.book_score or 0) >= config.BOOK_THRESHOLD:
            await self.alerts.fire(
                "sig-book", "book", ts, price, self.book_score, self.book_inputs,
                f"Book pressure {self.book_score:.2f} @ {price:.2f}")
        if self.comp_score >= config.COMPOSITE_ALERT_THRESHOLD:
            await self.alerts.fire(
                "sig-composite", "composite", ts, price, self.comp_score,
                {"candle_score": self.candle_score, "book_score": self.book_score,
                 "candle": self.candle_inputs, "book": self.book_inputs},
                (f"SPCX exhaustion composite {self.comp_score:.2f} "
                 f"@ {price:.2f} [{self.mode}]"),
                sms=True)

    def state(self):
        return {
            "type": "state", "mode": self.mode, "mode_reason": self.mode_reason,
            "feed": self.feed,
            "ipo_ref": config.IPO_REF_PRICE, "last": self.last_price, "nbbo": self.nbbo,
            "symbol": config.SYMBOL,
            "scores": {"candle": round(self.candle_score, 3),
                       "book": None if self.book_score is None else round(self.book_score, 3),
                       "composite": round(self.comp_score, 3)},
            "current_candle": self.fast.current,
            "current_candle_slow": self.slow.current,
            "thresholds": {"composite": config.COMPOSITE_ALERT_THRESHOLD},
        }


async def _ticker(store):
    while True:
        await asyncio.sleep(1)
        try:
            if engine.mode == "FULL":
                await engine.on_book_tick(time.time())
            store.flush()
            await broadcast(engine.state())
        except Exception as e:
            # the ticker must survive — it owns SQLite flushing
            print(f"[ticker] error: {e}")


@contextlib.asynccontextmanager
async def lifespan(app):
    global engine, _db_client
    if not config.POLYGON_API_KEY:
        raise SystemExit("POLYGON_API_KEY is required (Tier A). Set it in .env.")
    store = Store(config.DB_PATH)
    mode, reason = "DEGRADED", "DATABENTO_API_KEY not set"
    if config.DATABENTO_API_KEY:
        loop = asyncio.get_running_loop()
        ok, err = await loop.run_in_executor(
            None, databento_feed.probe, config.DATABENTO_API_KEY, config.SYMBOL)
        mode, reason = ("FULL", None) if ok else ("DEGRADED", err)
    print(f"[mode] {mode}" + (f" — {reason}" if reason else " — live depth confirmed"))
    store.start_session(mode, reason or "")
    engine = Engine(store, mode, reason)
    if mode == "FULL":
        _db_client = databento_feed.start_feed(
            config.DATABENTO_API_KEY, config.SYMBOL, engine.book,
            on_error=lambda e: print(f"[databento] {e}"))
    _tasks.append(asyncio.create_task(polygon_feed.run(
        config.POLYGON_API_KEY, config.SYMBOL, engine.on_trade, engine.on_quote,
        on_feed=engine.on_feed)))
    _tasks.append(asyncio.create_task(_ticker(store)))
    print(f"[server] monitoring {config.SYMBOL}, IPO ref ${config.IPO_REF_PRICE:g} "
          f"— http://127.0.0.1:8765")
    yield
    for t in _tasks:
        t.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    if _db_client is not None:
        with contextlib.suppress(Exception):
            _db_client.stop()
    store.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/status")
async def status():
    return engine.state()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "hello",
            "state": engine.state(),
            "candles_fast": engine.fast.history[-720:],
            "candles_slow": engine.slow.history[-390:],
            "alerts": engine.alerts.recent,
        }))
        while True:
            await ws.receive_text()  # client messages are ignored (keepalive only)
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


def main():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
