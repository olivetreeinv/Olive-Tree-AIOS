#!/usr/bin/env python3
"""Regression check for cc_premium_stats() across a month boundary.

The bug this pins: the closed-position fetch filtered on mtd_start, but the
WTD fallback reused that same list. Any week straddling the 1st of a month
(wtd_start lands in the PRIOR month) silently dropped the week's first days —
on 2026-08-01 that read $1,100 of real premium as $0 on --status, the
heartbeat summary, the scorecard email, and /goal-watch.

Run: python3 scripts/test_cc_premium_windows.py
"""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

# Must be set BEFORE db.connection is imported — it reads the env at module load.
_tmpdb = Path(tempfile.mkdtemp()) / "test_olive.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdb}"

from db.connection import Session, init_db          # noqa: E402
from db.schema import TradingCCPosition             # noqa: E402
from scripts import trading_covered_calls as cc     # noqa: E402


def _seed():
    """One lot closed 2026-07-31: inside the Jul 27 week, outside the Aug month."""
    init_db()
    s = Session()
    try:
        s.add(TradingCCPosition(
            underlying="RIVN", shares_qty=600, avg_cost=15.55,
            option_symbol="RIVN260807C00016000", option_type="call",
            strike=16.0, expiry="2026-08-07", premium_received=1100.0,
            status="closed",
            opened_at="2026-07-31T15:21:45.910609+00:00",
            closed_at="2026-07-31T18:39:06.504302+00:00",
            realized_pnl=-12.0,
        ))
        s.commit()
    finally:
        s.close()


class _FrozenDate(date):
    _now = date(2026, 8, 1)          # Saturday; that week started Mon Jul 27

    @classmethod
    def today(cls):
        return cls._now


def main():
    _seed()
    with mock.patch.object(cc, "date", _FrozenDate):
        stats = cc.cc_premium_stats()

    # The week (Jul 27 – Aug 2) contains the lot, so its premium must show up.
    assert stats["premium_wtd"] == 1100.0, \
        f"WTD lost the pre-month-boundary lot: {stats}"
    # August month-to-date must NOT claim July's premium or its realized P&L.
    assert stats["premium_mtd"] == 0, f"MTD leaked a July lot: {stats}"
    assert stats["realized_pnl"] == 0, f"realized_pnl leaked a July lot: {stats}"

    # Mid-month sanity: same lot is now outside BOTH windows.
    _FrozenDate._now = date(2026, 8, 20)
    with mock.patch.object(cc, "date", _FrozenDate):
        stats = cc.cc_premium_stats()
    assert stats == {"premium_wtd": 0, "premium_mtd": 0, "realized_pnl": 0}, \
        f"stale lot counted mid-month: {stats}"

    print("ok — cc_premium_stats windows correct across the month boundary")


if __name__ == "__main__":
    main()
