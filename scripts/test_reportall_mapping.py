#!/usr/bin/env python3
"""Offline check: a ReportAll-shaped record normalizes + filters correctly.

No API key, no network. Confirms the REPORTALL_FIELD_MAP wiring feeds the
existing pipeline (is_vacant / is_out_of_state / apply_filters / acre_stats)
so the moment trial keys land, only the live field names need confirming.

Run: python3 scripts/test_reportall_mapping.py
"""
from land_parcels import (
    REPORTALL_FIELD_MAP, _normalize, is_vacant, is_out_of_state,
    apply_filters, acre_stats, query_parcels_reportall,
)

# Two sample rows in ReportAll v9 shape: one vacant out-of-state in-band lot
# (a target), one improved in-state lot (should be filtered out).
SAMPLE = [
    {  # TARGET: vacant, FL owner, 4.5 ac
        "parcel_id": "001-A", "addr_number": "100", "addr_street_name": "Timber",
        "addr_street_suffix": "Trl", "physzip": "40004",
        "acreage_calc": 4.5, "land_use_code": "100", "mkt_val_bldg": 0,
        "owner": "SMITH JANE", "mail_address1": "9 Beach Rd",
        "mail_city": "Naples", "mail_state": "FL", "mail_zip": "34102",
        "mkt_val_land": 38000,
    },
    {  # SKIP: improved (has building value), KY owner
        "parcel_id": "002-B", "addr_number": "55", "addr_street_name": "Main",
        "addr_street_suffix": "St", "physzip": "40004",
        "acreage_calc": 0.3, "land_use_code": "200", "mkt_val_bldg": 145000,
        "owner": "DOE JOHN", "mail_address1": "55 Main St",
        "mail_city": "Bardstown", "mail_state": "KY", "mail_zip": "40004",
        "mkt_val_land": 20000,
    },
]


def test_normalize_maps_canonical_fields():
    rec = _normalize(SAMPLE[0], REPORTALL_FIELD_MAP)
    assert rec["parcel_id"] == "001-A"
    assert rec["site_address"] == "100 Timber Trl"
    assert rec["acres"] == 4.5
    assert rec["owner_state"] == "FL"
    assert rec["land_value"] == 38000.0


def test_vacant_and_absentee_flags():
    target = _normalize(SAMPLE[0], REPORTALL_FIELD_MAP)
    improved = _normalize(SAMPLE[1], REPORTALL_FIELD_MAP)
    assert is_vacant(target) and not is_vacant(improved)
    assert is_out_of_state(target, "KY") and not is_out_of_state(improved, "KY")


def test_pipeline_filters_to_the_one_target():
    recs = [_normalize(r, REPORTALL_FIELD_MAP) for r in SAMPLE]
    kept = apply_filters(recs, vacant=True, out_of_state=True, home_state="KY",
                         min_acres=1, max_acres=10)
    assert len(kept) == 1 and kept[0]["parcel_id"] == "001-A"
    assert acre_stats(kept)["count"] == 1


def test_fetch_is_inert_without_key():
    try:
        query_parcels_reportall("Nelson, KY", api_key=None)
    except RuntimeError as e:
        assert "REPORTALL_API_KEY" in str(e)
    else:
        raise AssertionError("expected RuntimeError when no API key is set")


if __name__ == "__main__":
    import os
    os.environ.pop("REPORTALL_API_KEY", None)  # ensure inert-fetch test is valid
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
