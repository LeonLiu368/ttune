import re
from pathlib import Path

import pytest

from scraper.extract import ParseError
from scraper.parsers import hhs_fpg, irs_eitc, medicaid_current, snap_cola, snap_sua

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


def fpg_text():
    return (FIXTURES / "fpg_2026_notice.txt").read_text()


def test_fpg_reads_all_three_tables():
    rows = hhs_fpg.parse_text(fpg_text())
    assert len(rows) == 30
    assert {r.period for r in rows} == {"2026"}
    assert pick(rows, "guideline", "CONTIGUOUS_US", 1).value == 15960.0
    assert pick(rows, "guideline", "CONTIGUOUS_US", 4).value == 33000.0
    assert pick(rows, "guideline", "AK", 8).value == 69650.0
    assert pick(rows, "guideline", "HI", 3).value == 31420.0
    assert pick(rows, "first_person", "HI").value == 18360.0
    assert pick(rows, "additional_person", "AK").value == 7100.0


def test_fpg_rejects_missing_table_or_row():
    with pytest.raises(ParseError, match="expected 3 poverty guideline tables"):
        hhs_fpg.parse_text(fpg_text().replace("Guidelines for Hawaii", "Guidelines for Elsewhere"))
    with pytest.raises(ParseError, match="expected sizes 1-8"):
        hhs_fpg.parse_text(re.sub(r"^8\.+\s+69,650$", "8 lots", fpg_text(), flags=re.M))


def cola(name):
    return (FIXTURES / name).read_text()


def test_cola_reads_allotments_deductions_and_asset_limits():
    rows = snap_cola.parse_allotments(cola("snap_fy27_allotments.txt"))
    assert {r.period for r in rows} == {"FY2027"}
    assert pick(rows, "max_allotment", "CONTIGUOUS_US", 1).value == 306.0
    assert pick(rows, "max_allotment", "AK_RURAL_2", 8).value == 3650.0
    assert pick(rows, "max_allotment", "VI", 4).value == 1315.0
    assert pick(rows, "max_allotment.additional_person", "HI").value == 364.0
    assert pick(rows, "standard_deduction", "GU", 6).value == 614.0
    assert pick(rows, "standard_deduction", "CONTIGUOUS_US", 4).value == 229.0
    assert pick(rows, "excess_shelter_deduction.cap", "AK").value == 1229.0
    assert pick(rows, "homeless_shelter_deduction", "VI").value == 205.66
    assert pick(rows, "asset_limit.elderly_disabled", "").value == 4750.0
    assert pick(rows, "asset_limit.standard", "").value == 3000.0


def test_cola_reads_income_standards():
    rows = snap_cola.parse_income_standards(cola("snap_fy27_income_standards.txt"))
    assert pick(rows, "income_limit.net", "CONTIGUOUS_US", 1).value == 1330.0
    assert pick(rows, "income_limit.gross", "AK", 4).value == 4469.0
    assert pick(rows, "income_limit.gross", "HI", 8).value == 6941.0
    assert pick(rows, "income_limit.gross.additional_person", "CONTIGUOUS_US").value == 616.0
    assert pick(rows, "income_limit.gross_separate_elderly.additional_person", "HI").value == 898.0


def test_cola_rejects_short_rows_and_missing_sections():
    with pytest.raises(ParseError, match="expected 7 amounts"):
        snap_cola.parse_allotments(cola("snap_fy27_allotments.txt").replace("$1,841 $2,352", "$1,841"))
    with pytest.raises(ParseError, match="no 'Table 2: Standard Deductions' section"):
        snap_cola.parse_allotments(cola("snap_fy27_allotments.txt").replace("Table 2: Standard", "Table 2: Other"))
    with pytest.raises(ParseError, match="no 'Fiscal Year"):
        snap_cola.parse_income_standards(cola("snap_fy27_income_standards.txt").replace("(FY) 2027", "2027"))


def medicaid_html():
    return (FIXTURES / "medicaid_levels_current_sample.html").read_text()


def test_medicaid_current_reads_table_date_and_footnoted_values():
    with pytest.raises(ParseError, match="expected 51 states"):
        medicaid_current.parse_html(medicaid_html())
    rows = medicaid_current.parse_html(medicaid_html(), min_states=5)
    assert {r.period for r in rows} == {"2023-12-01"}
    assert pick(rows, "income_limit.infant", "AL").value == 141.0
    assert pick(rows, "income_limit.expansion_adult", "AL").value is None  # "No"
    alaska = pick(rows, "income_limit.parent", "AK")  # "130%($)"; footnote 5 dropped from "Alaska"
    assert (alaska.value, alaska.raw) == (130.0, "130%($)")
    assert "dollar amounts" in pick(rows, "income_limit.parent.note", "AK").raw
    assert pick(rows, "income_limit.child", "DE").value == 212.0
    assert pick(rows, "income_limit.child.note", "DE").raw == "ages 1 up to 19"
    assert pick(rows, "income_limit.child", "CA").value is None  # "See note"
    wisconsin = pick(rows, "income_limit.expansion_adult", "WI")
    assert (wisconsin.value, wisconsin.raw) == (None, "No/95%")


def test_medicaid_current_rejects_changed_columns_and_values():
    with pytest.raises(ParseError, match="columns changed"):
        medicaid_current.parse_html(medicaid_html().replace("Pregnant Women Medicaid", "Pregnant People"), min_states=5)
    with pytest.raises(ParseError, match="can't read 'lots'"):
        medicaid_current.parse_html(medicaid_html().replace("<td>141%</td>", "<td>lots</td>", 1), min_states=5)
    with pytest.raises(ParseError, match="no 'as of <date>'"):
        medicaid_current.parse_html(medicaid_html().replace("as of December 1, 2023", "recently"), min_states=5)
