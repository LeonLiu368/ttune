from pathlib import Path

import pytest

from scraper.extract import ParseError
from scraper.parsers import irs_eitc, snap_sua

FIXTURES = Path(__file__).parent / "fixtures"

# Rows copied from the FY2026 FNS SUA spreadsheet (header keeps its original double space).
SUA_ROWS = [
    ("Supplemental Nutrition Assistance Program (SNAP) FY 2026 Standard Utility Allowances (SUA) by State",) + (None,) * 9,
    ("Effective October 1, 2025 - September 30, 2026",) + (None,) * 9,
    ("State (with Region and Household Size)", "Heating and Cooling Utility Allowance  (HCSUA)",
     "Basic/ Limited Utility Allowance (BUA/LUA)", "Electricity", "Gas and Fuel", "Water", "Sewage", "Trash",
     "Phone", "SMD Offset"),
    ("Alabama", 637, 466, 0, 0, 0, 0, 0, 53, 4),
    ("Alaska - Central", 625, 0, 134, 310, 59, 61, 37, 26, 0),
    ("Arizona - 1 to 3 members", 323, 149, 0, 0, 0, 0, 0, 44, 6),
    ("Arizona - 4 or more members", 438, 201, 0, 0, 0, 0, 0, 44, 6),
    ("Guam - 13 member +*", 0, 0, 453, 111, 183, 29, 31, 29, 0),
    ("Maryland**", 572, 350, 0, 0, 0, 0, 0, 41, 0),
    ("New Jersey***", "-", "-", "-", "-", "-", "-", "-", "-", "-"),
    ("New York - New York City", 1062, 419, 0, 0, 0, 0, 0, 32, 0),
    ("North Carolina - 1 member", 636.74, 392, 0, 0, 0, 0, 0, 42.11, 0),
    (None,) * 10,
    ("*Indicates the State is not a mandatory SUA State",) + (None,) * 9,
    ("**Indicates the State does not follow the fiscal year for their SUA approvals. Maryland's SUA is effective January 1",) + (None,) * 9,
    ("***Pending",) + (None,) * 9,
    ("Note: Standard Medical Deduction (SMD) offsets have been taken out of the HCSUA amount shown in column B",) + (None,) * 9,
]


def sua(rows=None):
    return snap_sua.parse_rows(rows or SUA_ROWS)


def pick(rows, parameter, region, size=None):
    matches = [r for r in rows if r.parameter == parameter and r.region == region and r.household_size == size]
    assert len(matches) == 1, (parameter, region, size, matches)
    return matches[0]


def test_sua_reads_amounts_regions_and_period():
    rows = sua()
    alabama = pick(rows, "sua.heating_cooling", "AL")
    assert (alabama.value, alabama.unit, alabama.period, alabama.program) == (637.0, "usd_per_month", "2025-10-01", "snap")
    assert pick(rows, "sua.electricity", "AK_C").value == 134.0
    assert pick(rows, "sua.heating_cooling", "NY_NYC").value == 1062.0
    assert pick(rows, "sua.heating_cooling", "NC", 1).value == 636.74


def test_sua_expands_household_size_ranges():
    rows = sua()
    assert [pick(rows, "sua.heating_cooling", "AZ", n).value for n in (1, 2, 3, 4)] == [323.0, 323.0, 323.0, 438.0]
    assert "4 or more members" in pick(rows, "sua.heating_cooling", "AZ", 4).location
    assert pick(rows, "sua.electricity", "GU", 13).value == 453.0


def test_sua_records_footnotes_pending_values_and_notes():
    rows = sua()
    assert pick(rows, "sua.footnote", "GU", 13).raw == "Indicates the State is not a mandatory SUA State"
    assert "effective January 1" in pick(rows, "sua.footnote", "MD").raw
    pending = pick(rows, "sua.heating_cooling", "NJ")
    assert (pending.value, pending.raw) == (None, "-")
    assert pick(rows, "sua.footnote", "NJ").raw == "Pending"
    assert pick(rows, "sua.note", "").raw.startswith("Note: Standard Medical Deduction")


@pytest.mark.parametrize(
    ("index", "replacement", "message"),
    [
        (3, ("Atlantis",) + (1,) * 9, "unknown region"),
        (3, ("Alabama", "lots") + (1,) * 8, "expected an amount"),
        (2, ("State",) + ("x",) * 9, "columns changed"),
        (1, ("Effective sometime",) + (None,) * 9, "effective dates"),
        (4, ("Alaska - Somewhere", 1, 1, 1, 1, 1, 1, 1, 1, 1), "can't read area"),
    ],
)
def test_sua_rejects_unexpected_content(index, replacement, message):
    rows = list(SUA_ROWS)
    rows[index] = replacement
    with pytest.raises(ParseError, match=message):
        sua(rows)


def test_sua_rejects_data_after_footnotes():
    rows = SUA_ROWS + [("Alabama", 1, 1, 1, 1, 1, 1, 1, 1, 1)]
    with pytest.raises(ParseError, match="after the footnotes"):
        sua(rows)


def test_sua_rejects_unexplained_footnote():
    rows = [r for r in SUA_ROWS if not str(r[0]).startswith("***")]
    with pytest.raises(ParseError, match="isn't explained"):
        sua(rows)


def eitc_pages():
    return (FIXTURES / "rp_25_32_eitc_pages.txt").read_text().split("\f")


def test_eitc_reads_table_from_real_rev_proc_text():
    rows = {r.parameter: r for r in irs_eitc.parse_pages(eitc_pages())}
    assert len(rows) == 25
    assert {r.period for r in rows.values()} == {"2026"}
    assert rows["eitc.max_credit.children_0"].value == 664.0
    assert rows["eitc.max_credit.children_3"].value == 8231.0
    assert rows["eitc.earned_income_amount.children_1"].value == 13020.0
    assert rows["eitc.phaseout_start.joint.children_2"].value == 31160.0
    assert rows["eitc.phaseout_end.joint.children_3"].value == 70244.0
    assert rows["eitc.phaseout_start.other.children_0"].value == 10860.0
    assert rows["eitc.phaseout_end.other.children_1"].value == 51593.0
    assert rows["eitc.investment_income_limit"].value == 12200.0
    assert "Three or More" in rows["eitc.max_credit.children_3"].location


def test_eitc_finds_section_on_any_page():
    rows = irs_eitc.parse_pages(["cover page", "contents"] + eitc_pages())
    assert len(rows) == 25


def test_eitc_rejects_missing_section():
    with pytest.raises(ParseError, match="no 'Earned Income Credit' section"):
        irs_eitc.parse_pages(["nothing here"])


def test_eitc_rejects_changed_table_rows():
    pages = [p.replace("Maximum Amount of Credit", "Biggest Credit") for p in eitc_pages()]
    with pytest.raises(ParseError, match="table rows changed"):
        irs_eitc.parse_pages(pages)


def test_eitc_rejects_row_with_missing_amount():
    pages = [p.replace("$4,427 $7,316 $8,231 $664", "$4,427 $7,316 $8,231") for p in eitc_pages()]
    with pytest.raises(ParseError, match="expected 4 amounts"):
        irs_eitc.parse_pages(pages)
