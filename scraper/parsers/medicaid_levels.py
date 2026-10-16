from __future__ import annotations

import csv
import re

from scraper.extract import ParseError, Row, Snapshot
from scraper.parsers.regions import STATE_CODES

# Column -> (program, parameter). Limits are % of the federal poverty level.
LIMIT_COLUMNS = {
    "Medicaid Ages 0-1": ("medicaid", "income_limit.infant"),
    "Medicaid Ages 1-5": ("medicaid", "income_limit.child_1_5"),
    "Medicaid Ages 6-18": ("medicaid", "income_limit.child_6_18"),
    "Separate CHIP": ("chip", "income_limit.child"),
    "Pregnant Women Medicaid": ("medicaid", "income_limit.pregnant"),
    "Pregnant Women CHIP": ("chip", "income_limit.pregnant"),
    "Parent/Caretaker": ("medicaid", "income_limit.parent"),
    "Expansion to Adults": ("medicaid", "income_limit.expansion_adult"),
}
TEXT_COLUMNS = {
    "Notes": ("medicaid", "notes"),
    "Separate CHIP Ages": ("chip", "child_age_range"),
    "Parent/Caretaker Income Standard": ("medicaid", "income_limit.parent.basis"),
}
EXPECTED_HEADER = {"State", *LIMIT_COLUMNS, *TEXT_COLUMNS}
NOT_APPLICABLE = {"N/A", "No"}  # "No" in Expansion to Adults: the state hasn't expanded
PERCENT = re.compile(r"^(\d+(?:\.\d+)?)%$")


def parse(snapshot: Snapshot) -> list[Row]:
    path = snapshot.file(".csv")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = set(reader.fieldnames or [])
        if header != EXPECTED_HEADER:
            raise ParseError(
                f"{path.name}: columns changed; missing {sorted(EXPECTED_HEADER - header)}, "
                f"unexpected {sorted(header - EXPECTED_HEADER)}"
            )
        rows: list[Row] = []
        for line, record in enumerate(reader, start=2):
            state = record["State"].strip()
            region = STATE_CODES.get(state)
            if region is None:
                raise ParseError(f"{path.name} line {line}: unknown state {state!r}")
            for column, (program, parameter) in LIMIT_COLUMNS.items():
                raw = record[column].strip()
                rows.append(Row(program, parameter, region, _percent(raw, path.name, line, column),
                                "pct_fpl", raw, f"line {line}, column {column!r}"))
            for column, (program, parameter) in TEXT_COLUMNS.items():
                raw = record[column].strip()
                if raw:
                    rows.append(Row(program, parameter, region, None, "text", raw, f"line {line}, column {column!r}"))
    return rows


def _percent(raw: str, filename: str, line: int, column: str) -> float | None:
    if raw in NOT_APPLICABLE:
        return None
    match = PERCENT.match(raw)
    if not match:
        raise ParseError(f"{filename} line {line}, column {column!r}: can't read {raw!r} as a percentage")
    return float(match.group(1))
