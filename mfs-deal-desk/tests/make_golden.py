"""Generate tests/golden.json from the ORIGINAL Olive Tree AIOS engine.

Run once (and after any deliberate engine change) from inside the AIOS monorepo:
    .venv/bin/python mfs-deal-desk/tests/make_golden.py
The parity test then locks the vendored core/underwriting.py to these values.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import deal_analysis as da  # noqa: E402

DEALS = {
    "maple_terrace": dict(
        asking=2_800_000, units=24, zip="30341", repair=240_000,
        current_gpr=22_000, market_gpr=26_000, current_opex=11_000, vintage=1975,
    ),
    "open_market": dict(
        asking=1_850_000, units=18, zip="37207",
        current_gpr=17_000, entry_cap=5.5, exit_cap=6.0,
    ),
    "minimal": dict(asking=900_000, units=8, current_gpr=9_500),
}

out = {"buy_box": da.BUY_BOX, "thresholds": da.THRESHOLDS, "deals": {}}
for name, inputs in DEALS.items():
    metrics = da.calculate_metrics(SimpleNamespace(**inputs))
    rec, passes, fails, warnings = da.score_deal(metrics, inputs.get("zip", ""))
    out["deals"][name] = {
        "inputs": inputs, "metrics": metrics, "rec": rec,
        "passes": passes, "fails": fails, "warnings": warnings,
    }

dest = Path(__file__).parent / "golden.json"
dest.write_text(json.dumps(out, indent=1, default=str))
print(f"wrote {dest}")
