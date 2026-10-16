from __future__ import annotations

import re
from datetime import datetime

from scraper.extract import ParseError, Row, Snapshot
from scraper.parsers.regions import SNAP_AREAS, STATE_CODES

HEADER = (
    "State (with Region and Household Size)",
    "Heating and Cooling Utility Allowance (HCSUA)",
    "Basic/ Limited Utility Allowance (BUA/LUA)",
    "Electricity",
    "Gas and Fuel",
    "Water",
    "Sewage",
    "Trash",
    "Phone",
    "SMD Offset",
)
PARAMETERS = (
    "sua.heating_cooling",
    "sua.basic_limited",
    "sua.electricity",
    "sua.gas_fuel",
    "sua.water",
    "sua.sewage",
    "sua.trash",
    "sua.phone",
    "sua.smd_offset",
)
EFFECTIVE = re.compile(r"Effective (\w+ \d{1,2}, \d{4}) - (\w+ \d{1,2}, \d{4})")
LABEL = re.compile(r"^(?P<name>[A-Za-z .]+?)(?: - (?P<qualifier>.+?))?(?P<marks>\**)$")
SIZE_RANGE = re.compile(r"^(\d+)(?: to (\d+))? members?$")
SIZE_OPEN = re.compile(r"^(\d+) (?:or more members?|members? \+)$")
PENDING = "-"


def parse(snapshot: Snapshot) -> list[Row]:
    import openpyxl

    path = snapshot.file(".xlsx")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows = [tuple(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()
    return parse_rows(rows)


def parse_rows(rows: list[tuple]) -> list[Row]:
    """Parse the FNS SUA table given as spreadsheet rows (row 1 = title)."""
    if len(rows) < 4 or "Standard Utility Allowances" not in str(rows[0][0]):
        raise ParseError("first row isn't the SUA table title")
    match = EFFECTIVE.search(str(rows[1][0]))
    if not match:
        raise ParseError(f"row 2 doesn't give the effective dates: {rows[1][0]!r}")
    period = datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat()
    header = tuple(" ".join(str(c).split()) for c in rows[2][: len(HEADER)])
    if header != HEADER:
        raise ParseError(f"columns changed: {header}")

    data_rows, legend_rows = [], []
    for line, row in enumerate(rows[3:], start=4):
        label = row[0]
        if label is None:
            continue
        label = " ".join(str(label).split())
        if label.startswith("*") or label.startswith("Note:"):
            legend_rows.append((line, label))
        elif legend_rows:
            raise ParseError(f"line {line}: data row {label!r} after the footnotes")
        else:
            data_rows.append((line, label, row[1 : len(HEADER)]))
    legend = _legend(legend_rows)

    out: list[Row] = []
    for line, label, values in data_rows:
        region, sizes, marks = _label(label, line)
        for column, parameter, raw in zip(HEADER[1:], PARAMETERS, values):
            value = _amount(raw, line, column)
            for size in sizes:
                out.append(Row("snap", parameter, region, value, "usd_per_month", str(raw),
                               f"line {line} ({label}), column {column!r}", size, period))
        if marks:
            if marks not in legend:
                raise ParseError(f"line {line}: footnote {marks!r} isn't explained under the table")
            out.append(Row("snap", "sua.footnote", region, None, "text", legend[marks],
                           f"line {line} ({label})", sizes[0], period))
    for line, text in legend_rows:
        if text.startswith("Note:"):
            out.append(Row("snap", "sua.note", "", None, "text", text, f"line {line}", None, period))
    return out


def _legend(rows: list[tuple[int, str]]) -> dict[str, str]:
    legend = {}
    for _, text in rows:
        marks = re.match(r"^\*+", text)
        if marks:
            legend[marks.group(0)] = text[len(marks.group(0)):].strip()
    return legend


def _label(label: str, line: int) -> tuple[str, list[int | None], str]:
    """'Arizona - 1 to 3 members' -> ('AZ', [1, 2, 3], ''); 'Guam - 13 member +*' -> ('GU', [13], '*')."""
    match = LABEL.match(label)
    if not match or match.group("name").strip() not in STATE_CODES:
        raise ParseError(f"line {line}: unknown region {label!r}")
    name, qualifier, marks = match.group("name").strip(), match.group("qualifier"), match.group("marks")
    if qualifier is None:
        return STATE_CODES[name], [None], marks
    if (name, qualifier) in SNAP_AREAS:
        return SNAP_AREAS[(name, qualifier)], [None], marks
    if size := SIZE_RANGE.match(qualifier):
        low, high = int(size.group(1)), int(size.group(2) or size.group(1))
        return STATE_CODES[name], list(range(low, high + 1)), marks
    if size := SIZE_OPEN.match(qualifier):
        # "N or more": recorded at size N; the location column keeps the original wording.
        return STATE_CODES[name], [int(size.group(1))], marks
    raise ParseError(f"line {line}: can't read area or household size from {label!r}")


def _amount(raw, line: int, column: str) -> float | None:
    if raw == PENDING:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    raise ParseError(f"line {line}, column {column!r}: expected an amount, got {raw!r}")
