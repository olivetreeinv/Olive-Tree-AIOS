"""Parity: vendored core.underwriting must match the original AIOS engine exactly.

golden.json is produced by make_golden.py from the ORIGINAL scripts/deal_analysis.py.
Regenerate only when the source engine changes deliberately.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import underwriting as uw  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent / "golden.json").read_text())
CRITERIA = {"thresholds": GOLDEN["thresholds"], "buy_box": GOLDEN["buy_box"]}


def _eq(a, b, path):
    if isinstance(a, float) or isinstance(b, float):
        assert a is not None and b is not None, f"{path}: {a!r} vs {b!r}"
        assert math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-9), f"{path}: {a!r} vs {b!r}"
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), f"{path}: length {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            _eq(x, y, f"{path}[{i}]")
    elif isinstance(a, dict):
        assert set(a) == set(b), f"{path}: keys {set(a) ^ set(b)}"
        for k in a:
            _eq(a[k], b[k], f"{path}.{k}")
    else:
        assert a == b, f"{path}: {a!r} vs {b!r}"


def test_metrics_and_verdict_parity():
    for name, deal in GOLDEN["deals"].items():
        metrics = uw.calculate_metrics(deal["inputs"], criteria=CRITERIA)
        golden_metrics = dict(deal["metrics"])
        golden_metrics.pop("annual_debt_svc", None)  # legacy duplicate key, dropped in vendored engine
        _eq(golden_metrics, metrics, f"{name}.metrics")

        rec, passes, fails, warnings = uw.score_deal(
            metrics, deal["inputs"].get("zip", ""), criteria=CRITERIA)
        # Original phrasing: "outside the active buy box" → vendored: "outside your buy box"
        norm = lambda xs: [x.replace("the active buy box", "your buy box") for x in xs]
        assert rec == deal["rec"], f"{name}: {rec} vs {deal['rec']}"
        assert norm(deal["passes"]) == passes, f"{name}.passes"
        assert norm(deal["fails"]) == fails, f"{name}.fails"
        assert norm(deal["warnings"]) == warnings, f"{name}.warnings"


def test_empty_buy_box_means_no_zip_gate():
    """Multi-tenant default: a member with no buy box gets no zip fail."""
    inputs = GOLDEN["deals"]["open_market"]["inputs"]
    metrics = uw.calculate_metrics(inputs, criteria=uw.default_criteria())
    _, _, fails, _ = uw.score_deal(metrics, "99999", criteria=uw.default_criteria())
    assert not any("buy box" in f for f in fails)


def test_scorecard_and_verdict_shapes():
    inputs = GOLDEN["deals"]["maple_terrace"]["inputs"]
    metrics = uw.calculate_metrics(inputs, criteria=CRITERIA)
    rec, *_ = uw.score_deal(metrics, inputs["zip"], criteria=CRITERIA)
    card = uw.build_scorecard(metrics, inputs, criteria=CRITERIA)
    assert [c[0] for c in card] == ["Deal Economics", "Basis (PPU)", "Leverage / DSCR",
                                    "Value-Add Upside", "Physical Risk"]
    qv = uw.quick_verdict(metrics, rec, inputs, criteria=CRITERIA)
    assert [q[1] for q in qv] == ["Basis", "Returns", "This Deal"]
    assert all(q[0] in ("green", "yellow", "red", "none") for q in qv)
    assert uw.build_callouts(metrics, inputs, criteria=CRITERIA)  # 1975 vintage → at least one callout


if __name__ == "__main__":
    test_metrics_and_verdict_parity()
    test_empty_buy_box_means_no_zip_gate()
    test_scorecard_and_verdict_shapes()
    print("parity OK")
