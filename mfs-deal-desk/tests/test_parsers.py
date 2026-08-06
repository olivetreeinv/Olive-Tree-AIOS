"""Parser regression checks — the three defects found in the 2026-07-31 review.

These are the deterministic layer that runs BEFORE any LLM extraction, so a
silent None here reads downstream as "the document didn't have that line."
Run: python3 tests/test_parsers.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.parsers import _num, _scan_t12_rows, _scan_rent_roll_rows, classify_filename  # noqa: E402

EMPTY_T12 = {"current_gpr": None, "current_opex": None, "current_noi": None, "vacancy_annual": None}


def test_num_handles_csv_strings():
    assert _num(1200000) == 1200000.0          # xlsx hands back real numbers
    assert _num("$1,200,000") == 1200000.0     # csv.reader hands back strings
    assert _num("450,000") == 450000.0
    assert _num(" 1 234.50 ") == 1234.50
    assert _num("(45,000)") == -45000.0        # accounting negative
    assert _num("-45000") == -45000.0
    assert _num("") is None
    assert _num(None) is None
    assert _num("n/a") is None
    assert _num("-") is None
    assert _num(True) is None                  # bool is an int subclass; not a figure


def test_formatted_csv_t12_parses():
    """Was the worst of the three: every value dropped, whole doc read as empty."""
    rows = [["Gross Potential Rent", "$1,200,000"],
            ["Total Operating Expenses", "450,000"],
            ["Net Operating Income", "750,000"]]
    got = _scan_t12_rows(rows, dict(EMPTY_T12))
    assert got["current_gpr"] == 1200000.0, got
    assert got["current_opex"] == 450000.0, got
    assert got["current_noi"] == 750000.0, got


def test_negative_vacancy_captured_as_magnitude():
    """Vacancy loss is conventionally negative; the engine wants a positive loss."""
    assert _scan_t12_rows([["Vacancy Loss", -45000.0]], dict(EMPTY_T12))["vacancy_annual"] == 45000.0
    assert _scan_t12_rows([["Vacancy Loss", "(45,000)"]], dict(EMPTY_T12))["vacancy_annual"] == 45000.0
    # a wholly-negative monthly expense row flips, and still sums to the year
    months = [["Total Operating Expenses"] + [-37500.0] * 12]
    assert _scan_t12_rows(months, dict(EMPTY_T12))["current_opex"] == 450000.0


def test_positive_rows_unchanged():
    """Guard the flip: normal positive layouts must behave exactly as before."""
    months = [["Gross Potential Rent"] + [100000.0] * 12]
    assert _scan_t12_rows(months, dict(EMPTY_T12))["current_gpr"] == 1200000.0
    # annual-total column wins when it dwarfs the monthly median
    with_total = [["Gross Potential Rent"] + [100000.0] * 12 + [1200000.0]]
    assert _scan_t12_rows(with_total, dict(EMPTY_T12))["current_gpr"] == 1200000.0
    # mixed-sign row still drops its negatives rather than flipping
    mixed = [["Rental Income", 100000.0, -2000.0]]
    assert _scan_t12_rows(mixed, dict(EMPTY_T12))["current_gpr"] == 100000.0


def test_rent_roll_csv_strings():
    rows = [["Unit", "Bed", "Current Rent", "Market Rent"],
            ["101", "1BR", "$1,250", "1,400"],
            ["102", "1BR", "1,250.00", "$1,400"],
            ["103", "2BR", "1,600", "1,750"]]
    result = {"units": 0, "current_gpr": 0.0, "unit_mix": [], "source": "Rent Roll"}
    got = _scan_rent_roll_rows(iter(rows), result)
    assert got["units"] == 3, got
    assert got["current_gpr"] == 4100.0, got
    one_br = next(e for e in got["unit_mix"] if e["type"] == "1BR")
    assert one_br["count"] == 2 and one_br["current_rent"] == 1250
    assert one_br["market_rent"] == 1400


def test_om_matches_whole_word_only():
    assert classify_filename("Thompson Apartments Financials.xlsx") is None
    assert classify_filename("Somerset Apartments.pdf") is None
    assert classify_filename("Compass Ridge.pdf") is None
    assert classify_filename("641 Powder Springs OM.pdf") == "om"
    assert classify_filename("OM_final.pdf") == "om"
    assert classify_filename("641-om-v2.pdf") == "om"
    assert classify_filename("Offering Memorandum.pdf") == "om"
    # the other classes keep priority over om
    assert classify_filename("Somerset T-12.pdf") == "t12"
    assert classify_filename("Compass Ridge Rent Roll.xlsx") == "rent_roll"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ✅ {name}")
    print("parsers OK")
