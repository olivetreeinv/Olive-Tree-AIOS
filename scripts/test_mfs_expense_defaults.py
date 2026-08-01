"""Self-check for the MFS expense fallbacks in deal_analysis.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from deal_analysis import (
    mfs_expense_ratio_mid, mfs_expense_backfill,
    MFS_RM_PER_UNIT, MFS_TURNOVER_PER_UNIT,
)

# Vintage bands (11-11-25 mentorship): pre-1980 45-50, 1980-2010 35-45, 2010+ 30-40
assert mfs_expense_ratio_mid(1965) == 0.475
assert mfs_expense_ratio_mid(1995) == 0.40
assert mfs_expense_ratio_mid(2015) == 0.35
assert mfs_expense_ratio_mid(None) == 0.475      # unknown → pre-1980 band
assert mfs_expense_ratio_mid("bad") == 0.475     # unparseable → same

# Per-unit defaults match the MFS numbers
assert MFS_RM_PER_UNIT == 750
assert MFS_TURNOVER_PER_UNIT == 450

# Backfill: 24-unit pre-1980, EGI $300k → target opex $142.5k; known $100k → plug $42.5k
plug = mfs_expense_backfill(300_000, 100_000, 1970, ["utilities", "admin", "contracts", "marketing"])
assert sum(plug.values()) == 42_500, plug
assert plug["utilities"] == 25_500               # 60% of the residual
assert plug["utilities"] > plug["admin"] == plug["contracts"] > plug["marketing"]

# Weights renormalize when only some lines are unsourced
plug = mfs_expense_backfill(300_000, 100_000, 1970, ["admin", "marketing"])
assert sum(plug.values()) == 42_500
assert plug["admin"] == 25_500                   # 0.15/0.25 of residual

# Known expenses already at/above the midpoint → no plug
assert mfs_expense_backfill(300_000, 150_000, 1970, ["utilities"]) == {}
# Nothing unsourced → no plug
assert mfs_expense_backfill(300_000, 100_000, 1970, []) == {}

print("OK — all MFS expense fallback checks pass")
