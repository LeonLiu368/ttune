from __future__ import annotations

import re

from scraper.extract import ParseError, Row, Snapshot

SECTION = re.compile(r"\.\d{2} Earned Income Credit\.")
TAX_YEAR = re.compile(
    r"For taxable years beginning in (\d{4}), the following amounts are\s+used to determine the earned income credit"
)
COLUMNS = re.compile(r"Item One Two Three or More None")
END = re.compile(r"The instructions for the Form 1040")
INVESTMENT = re.compile(r"investment income exceeds \$([\d,]+)\.")
AMOUNT = re.compile(r"\$([\d,]+)")
CHILDREN = (1, 2, 3, 0)  # table column order; 3 means "three or more"
COLUMN_NAMES = {1: "One", 2: "Two", 3: "Three or More", 0: "None"}

ITEMS = {
    "Earned Income Amount": "eitc.earned_income_amount",
    "Maximum Amount of Credit": "eitc.max_credit",
    "Threshold Phaseout Amount (Married Filing Jointly)": "eitc.phaseout_start.joint",
    "Completed Phaseout Amount (Married Filing Jointly)": "eitc.phaseout_end.joint",
    "Threshold Phaseout Amount (All other filing statuses)": "eitc.phaseout_start.other",
    "Completed Phaseout Amount (All other filing statuses)": "eitc.phaseout_end.other",
}


def parse(snapshot: Snapshot) -> list[Row]:
    import pdfplumber

    with pdfplumber.open(snapshot.file(".pdf")) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return parse_pages(pages)


def parse_pages(pages: list[str]) -> list[Row]:
    """Parse the EITC section of an IRS inflation-adjustment Rev. Proc., given each page's text."""
    start = next((i for i, text in enumerate(pages) if SECTION.search(text)), None)
    if start is None:
        raise ParseError("no 'Earned Income Credit' section found")
    text = "\n".join(pages[start : start + 3])
    text = text[SECTION.search(text).start() :]

    year = TAX_YEAR.search(text)
    columns = COLUMNS.search(text)
    end = END.search(text)
    investment = INVESTMENT.search(text)
    if not year:
        raise ParseError("EITC section doesn't state the taxable year")
    if not columns or not end or end.start() < columns.end():
        raise ParseError("EITC table header or end marker not found")
    if not investment:
        raise ParseError("excessive investment income limit not found")
    period = year.group(1)

    items = _table_rows(text[columns.end() : end.start()])
    if set(items) != set(ITEMS):
        raise ParseError(f"EITC table rows changed: found {sorted(items)}")

    rows = [
        Row("eitc", f"{ITEMS[label]}.children_{children}", "", _usd(raw), "usd_per_year", f"${raw}",
            f"EITC table, row {label!r}, column {COLUMN_NAMES[children]!r}", None, period)
        for label, amounts in items.items()
        for children, raw in zip(CHILDREN, amounts)
    ]
    rows.append(Row("eitc", "eitc.investment_income_limit", "", _usd(investment.group(1)), "usd_per_year",
                    f"${investment.group(1)}", "EITC section, excessive investment income", None, period))
    return rows


def _table_rows(table: str) -> dict[str, list[str]]:
    """Group lines into labelled rows. A label can wrap onto following lines that carry no amounts,
    e.g. 'Completed Phaseout $58,863 ...' / 'Amount (Married Filing' / 'Jointly)'."""
    rows: dict[str, list[str]] = {}
    label: list[str] = []
    amounts: list[str] | None = None
    for line in filter(None, (line.strip() for line in table.splitlines())):
        found = AMOUNT.findall(line)
        if not found:
            if amounts is not None:
                label.append(line)
            continue
        if len(found) != len(CHILDREN):
            raise ParseError(f"expected {len(CHILDREN)} amounts in {line!r}")
        if amounts is not None:
            rows[" ".join(label)] = amounts
        label, amounts = [line[: line.index("$")].strip()], found
    if amounts is not None:
        rows[" ".join(label)] = amounts
    return rows


def _usd(raw: str) -> float:
    return float(raw.replace(",", ""))
