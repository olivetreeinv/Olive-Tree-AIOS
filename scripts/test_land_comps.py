#!/usr/bin/env python3
"""Offline check: assessed $/acre median math + in-band/vacant filtering.

No network. Monkeypatches land_parcels.query_parcels with sample records so the
comp logic is exercised without hitting a county GIS.

Run: python3 scripts/test_land_comps.py
"""
import land_comps
import land_parcels as lp


def _rec(land_value, acres, bldg=0):
    return {"land_value": land_value, "acres": acres, "bldg_area_raw": bldg}


def test_assessed_median_in_band_only(monkey=None):
    # $/ac: 10k, 20k, 30k in-band -> median 20k. Out-of-band + improved excluded.
    sample = [
        _rec(40000, 4.0),    # 10,000/ac  ✓
        _rec(100000, 5.0),   # 20,000/ac  ✓
        _rec(90000, 3.0),    # 30,000/ac  ✓
        _rec(500000, 0.2),   # out of band (<1 ac) — excluded
        _rec(60000, 2.0, bldg=150000),  # improved — excluded by is_vacant
    ]
    orig = lp.query_parcels
    lp.query_parcels = lambda county, **kw: sample
    try:
        val, n = land_comps.assessed_ppa("00000", "bartow-ga", 1.0, 10.0)
    finally:
        lp.query_parcels = orig
    assert n == 3, f"expected 3 in-band vacant, got {n}"
    assert val == 20000, f"expected median 20000, got {val}"


def test_thin_sample_returns_none():
    orig = lp.query_parcels
    lp.query_parcels = lambda county, **kw: [_rec(40000, 4.0)]  # only 1
    try:
        val, n = land_comps.assessed_ppa("00000", "bartow-ga")
    finally:
        lp.query_parcels = orig
    assert val is None and n == 1


def test_comp_prefers_sold_over_assessed():
    orig_q, orig_f = lp.query_parcels, land_comps.fmls_median_ppa
    lp.query_parcels = lambda county, **kw: [_rec(40000, 4.0)] * 3  # assessed=10k
    # Closed/ClosePrice -> 27k sold comp wins; Active -> asking reference.
    land_comps.fmls_median_ppa = lambda z, *a, **k: (
        27000 if k.get("status") == "Closed" else 40000)
    try:
        c = land_comps.comp_for_zip("30120", "bartow-ga")
    finally:
        lp.query_parcels, land_comps.fmls_median_ppa = orig_q, orig_f
    assert c["comp"] == 27000 and c["comp_source"] == "sold"
    assert c["sold_ppa"] == 27000 and c["asking_ppa"] == 40000
    assert c["assessed_ppa"] == 10000


def test_comp_falls_back_to_assessed_when_no_sold():
    orig_q, orig_f = lp.query_parcels, land_comps.fmls_median_ppa
    lp.query_parcels = lambda county, **kw: [_rec(40000, 4.0)] * 3  # assessed=10k
    land_comps.fmls_median_ppa = lambda z, *a, **k: None            # no MLS data
    try:
        c = land_comps.comp_for_zip("30120", "bartow-ga")
    finally:
        lp.query_parcels, land_comps.fmls_median_ppa = orig_q, orig_f
    assert c["comp"] == 10000 and c["comp_source"] == "assessed"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
