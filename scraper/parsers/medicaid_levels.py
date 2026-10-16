from __future__ import annotations

import csv
import re

from scraper.extract import ParseError, Row, Snapshot

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

STATE_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


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
