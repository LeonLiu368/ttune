import csv
import json
import shutil
from pathlib import Path

import pytest

from scraper.extract import ParseError, Row, extract_source
from scraper.parsers import PARSERS

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOT = "raw/medicaid-eligibility-levels/2026-10-09"
CSV_NAME = "medicaid-and-chip-eligibility-levels.xy8t-auhk.csv"


def make_snapshot(data_dir: Path, csv_text: str | None = None) -> dict:
    snapshot = data_dir / SNAPSHOT
    snapshot.mkdir(parents=True)
    if csv_text is None:
        shutil.copy(FIXTURES / "medicaid_levels_sample.csv", snapshot / CSV_NAME)
    else:
        (snapshot / CSV_NAME).write_text(csv_text)
    (snapshot / "_fetch.json").write_text(json.dumps({"files": [{"file": CSV_NAME}]}))
    return {"id": "medicaid-eligibility-levels", "kind": ["rules"], "latest_snapshot": SNAPSHOT,
            "fetch": {"type": "direct", "urls": ["https://download.medicaid.gov/x.csv"]}}


def read_rows(data_dir: Path) -> list[dict]:
    with (data_dir / "processed/medicaid-eligibility-levels.csv").open() as fh:
        return list(csv.DictReader(fh))


def find(rows, region, parameter, program="medicaid"):
    return next(r for r in rows if r["region"] == region and r["parameter"] == parameter and r["program"] == program)


def test_medicaid_levels_parses_limits_and_text(tmp_path):
    source = make_snapshot(tmp_path)

    result = extract_source(source, tmp_path, PARSERS)

    assert result == {"id": source["id"], "result": "ok", "rows": result["rows"],
                      "output": "processed/medicaid-eligibility-levels.csv"}
    rows = read_rows(tmp_path)
    assert {r["region"] for r in rows} == {"AL", "AR", "HI", "NC"}
    assert all(r["snapshot"] == SNAPSHOT for r in rows)

    infant = find(rows, "AL", "income_limit.infant")
    assert (infant["value"], infant["unit"], infant["raw"]) == ("141.0", "pct_fpl", "141%")
    not_expanded = find(rows, "AL", "income_limit.expansion_adult")
    assert (not_expanded["value"], not_expanded["raw"]) == ("", "No")
    no_chip = find(rows, "AL", "income_limit.pregnant", program="chip")
    assert (no_chip["value"], no_chip["raw"]) == ("", "N/A")
    assert find(rows, "NC", "child_age_range", program="chip")["raw"] == "6 up to 19"
    assert "Alaska and Hawaii" in find(rows, "HI", "notes")["raw"]
    assert find(rows, "AR", "income_limit.parent.basis")["raw"] == "Dollars"


def test_medicaid_levels_rejects_changed_columns(tmp_path):
    source = make_snapshot(tmp_path, "State,Notes,Something New\nAlabama,,1%\n")

    with pytest.raises(ParseError, match="columns changed"):
        extract_source(source, tmp_path, PARSERS)


def test_medicaid_levels_rejects_unreadable_value(tmp_path):
    text = (FIXTURES / "medicaid_levels_sample.csv").read_text().replace("141%", "about 141", 1)
    source = make_snapshot(tmp_path, text)

    with pytest.raises(ParseError, match="can't read 'about 141'"):
        extract_source(source, tmp_path, PARSERS)


def test_sources_without_parser_or_snapshot_are_reported(tmp_path):
    scraped = {"type": "direct", "urls": ["https://x.gov/a"]}
    assert extract_source({"id": "pe"}, tmp_path, PARSERS)["result"] == "fetched by hand, not extracted"
    assert extract_source({"id": "x", "fetch": scraped}, tmp_path, PARSERS)["result"] == "no snapshot"
    assert extract_source({"id": "x", "fetch": scraped, "latest_snapshot": "raw/x/1"}, tmp_path, PARSERS)["result"] == "no parser yet"
    template = {"id": "w2", "fetch": scraped, "kind": ["templates"], "latest_snapshot": "raw/w2/1"}
    assert extract_source(template, tmp_path, PARSERS)["result"] == "template, nothing to parse"


def test_parser_returning_nothing_is_an_error(tmp_path):
    source = make_snapshot(tmp_path)

    with pytest.raises(ParseError, match="no rows"):
        extract_source(source, tmp_path, {source["id"]: lambda snapshot: []})


def test_row_defaults():
    row = Row("snap", "max_allotment", "CONTIGUOUS_US", 306.0, "usd_per_month", "$306", "table 1")
    assert row.household_size is None and row.period == ""
