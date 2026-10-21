from __future__ import annotations

import re

from scraper.extract import ParseError, Row, Snapshot

# "2026 Poverty Guidelines for the 48 Contiguous States and the District of Columbia", "... for Alaska", "... for Hawaii"
TABLE = re.compile(r"(\d{4}) Poverty Guidelines for (the 48 Contiguous States|Alaska|Hawaii)")
REGIONS = {"the 48 Contiguous States": "CONTIGUOUS_US", "Alaska": "AK", "Hawaii": "HI"}
SIZE_ROW = re.compile(r"^\s*(\d)\.{3,}\s+\$?([\d,]+)\s*$")
ADDITIONAL = re.compile(r"more than 8 persons, add \$([\d,]+) for\s+each additional person")
TAGS = re.compile(r"<[^>]+>")


def parse(snapshot: Snapshot) -> list[Row]:
    return parse_text(snapshot.file(".txt").read_text(encoding="utf-8"))


def parse_text(text: str) -> list[Row]:
    """Parse the three guideline tables from HHS's annual Federal Register notice (plain-text version)."""
    text = TAGS.sub("", text)
    starts = list(TABLE.finditer(text))
    if len(starts) != 3:
        raise ParseError(f"expected 3 poverty guideline tables, found {len(starts)}")
    rows: list[Row] = []
    for i, start in enumerate(starts):
        year, region = start.group(1), REGIONS[start.group(2)]
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        block = text[start.start():end]
        sizes = {}
        for line_no, line in enumerate(block.splitlines()):
            match = SIZE_ROW.match(line)
            if match:
                sizes[int(match.group(1))] = (match.group(2), line.strip())
        if sorted(sizes) != list(range(1, 9)):
            raise ParseError(f"{region} table: expected sizes 1-8, found {sorted(sizes)}")
        extra = ADDITIONAL.search(" ".join(block.split()))
        if not extra:
            raise ParseError(f"{region} table: no 'add $X for each additional person' sentence")
        where = f"table '{start.group(0)}'"
        for size, (amount, raw) in sorted(sizes.items()):
            rows.append(Row("fpg", "guideline", region, _dollars(amount), "usd_per_year", raw, where, size, year))
        rows.append(Row("fpg", "first_person", region, _dollars(sizes[1][0]), "usd_per_year", sizes[1][1], where, None, year))
        rows.append(Row("fpg", "additional_person", region, _dollars(extra.group(1)), "usd_per_year",
                        extra.group(0), where, None, year))
    return rows


def _dollars(text: str) -> float:
    return float(text.replace(",", ""))
