from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from scraper.fetch import META_FILE


class ParseError(Exception):
    pass


@dataclass(frozen=True)
class Row:
    """One value from an official source, in a shape every parser shares so `check` can compare them."""

    program: str  # snap, medicaid, chip, eitc, wic, fpg
    parameter: str  # dotted name, e.g. income_limit.infant
    region: str  # state postal code, a federal region like CONTIGUOUS_US, or "" for national
    value: float | None  # None when the source says N/A, No, etc.; the original text is in raw
    unit: str  # pct_fpl, usd_per_month, usd_per_year, text, ...
    raw: str  # the cell or text exactly as it appeared
    location: str  # where in the file, so a human can check it
    household_size: int | None = None
    period: str = ""  # effective date or fiscal year if the source states one


@dataclass(frozen=True)
class Snapshot:
    path: Path
    meta: dict

    def file(self, suffix: str) -> Path:
        matches = [self.path / f["file"] for f in self.meta["files"] if f["file"].lower().endswith(suffix)]
        if len(matches) != 1:
            raise ParseError(f"expected one {suffix} file in {self.path}, found {len(matches)}")
        return matches[0]


Parser = Callable[[Snapshot], list[Row]]

COLUMNS = ["source_id", "snapshot", *(f.name for f in fields(Row))]


def extract_source(source: dict, data_dir: Path, parsers: dict[str, Parser]) -> dict:
    """Parse a source's latest snapshot into data/processed/<id>.csv and return a result row."""
    source_id = source["id"]
    snapshot_rel = source.get("latest_snapshot")
    if not source.get("fetch"):
        return {"id": source_id, "result": "fetched by hand, not extracted", "rows": 0, "output": ""}
    if not snapshot_rel:
        return {"id": source_id, "result": "no snapshot", "rows": 0, "output": ""}
    if source.get("kind") == ["templates"]:
        return {"id": source_id, "result": "template, nothing to parse", "rows": 0, "output": ""}
    parser = parsers.get(source_id)
    if parser is None:
        return {"id": source_id, "result": "no parser yet", "rows": 0, "output": ""}

    snapshot_dir = data_dir / snapshot_rel
    snapshot = Snapshot(snapshot_dir, json.loads((snapshot_dir / META_FILE).read_text()))
    rows = parser(snapshot)
    if not rows:
        raise ParseError(f"{source_id}: parser produced no rows from {snapshot_rel}")

    out = data_dir / "processed" / f"{source_id}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"source_id": source_id, "snapshot": snapshot_rel, **asdict(row)})
    return {"id": source_id, "result": "ok", "rows": len(rows), "output": out.relative_to(data_dir).as_posix()}
