"""Check the share leg of the weekly realized-P&L line (trading_report._share_pnl).

Money path: it feeds the "Week realized" number in every Suna Desk text, so a sign
flip or a double-counted premium would quietly misreport the week. Run: python3 scripts/test_week_pnl.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.trading_report import _share_pnl


def _lot(strike, avg_cost, shares=100):
    return SimpleNamespace(strike=strike, avg_cost=avg_cost, shares_qty=shares)


def test_share_pnl():
    # called away above basis → gain
    assert _share_pnl([_lot(52.0, 50.0)]) == 200.0
    # called away below basis → loss (never-below-basis rule can be overridden by a roll)
    assert _share_pnl([_lot(48.0, 50.0)]) == -200.0
    # multiple lots sum
    assert _share_pnl([_lot(52.0, 50.0), _lot(31.0, 30.0)]) == 300.0
    # partial lot sizes respected
    assert _share_pnl([_lot(52.0, 50.0, shares=50)]) == 100.0
    # a share-less row books $0, never a phantom 100-share lot
    assert _share_pnl([_lot(52.0, 0.0, shares=0)]) == 0
    # missing fields never crash the alert
    assert _share_pnl([_lot(None, None, None)]) == 0
    assert _share_pnl([]) == 0
    print("✅ _share_pnl OK")


if __name__ == "__main__":
    test_share_pnl()
