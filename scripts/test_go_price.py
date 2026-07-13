#!/usr/bin/env python3
"""Tiny self-check for deal_analysis.solve_dscr_price — run: python3 scripts/test_go_price.py

Verifies the DSCR 1.25x GO-price solver is self-consistent: plugging the
solved price's implied loan back through the fully-amortized payment math
must reproduce a 1.25x DSCR to within 0.001.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deal_analysis import solve_dscr_price, _pi_payment, recon_classify  # noqa: E402


def test_recon_classify():
    """Sheet read-back vs Python metrics compare — OK inside tolerance, DRIFT
    beyond it, N/A when either side is missing."""
    delta, status = recon_classify(1.30, 1.32, tol=0.10)
    assert status == "OK" and abs(delta - 0.02) < 1e-9

    delta, status = recon_classify(1.30, 1.55, tol=0.10)
    assert status == "DRIFT" and abs(delta - 0.25) < 1e-9

    delta, status = recon_classify(None, 1.30, tol=0.10)
    assert status == "N/A" and delta is None

    # exactly at the tolerance boundary is still OK (strict > for DRIFT)
    delta, status = recon_classify(1.30, 1.40, tol=0.10)
    assert status == "OK"


def test_go_price_round_trips_to_target_dscr():
    noi, ltv, rate, amort = 100_000, 0.70, 0.065, 30
    price = solve_dscr_price(noi, ltv, rate, amort, target_dscr=1.25)
    assert price is not None

    loan = price * ltv
    annual_ds = _pi_payment(loan, rate, amort) * 12
    dscr = noi / annual_ds
    assert abs(dscr - 1.25) < 0.001, f"DSCR {dscr} != 1.25"


def test_go_price_none_on_missing_noi():
    assert solve_dscr_price(None, 0.70, 0.065, 30) is None
    assert solve_dscr_price(0, 0.70, 0.065, 30) is None


if __name__ == "__main__":
    test_go_price_round_trips_to_target_dscr()
    test_go_price_none_on_missing_noi()
    test_recon_classify()
    print("OK — solve_dscr_price round-trips to DSCR 1.25 within 0.001")
    print("OK — recon_classify OK/DRIFT/N/A classification")
