import csv
from dataclasses import fields
from pathlib import Path

import pytest

from scraper.__main__ import main
from scraper.check import PE_ROOT, PolicyEngine, compare_eitc, compare_medicaid, compare_sua
from scraper.extract import Row

PE_FILES = {
    "hhs/medicaid/eligibility/categories/infant/income_limit.yaml": "AL:\n  2018-01-01: 1.46\n",
    "hhs/medicaid/eligibility/categories/adult/income_limit.yaml":
        "AL:\n  2018-01-01: -.inf\nDC:\n  2018-01-01: 2.15\n  2026-01-01: 1.38\n",
    "usda/snap/income/deductions/utility/standard/main.yaml": "AL:\n  2024-10-01: 609\n  2025-10-01: 637\n",
    "usda/snap/income/deductions/utility/standard/by_household_size/amount.yaml":
        "AZ:\n  1:\n    2025-10-01: 323\n  4:\n    2025-10-01: 438\n",
    "usda/snap/income/deductions/utility/single/phone.yaml": "NC:\n  2025-10-01: 42\n",
    "irs/credits/eitc/max.yaml": """
brackets:
  - threshold:
      0000-01-01: 0
    amount:
      values:
        2026-01-01: 664
  - threshold:
      0000-01-01: 1
    amount:
      values:
        2026-01-01: 4_427
  - threshold:
      0000-01-01: 3
    amount:
      values:
        2026-01-01: 8_231
""",
    "irs/credits/eitc/phase_out/start.yaml": """
brackets:
  - threshold:
      values:
        0000-01-01: 0
    amount:
      values:
        2026-01-01: 10_860
  - threshold:
      values:
        0000-01-01: 1
    amount:
      values:
        2026-01-01: 23_890
""",
    "irs/credits/eitc/phase_out/joint_bonus.yaml": """
brackets:
  - threshold:
      0000-01-01: 0
    amount:
      2026-01-01: 7_280
  - threshold:
      0000-01-01: 1
    amount:
      2026-01-01: 7_270
""",
    "irs/credits/eitc/phase_in_rate.yaml": """
brackets:
  - threshold:
      0000-01-01: 0
    amount:
      2018-01-01: 0.0765
  - threshold:
      0000-01-01: 1
    amount:
      2018-01-01: 0.34
""",
    "irs/credits/eitc/phase_out/rate.yaml": """
brackets:
  - threshold:
      0000-01-01: 0
    amount:
      2018-01-01: 0.0765
  - threshold:
      0000-01-01: 1
    amount:
      2018-01-01: 0.1598
""",
    "irs/credits/eitc/phase_out/max_investment_income.yaml": "values:\n  2026-01-01: 12_200\n",
}
COLUMNS = ["source_id", "snapshot", *(f.name for f in fields(Row))]


@pytest.fixture
def data_dir(tmp_path):
    root = tmp_path / PE_ROOT
    for rel, text in PE_FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return tmp_path


@pytest.fixture
def pe(data_dir):
    return PolicyEngine(data_dir / PE_ROOT)


def row(source_id, program, parameter, region, value, raw, unit="usd_per_month", size="", period="",
        snapshot="raw/x/2026-10-16"):
    return {"source_id": source_id, "snapshot": snapshot, "program": program, "parameter": parameter,
            "region": region, "value": value, "unit": unit, "raw": raw, "location": "", "household_size": size,
            "period": period}


def by_param(results):
    return {(r.parameter, r.region, r.household_size): r for r in results}


def test_medicaid_adds_disregard_and_reads_not_covered(pe):
    rows = [
        row("m", "medicaid", "income_limit.infant", "AL", "141.0", "141%", "pct_fpl"),
        row("m", "medicaid", "income_limit.expansion_adult", "AL", "", "No", "pct_fpl"),
        row("m", "medicaid", "income_limit.expansion_adult", "DC", "210.0", "210%", "pct_fpl"),
        row("m", "chip", "income_limit.child", "AL", "312.0", "312%", "pct_fpl"),
        row("m", "medicaid", "notes", "AL", "", "some note", "text"),
    ]

    results = by_param(compare_medicaid(rows, pe))

    assert results[("income_limit.infant", "AL", "")].status == "match"
    assert results[("income_limit.expansion_adult", "AL", "")].status == "match"
    dc = results[("income_limit.expansion_adult", "DC", "")]
    assert (dc.status, dc.policyengine) == ("differ", "1.38")
    assert "2.15" in dc.note
    assert results[("income_limit.child", "AL", "")].status == "missing in PolicyEngine"
    assert ("notes", "AL", "") not in results


def test_sua_uses_household_size_files_and_flags_cents(pe):
    rows = [
        row("s", "snap", "sua.heating_cooling", "AL", "637.0", "637", period="2025-10-01"),
        row("s", "snap", "sua.heating_cooling", "AZ", "323.0", "323", size="1", period="2025-10-01"),
        row("s", "snap", "sua.heating_cooling", "AZ", "438.0", "438", size="4", period="2025-10-01"),
        row("s", "snap", "sua.phone", "NC", "42.11", "42.11", size="1", period="2025-10-01"),
        row("s", "snap", "sua.smd_offset", "AL", "4.0", "4", period="2025-10-01"),
        row("s", "snap", "sua.heating_cooling", "NJ", "", "-", period="2025-10-01"),
        row("s", "snap", "sua.footnote", "NJ", "", "Pending", "text", period="2025-10-01"),
    ]

    results = by_param(compare_sua(rows, pe))

    assert results[("sua.heating_cooling", "AL", "")].status == "match"
    assert results[("sua.heating_cooling", "AZ", "1")].status == "match"
    assert results[("sua.heating_cooling", "AZ", "4")].status == "match"
    assert "by_household_size" in results[("sua.heating_cooling", "AZ", "1")].policyengine_file
    nc = results[("sua.phone", "NC", "1")]
    assert (nc.status, nc.note) == ("differ", "under $1 apart; FNS gives cents")
    assert results[("sua.smd_offset", "AL", "")].status == "missing in PolicyEngine"
    nj = results[("sua.heating_cooling", "NJ", "")]
    assert (nj.status, nj.note) == ("no official value", "Pending")


def eitc_rows(**overrides):
    values = {
        "eitc.max_credit.children_0": 664, "eitc.max_credit.children_3": 8231,
        "eitc.phaseout_start.other.children_2": 23890, "eitc.phaseout_start.joint.children_1": 31160,
        "eitc.earned_income_amount.children_1": 13020, "eitc.phaseout_end.other.children_1": 51593,
        "eitc.phaseout_end.joint.children_0": 26820, "eitc.investment_income_limit": 12200,
    }
    values.update(overrides)
    return [row("e", "eitc", p, "", str(float(v)), f"${v:,}", "usd_per_year", period="2026") for p, v in values.items()]


def test_eitc_matches_direct_bracketed_and_derived_values(pe):
    results = compare_eitc(eitc_rows(), pe)

    assert {r.parameter: r.status for r in results} == {r.parameter: "match" for r in results}
    derived = next(r for r in results if r.parameter == "eitc.earned_income_amount.children_1")
    assert derived.note.startswith("derived")


def test_eitc_reports_a_real_difference(pe):
    results = by_param(compare_eitc(eitc_rows(**{"eitc.max_credit.children_3": 9000}), pe))

    wrong = results[("eitc.max_credit.children_3", "", "")]
    assert (wrong.status, wrong.policyengine) == ("differ", "8231")


def write_processed(data_dir: Path, source_id: str, rows: list[dict]):
    path = data_dir / "processed" / f"{source_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_cli_writes_reports_and_summary(data_dir, capsys):
    write_processed(data_dir, "irs-eitc-rp-25-32",
                    [dict(r, source_id="irs-eitc-rp-25-32") for r in eitc_rows(**{"eitc.max_credit.children_0": 700})])

    assert main(["--data-dir", str(data_dir), "check"]) == 0

    out = capsys.readouterr().out
    assert "irs-eitc-rp-25-32: 7 match, 1 differ" in out
    assert "medicaid-eligibility-levels: not extracted yet" in out
    summary = (data_dir / "processed/checks/summary.md").read_text()
    assert "| `irs-eitc-rp-25-32` | 7 | 1 | 0 | 0 |" in summary
    assert "eitc.max_credit.children_0" in summary
    report = list(csv.DictReader((data_dir / "processed/checks/irs-eitc-rp-25-32.csv").open()))
    assert len(report) == 8


def test_cli_rejects_source_without_comparison(data_dir, capsys):
    assert main(["--data-dir", str(data_dir), "check", "--source", "irs-form-w2"]) == 2
