"""Buffered SQLite recorder. add_* methods buffer in memory; flush() batches to disk
(called once a second by the server) so IPO-day tick rates don't bottleneck on commits."""
import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, start_ts REAL, mode TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS trades(ts REAL, price REAL, size INTEGER);
CREATE TABLE IF NOT EXISTS quotes(ts REAL, bid REAL, bid_size INTEGER, ask REAL, ask_size INTEGER);
CREATE TABLE IF NOT EXISTS book_snaps(ts REAL, bids TEXT, asks TEXT);
CREATE TABLE IF NOT EXISTS signals(ts REAL, kind TEXT, score REAL, price REAL, mode TEXT, inputs TEXT);
CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts);
CREATE INDEX IF NOT EXISTS idx_quotes_ts ON quotes(ts);
CREATE INDEX IF NOT EXISTS idx_snaps_ts ON book_snaps(ts);
"""


class Store:
    def __init__(self, path):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)
        self._trades = []
        self._quotes = []
        self._snaps = []

    def start_session(self, mode, note=""):
        self.con.execute(
            "INSERT INTO sessions(start_ts, mode, note) VALUES(strftime('%s','now'), ?, ?)",
            (mode, note))
        self.con.commit()

    def add_trade(self, ts, price, size):
        self._trades.append((ts, price, size))

    def add_quote(self, ts, bid, bid_size, ask, ask_size):
        self._quotes.append((ts, bid, bid_size, ask, ask_size))

    def add_book_snap(self, ts, bids, asks):
        self._snaps.append((ts, json.dumps(bids), json.dumps(asks)))

    def log_signal(self, ts, kind, score, price, mode, inputs):
        # Fires are rare — write through immediately so nothing is lost on crash.
        self.con.execute("INSERT INTO signals VALUES(?,?,?,?,?,?)",
                         (ts, kind, score, price, mode, json.dumps(inputs)))
        self.con.commit()

    def flush(self):
        if self._trades:
            self.con.executemany("INSERT INTO trades VALUES(?,?,?)", self._trades)
            self._trades = []
        if self._quotes:
            self.con.executemany("INSERT INTO quotes VALUES(?,?,?,?,?)", self._quotes)
            self._quotes = []
        if self._snaps:
            self.con.executemany("INSERT INTO book_snaps VALUES(?,?,?)", self._snaps)
            self._snaps = []
        self.con.commit()

    def close(self):
        self.flush()
        self.con.close()
