"""Tier B (optional): Databento XNAS.ITCH live MBO depth.

probe() decides FULL vs DEGRADED at startup; start_feed() applies records to a
thread-safe OrderBook from Databento's own client thread."""
import threading

from . import config


def _ch(v):
    return chr(v) if isinstance(v, int) else v


def probe(api_key, symbol, timeout=config.PROBE_TIMEOUT_SEC):
    """Try to receive one live MBO record (snapshot or stream) for symbol.
    Returns (ok, reason)."""
    try:
        import databento as db
    except ImportError:
        return False, "databento package not installed (pip install databento)"
    got = threading.Event()

    def cb(rec):
        if isinstance(rec, db.MBOMsg):
            got.set()

    client = None
    try:
        client = db.Live(key=api_key)
        client.subscribe(dataset=config.DATABENTO_DATASET, schema="mbo",
                         stype_in="raw_symbol", symbols=[symbol], snapshot=True)
        client.add_callback(cb)
        client.start()
        ok = got.wait(timeout)
        return ok, None if ok else (
            f"no MBO records within {timeout:.0f}s "
            "(no TotalView license, market closed, or symbol not yet live)")
    except Exception as e:
        return False, str(e)
    finally:
        if client is not None:
            try:
                client.stop()
            except Exception:
                pass


def start_feed(api_key, symbol, book, on_error=None):
    """Subscribe and pump MBO records into `book`. Returns the live client
    (call .stop() on shutdown). Callbacks run on Databento's thread; the
    OrderBook is lock-guarded, so no event-loop hop per record."""
    import databento as db

    client = db.Live(key=api_key)
    client.subscribe(dataset=config.DATABENTO_DATASET, schema="mbo",
                     stype_in="raw_symbol", symbols=[symbol], snapshot=True)

    def cb(rec):
        if isinstance(rec, db.MBOMsg):
            book.apply(_ch(rec.action), _ch(rec.side), rec.order_id,
                       rec.price / 1e9, rec.size)

    client.add_callback(cb)
    if on_error is not None:
        client.add_exception_callback(on_error)
    client.start()
    return client
