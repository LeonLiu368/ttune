from __future__ import annotations

import re

from scraper.extract import ParseError, Row, Snapshot

# Column order in FNS's FY tables, as PolicyEngine's SNAP region codes.
ALLOTMENT_REGIONS = ["CONTIGUOUS_US", "AK_URBAN", "AK_RURAL_1", "AK_RURAL_2", "GU", "HI", "VI"]
DEDUCTION_REGIONS = ["CONTIGUOUS_US", "AK", "GU", "HI", "VI"]
# Income standards: "48 States, District of Columbia, Guam, Virgin Islands" share one column.
INCOME_REGIONS = ["CONTIGUOUS_US", "AK", "HI"]

FISCAL_YEAR = re.compile(r"Fiscal\s+Year \(FY\) (\d{4})")
AMOUNT = re.compile(r"\$([\d,]+(?:\.\d+)?)")
SIZE_ROW = re.compile(r"^(\d)(\+?)\s+((?:\$[\d,.]+\s*)+)$")


def parse(snapshot: Snapshot) -> list[Row]:
    import pdfplumber

    rows: list[Row] = []
    for name, parse_text in (("maximumallotments-deductions.pdf", parse_allotments),
                             ("-incomeeligibilitystandards.pdf", parse_income_standards)):
        with pdfplumber.open(snapshot.file(name)) as pdf:
            rows += parse_text("\n".join(page.extract_text() or "" for page in pdf.pages))
    return rows


def _fiscal_year(text: str) -> str:
    match = FISCAL_YEAR.search(text)
    if not match:
        raise ParseError("no 'Fiscal Year (FY) YYYY' in the title")
    return f"FY{match.group(1)}"


def _section(text: str, start: str, end: str | None) -> str:
    i = text.find(start)
    if i < 0:
        raise ParseError(f"no {start!r} section")
    j = text.find(end, i) if end else len(text)
    if j < 0:
        raise ParseError(f"no {end!r} section")
    return text[i:j]


def _amounts(line: str) -> list[float]:
    return [float(a.replace(",", "")) for a in AMOUNT.findall(line)]


def _size_rows(section: str, regions: list[str]) -> dict[int, tuple[list[float], str, bool]]:
    rows = {}
    for line in section.splitlines():
        match = SIZE_ROW.match(line.strip())
        if match:
            values = _amounts(match.group(3))
            if len(values) != len(regions):
                raise ParseError(f"expected {len(regions)} amounts in {line!r}")
            rows[int(match.group(1))] = (values, line.strip(), bool(match.group(2)))
    return rows


def _one_line(section: str, regions: list[str], label: str) -> tuple[list[float], str]:
    for line in section.splitlines():
        values = _amounts(line)
        if len(values) == len(regions) and not SIZE_ROW.match(line.strip()):
            return values, line.strip()
    raise ParseError(f"no line of {len(regions)} amounts for {label}")


def parse_allotments(text: str) -> list[Row]:
    """FNS 'Maximum Allotments and Deductions': max allotments, standard and shelter deductions, asset limits."""
    fy = _fiscal_year(text)
    rows: list[Row] = []

    table1 = _section(text, "Table 1: Maximum Monthly Allotment", "Table 2: Standard Deductions")
    sizes = _size_rows(table1, ALLOTMENT_REGIONS)
    if sorted(sizes) != list(range(1, 9)):
        raise ParseError(f"max allotment table: expected sizes 1-8, found {sorted(sizes)}")
    for size, (values, raw, _) in sorted(sizes.items()):
        for region, value in zip(ALLOTMENT_REGIONS, values):
            rows.append(Row("snap", "max_allotment", region, value, "usd_per_month", raw, "Table 1", size, fy))
    extra_line = next((l for l in table1.splitlines() if l.count(" per") == len(ALLOTMENT_REGIONS)), None)
    if extra_line is None:
        raise ParseError("max allotment table: no '$X per additional person' line")
    for region, value in zip(ALLOTMENT_REGIONS, _amounts(extra_line)):
        rows.append(Row("snap", "max_allotment.additional_person", region, value, "usd_per_month",
                        extra_line.strip(), "Table 1, sizes 9-17", None, fy))

    table2 = _section(text, "Table 2: Standard Deductions", "Table 3:")
    sizes = _size_rows(table2, DEDUCTION_REGIONS)
    if sorted(sizes) != list(range(1, 7)) or not sizes[6][2]:
        raise ParseError(f"standard deduction table: expected sizes 1-5 and 6+, found {sorted(sizes)}")
    for size, (values, raw, _) in sorted(sizes.items()):
        for region, value in zip(DEDUCTION_REGIONS, values):
            rows.append(Row("snap", "standard_deduction", region, value, "usd_per_month", raw, "Table 2", size, fy))

    for title, parameter in (("Table 3: Maximum Excess Shelter Deductions", "excess_shelter_deduction.cap"),
                             ("Table 4: Homeless Shelter Deduction", "homeless_shelter_deduction")):
        values, raw = _one_line(_section(text, title, None), DEDUCTION_REGIONS, title)
        for region, value in zip(DEDUCTION_REGIONS, values):
            rows.append(Row("snap", parameter, region, value, "usd_per_month", raw, title.split(":")[0], None, fy))

    assets = _section(text, "Maximum Asset Limits", None)
    values, raw = _one_line(assets, ["elderly_disabled", "standard"], "asset limits")
    for kind, value in zip(["elderly_disabled", "standard"], values):
        rows.append(Row("snap", f"asset_limit.{kind}", "", value, "usd", raw, "Maximum Asset Limits", None, fy))
    return rows


def parse_income_standards(text: str) -> list[Row]:
    """FNS 'Income Eligibility Standards': net (100%), gross (130%) and 165% monthly limits by household size."""
    fy = _fiscal_year(text)
    rows: list[Row] = []
    tables = [("Table 1: Net Monthly Income Limit", "Table 2:", "income_limit.net"),
              ("Table 2: Gross Monthly Income Limit", "Table 3:", "income_limit.gross"),
              ("Table 3: Gross Monthly Income Limit Where Elderly", None, "income_limit.gross_separate_elderly")]
    for title, end, parameter in tables:
        section = _section(text, title, end)
        sizes = _size_rows(section, INCOME_REGIONS)
        if sorted(sizes) != list(range(1, 9)):
            raise ParseError(f"{title}: expected sizes 1-8, found {sorted(sizes)}")
        where = title.split(":")[0]
        for size, (values, raw, _) in sorted(sizes.items()):
            for region, value in zip(INCOME_REGIONS, values):
                rows.append(Row("snap", parameter, region, value, "usd_per_month", raw, where, size, fy))
        flat = " ".join(section.split())
        extra = re.search(r"Each Additional (?:Member )?((?:\$[\d,]+\s*){3})", flat)
        if not extra:
            raise ParseError(f"{title}: no 'Each Additional Member' amounts")
        for region, value in zip(INCOME_REGIONS, _amounts(extra.group(1))):
            rows.append(Row("snap", f"{parameter}.additional_person", region, value, "usd_per_month",
                            extra.group(0), where, None, fy))
    return rows
