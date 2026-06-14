"""Tier A (required): Polygon.io trades + NBBO over websocket.

Auto-negotiates entitlements, best feed first:
  1. real-time trades+quotes   2. real-time per-second aggregates
  3. delayed trades+quotes     4. delayed per-second aggregates
While on a fallback it re-probes the better feeds every RETRY_BETTER_SEC, so a
plan upgrade is picked up automatically without a restart. Per-second aggregate
bars are synthesized into pseudo-trades (o/h/l/c) so candle highs and lows
survive; volume rides on the close print.
"""
import asyncio
import json
import ssl
import time

import certifi
import websockets

# python.org builds on macOS don't trust the system CA store — use certifi's bundle
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

CONFIGS = [  # best -> worst
    {"name": "real-time trades", "url": "wss://socket.polygon.io/stocks", "channel": "trades", "delayed": False},
    {"name": "real-time aggregates", "url": "wss://socket.polygon.io/stocks", "channel": "aggs", "delayed": False},
    {"name": "DELAYED trades", "url": "wss://delayed.polygon.io/stocks", "channel": "trades", "delayed": True},
    {"name": "DELAYED aggregates", "url": "wss://delayed.polygon.io/stocks", "channel": "aggs", "delayed": True},
]
RETRY_BETTER_SEC = 300


def _subs(channel, symbol):
    return f"T.{symbol},Q.{symbol}" if channel == "trades" else f"A.{symbol}"


async def _run_config(cfg, api_key, symbol, on_trade, on_quote, on_feed):
    """Returns 'unauthorized' | 'retry_better' | 'closed'. Raises on transport errors."""
    started = time.time()
    async with websockets.connect(cfg["url"], ssl=SSL_CTX, ping_interval=20) as ws:
        await ws.send(json.dumps({"action": "auth", "params": api_key}))
        async for raw in ws:
            for m in json.loads(raw):
                ev = m.get("ev")
                if ev == "T":
                    await on_trade(m["t"] / 1000.0, m["p"], m.get("s", 0))
                elif ev == "Q":
                    await on_quote(m["t"] / 1000.0, m.get("bp"), m.get("bs"),
                                   m.get("ap"), m.get("as"))
                elif ev == "A":
                    ts = m["s"] / 1000.0
                    await on_trade(ts, m["o"], 0)
                    await on_trade(ts + 0.25, m["h"], 0)
                    await on_trade(ts + 0.50, m["l"], 0)
                    await on_trade(ts + 0.75, m["c"], m.get("v", 0))
                elif ev == "status":
                    st = m.get("status")
                    msg = m.get("message") or ""
                    if st == "auth_success":
                        await ws.send(json.dumps(
                            {"action": "subscribe", "params": _subs(cfg["channel"], symbol)}))
                    elif st == "auth_failed":
                        raise RuntimeError(f"Polygon auth failed: {msg}")
                    elif st == "success" and "subscribed" in msg.lower():
                        print(f"[polygon] connected: {cfg['name']}")
                        if on_feed:
                            await on_feed({"name": cfg["name"], "delayed": cfg["delayed"],
                                           "channel": cfg["channel"]})
                    elif st == "error":
                        low = msg.lower()
                        if "not authorized" in low or "access" in low:
                            return "unauthorized"
                        print(f"[polygon] {msg}")
            # while on a fallback feed, periodically re-probe the better ones
            if cfg is not CONFIGS[0] and time.time() - started > RETRY_BETTER_SEC:
                return "retry_better"
    return "closed"


async def run(api_key, symbol, on_trade, on_quote, on_feed=None):
    backoff = 1
    while True:
        for cfg in CONFIGS:
            try:
                result = await _run_config(cfg, api_key, symbol, on_trade, on_quote, on_feed)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[polygon] {cfg['name']}: {e} — reconnecting in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
                break  # transport problem — restart from the best feed
            if result == "unauthorized":
                print(f"[polygon] {cfg['name']}: not authorized — trying next tier")
                continue
            if result == "retry_better":
                print("[polygon] re-probing for a better feed (plan may have upgraded)")
            backoff = 1
            break  # clean close or re-probe — restart from the best feed
        else:
            # every tier unauthorized — wait and retry from the top
            print(f"[polygon] no authorized feed — retrying in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 15)
