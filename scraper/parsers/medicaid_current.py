from __future__ import annotations

import re
from html.parser import HTMLParser

from scraper.extract import ParseError, Row, Snapshot
from scraper.parsers.medicaid_levels import LIMIT_COLUMNS
from scraper.parsers.regions import STATE_CODES

# Column headers on Medicaid.gov (footnote markers removed) -> the same (program, parameter) as the 2018 CSV.
COLUMNS = dict(zip(
    ["Children Medicaid Ages 0-1", "Children Medicaid Ages 1-5", "Children Medicaid Ages 6-18",
     "Children Separate CHIP", "Pregnant Women Medicaid", "Pregnant Women CHIP",
     "Adults (Medicaid) Parent/ Caretaker", "Adults (Medicaid) Expansion to Adults"],
    LIMIT_COLUMNS.values(),
))
AS_OF = re.compile(r"as of (\w+ \d{1,2}, \d{4})")
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], start=1)}
# "141%", "130%($)" (state uses dollar amounts), "212% (1 up to 19)" (age range)
PERCENT = re.compile(r"^(\d+(?:\.\d+)?)%\s*(\(\$\))?\s*(\(.*\))?$")


class _Table(HTMLParser):
    """Collects the first table's rows as text, skipping <sup> footnote markers."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.caption = ""
        self._row: list[str] | None = None
        self._cell: str | None = None
        self._in_caption = self._done = False
        self._sup = 0

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        if tag == "sup":
            self._sup += 1
        elif tag == "caption":
            self._in_caption = True
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = ""

    def handle_endtag(self, tag):
        if self._done:
            return
        if tag == "sup":
            self._sup -= 1
        elif tag == "caption":
            self._in_caption = False
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join(self._cell.split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._done = True

    def handle_data(self, data):
        if self._done or self._sup:
            return
        if self._in_caption:
            self.caption += data
        if self._cell is not None:
            self._cell += data


def parse(snapshot: Snapshot) -> list[Row]:
    return parse_html(snapshot.file(".html").read_text(encoding="utf-8"))


def parse_html(html: str, min_states: int = 51) -> list[Row]:
    """Parse Medicaid.gov's table of MAGI income eligibility standards by state."""
    table = _Table()
    table.feed(html)
    if not table.rows:
        raise ParseError("no table found")
    header, *body = table.rows
    if header[0] != "State" or header[1:] != list(COLUMNS):
        raise ParseError(f"columns changed: {header}")
    as_of = AS_OF.search(" ".join(table.caption.split()))
    if not as_of:
        raise ParseError(f"no 'as of <date>' in the caption: {table.caption!r}")
    month, day, year = as_of.group(1).replace(",", "").split()
    period = f"{year}-{MONTHS[month]:02d}-{int(day):02d}"

    rows: list[Row] = []
    for n, record in enumerate(body, start=1):
        state, cells = record[0], record[1:]
        region = STATE_CODES.get(state)
        if region is None or len(cells) != len(COLUMNS):
            raise ParseError(f"table row {n}: can't read {record}")
        for column, raw in zip(COLUMNS, cells):
            program, parameter = COLUMNS[column]
            value, note = _value(raw)
            location = f"table row {n} ({state}), column {column!r}"
            rows.append(Row(program, parameter, region, value, "pct_fpl", raw, location, None, period))
            if note:
                rows.append(Row(program, f"{parameter}.note", region, None, "text", note, location, None, period))
    if len(body) < min_states:
        raise ParseError(f"expected {min_states} states, got {len(body)} rows")
    return rows


def _value(raw: str) -> tuple[float | None, str]:
    """(percent of FPL or None, note). N/A, No and 'See note' have no number."""
    if raw == "N/A" or raw.startswith("No") or raw.startswith("See note"):
        return None, "" if raw in ("N/A", "No") else raw
    match = PERCENT.match(raw)
    if not match:
        raise ParseError(f"can't read {raw!r} as a percentage")
    notes = []
    if match.group(2):
        notes.append("state uses dollar amounts by household size; CMS converted to % FPL")
    if match.group(3):
        notes.append(f"ages {match.group(3).strip('()')}")
    return float(match.group(1)), "; ".join(notes)
