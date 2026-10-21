"""Compare parsed official values (data/processed) with PolicyEngine's parameters."""

from __future__ import annotations

import csv
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import yaml

PE_ROOT = Path("raw/policyengine-us/parameters/gov")


class _StringDates(yaml.SafeLoader):
    """Keep dates as strings: PolicyEngine uses 0000-01-01, which yaml's date type rejects."""


_StringDates.yaml_implicit_resolvers = {
    key: [r for r in resolvers if r[0] != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class PolicyEngine:
    def __init__(self, root: Path):
        self.root = root
        self._cache: dict[str, dict | None] = {}

    def load(self, rel: str) -> dict | None:
        if rel not in self._cache:
            path = self.root / rel
            self._cache[rel] = yaml.load(path.read_text(), Loader=_StringDates) if path.is_file() else None
        return self._cache[rel]

    def value(self, rel: str, date: str, *keys) -> float | None:
        node = self.load(rel)
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        return at(node, date)

    def bracket(self, rel: str, count: int, date: str) -> float | None:
        """Value of the bracket that applies to `count` (brackets mean "this many or more")."""
        data = self.load(rel)
        if not data:
            return None
        best = None
        for bracket in data.get("brackets", []):
            threshold = at(bracket["threshold"], date)
            if threshold is not None and threshold <= count and (best is None or threshold > best[0]):
                best = (threshold, at(bracket["amount"], date))
        return best[1] if best else None


def at(series, date: str):
    """The value in effect on `date` from a {date: value} mapping (optionally nested under 'values')."""
    if isinstance(series, dict) and "values" in series:
        series = series["values"]
    if not isinstance(series, dict):
        return None
    dates = sorted(k for k in series if isinstance(k, str) and k[:4].isdigit() and k <= date)
    return series[dates[-1]] if dates else None


@dataclass(frozen=True)
class Result:
    source_id: str
    parameter: str
    region: str
    household_size: str
    period: str
    official: str
    policyengine: str
    status: str  # match | differ | missing in PolicyEngine | no official value
    policyengine_file: str
    note: str = ""


Comparison = Callable[[list[dict], PolicyEngine], list[Result]]
STATUSES = ("match", "differ", "missing in PolicyEngine", "no official value")


def _num(text: str) -> float | None:
    return float(text) if text not in ("", None) else None


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isinf(value):
        return "not covered (-inf)"
    return f"{value:g}" if isinstance(value, float) else str(value)


def _result(row: dict, official, pe_value, status: str, rel: str, note: str = "") -> Result:
    return Result(row["source_id"], row["parameter"], row["region"], row.get("household_size", ""),
                  row["period"], official, _fmt(pe_value), status, rel, note)


# --- Medicaid / CHIP eligibility levels -------------------------------------------------------

MEDICAID_CATEGORIES = {
    "income_limit.infant": "infant",
    "income_limit.child_1_5": "young_child",
    "income_limit.child_6_18": "older_child",
    "income_limit.pregnant": "pregnant",
    "income_limit.parent": "parent",
    "income_limit.expansion_adult": "adult",
}
# Medicaid.gov lists limits without the 5-point MAGI income disregard; PolicyEngine includes it.
MAGI_DISREGARD = 5


def compare_medicaid(rows: list[dict], pe: PolicyEngine) -> list[Result]:
    results = []
    for row in rows:
        if row["unit"] == "text":
            continue
        if row["program"] == "chip":
            results.append(_result(row, row["raw"], None, "missing in PolicyEngine", "",
                                   "CHIP parameters aren't in the downloaded PolicyEngine files"))
            continue
        category = MEDICAID_CATEGORIES[row["parameter"]]
        rel = f"hhs/medicaid/eligibility/categories/{category}/income_limit.yaml"
        # Use the date the source states; the 2018 CSV has none, so fall back to when it was fetched.
        date = row["period"] or row["snapshot"].rsplit("/", 1)[-1][:10]
        pe_value = pe.value(rel, date, row["region"])
        official = _num(row["value"])
        not_covered = pe_value is None or (isinstance(pe_value, float) and math.isinf(pe_value))
        if official is None:
            status = "match" if not_covered else "differ"
            note = "neither covers this group" if not_covered else f"official says {row['raw']!r}"
        elif pe_value is None:
            status, note = "missing in PolicyEngine", ""
        else:
            expected = (official + MAGI_DISREGARD) / 100
            status = "match" if not_covered is False and abs(pe_value - expected) < 0.0005 else "differ"
            note = f"official {row['raw']} + {MAGI_DISREGARD}-point disregard = {expected:g}"
        results.append(_result(row, row["raw"], pe_value, status, rel, note))
    return results


# --- SNAP standard utility allowances --------------------------------------------------------

SUA_DIR = "usda/snap/income/deductions/utility/"
SUA_FILES = {
    "sua.heating_cooling": ("standard/main.yaml", "standard/by_household_size/amount.yaml"),
    "sua.basic_limited": ("limited/main.yaml", "limited/by_household_size/amount.yaml"),
    "sua.electricity": ("single/electricity.yaml", "single/by_household_size/electricity.yaml"),
    "sua.gas_fuel": ("single/gas_and_fuel.yaml", "single/by_household_size/gas_and_fuel.yaml"),
    "sua.water": ("single/water.yaml", "single/by_household_size/water.yaml"),
    "sua.sewage": ("single/sewage.yaml", None),
    "sua.trash": ("single/trash.yaml", None),
    "sua.phone": ("single/phone.yaml", None),
}


def compare_sua(rows: list[dict], pe: PolicyEngine) -> list[Result]:
    footnotes = {r["region"]: r["raw"] for r in rows if r["parameter"] == "sua.footnote"}
    results = []
    for row in rows:
        if row["unit"] == "text":
            continue
        if row["parameter"] not in SUA_FILES:
            results.append(_result(row, row["raw"], None, "missing in PolicyEngine", "",
                                   "PolicyEngine doesn't store this column"))
            continue
        main, by_size = SUA_FILES[row["parameter"]]
        size = row["household_size"]
        rel, pe_value = SUA_DIR + main, None
        if size and by_size and pe.load(SUA_DIR + by_size) and row["region"] in pe.load(SUA_DIR + by_size):
            rel = SUA_DIR + by_size
            pe_value = pe.value(rel, row["period"], row["region"], int(size))
        else:
            pe_value = pe.value(rel, row["period"], row["region"])
        official = _num(row["value"])
        footnote = footnotes.get(row["region"], "")
        if official is None:
            results.append(_result(row, row["raw"], pe_value, "no official value", rel, footnote))
        elif pe_value is None:
            results.append(_result(row, row["raw"], None, "missing in PolicyEngine", rel, footnote))
        else:
            gap = abs(official - pe_value)
            status = "match" if gap < 0.005 else "differ"
            note = "under $1 apart; FNS gives cents" if 0.005 <= gap < 1 else footnote
            results.append(_result(row, row["raw"], pe_value, status, rel, note))
    return results


# --- EITC (IRS Rev. Proc.) ---------------------------------------------------------------------

EITC = "irs/credits/eitc/"
DERIVED_TOLERANCE = 10  # the IRS rounds derived amounts to the nearest $10


def compare_eitc(rows: list[dict], pe: PolicyEngine) -> list[Result]:
    results = []
    for row in rows:
        date = f"{row['period']}-01-01"
        parameter = row["parameter"]
        official = _num(row["value"])
        if parameter == "eitc.investment_income_limit":
            rel = EITC + "phase_out/max_investment_income.yaml"
            pe_value = pe.value(rel, date)
            results.append(_exact(row, official, pe_value, rel))
            continue
        item, children = parameter.rsplit(".children_", 1)
        n = int(children)
        max_credit = pe.bracket(EITC + "max.yaml", n, date)
        start = pe.bracket(EITC + "phase_out/start.yaml", n, date)
        bonus = pe.bracket(EITC + "phase_out/joint_bonus.yaml", n, date)
        phase_in = pe.bracket(EITC + "phase_in_rate.yaml", n, date)
        phase_out = pe.bracket(EITC + "phase_out/rate.yaml", n, date)
        if item == "eitc.max_credit":
            results.append(_exact(row, official, max_credit, EITC + "max.yaml"))
        elif item == "eitc.phaseout_start.other":
            results.append(_exact(row, official, start, EITC + "phase_out/start.yaml"))
        elif item == "eitc.phaseout_start.joint":
            joint = None if start is None or bonus is None else start + bonus
            results.append(_exact(row, official, joint, EITC + "phase_out/start.yaml + joint_bonus.yaml",
                                  "phase-out start + joint bonus"))
        elif item == "eitc.earned_income_amount":
            derived = None if not max_credit or not phase_in else max_credit / phase_in
            results.append(_derived(row, official, derived, EITC + "max.yaml / phase_in_rate.yaml",
                                    "derived: max credit ÷ phase-in rate"))
        elif item in ("eitc.phaseout_end.other", "eitc.phaseout_end.joint"):
            begin = start if item.endswith("other") else (None if start is None or bonus is None else start + bonus)
            derived = None if begin is None or not max_credit or not phase_out else begin + max_credit / phase_out
            results.append(_derived(row, official, derived, EITC + "phase_out/start.yaml + max.yaml / rate.yaml",
                                    "derived: phase-out start + max credit ÷ phase-out rate"))
        else:
            results.append(_result(row, row["raw"], None, "missing in PolicyEngine", "", "no mapping for this item"))
    return results


def _exact(row: dict, official, pe_value, rel: str, note: str = "") -> Result:
    if pe_value is None:
        return _result(row, row["raw"], None, "missing in PolicyEngine", rel, note)
    status = "match" if abs(official - pe_value) < 0.5 else "differ"
    return _result(row, row["raw"], pe_value, status, rel, note)


def _derived(row: dict, official, derived, rel: str, note: str) -> Result:
    if derived is None:
        return _result(row, row["raw"], None, "missing in PolicyEngine", rel, note)
    status = "match" if abs(official - derived) <= DERIVED_TOLERANCE else "differ"
    return _result(row, row["raw"], round(derived, 2), status, rel, note)


# --- HHS poverty guidelines -------------------------------------------------------------------

FPG = "hhs/fpg.yaml"


def fpg(pe: PolicyEngine, region: str, size: int, date: str) -> float | None:
    first = pe.value(FPG, date, "first_person", region)
    extra = pe.value(FPG, date, "additional_person", region)
    return None if first is None or extra is None else first + (size - 1) * extra


def compare_fpg(rows: list[dict], pe: PolicyEngine) -> list[Result]:
    results = []
    for row in rows:
        date = f"{row['period']}-01-01"
        official = _num(row["value"])
        if row["parameter"] == "guideline":
            pe_value = fpg(pe, row["region"], int(row["household_size"]), date)
            results.append(_exact(row, official, pe_value, FPG, "first_person + (size - 1) × additional_person"))
        else:
            results.append(_exact(row, official, pe.value(FPG, date, row["parameter"], row["region"]), FPG))
    return results


# --- SNAP cost-of-living adjustments (FNS FY tables) -------------------------------------------

SNAP = "usda/snap/"
SHELTER_CAP_REGIONS = {"AK": "AK_URBAN"}  # PolicyEngine keys Alaska's shelter cap by SNAP region
INCOME_LIMIT_RATES = {"income_limit.net": "net", "income_limit.gross": "gross"}


def _snap_income_limit(pe: PolicyEngine, row: dict, date: str) -> tuple[float | None, str]:
    """PolicyEngine's monthly limit: rate × poverty guideline ÷ 12, rounded up to the next dollar (7 CFR 273.9)."""
    parameter = row["parameter"].removesuffix(".additional_person")
    rel = f"{SNAP}income/limit/{INCOME_LIMIT_RATES[parameter]}.yaml"
    rate = at(pe.load(rel), date)
    if row["parameter"].endswith(".additional_person"):
        annual = pe.value(FPG, date, "additional_person", row["region"])
    else:
        annual = fpg(pe, row["region"], int(row["household_size"]), date)
    if rate is None or annual is None:
        return None, rel
    return float(math.ceil(round(rate * annual / 12, 2))), f"{rel} × {FPG}"


def compare_cola(rows: list[dict], pe: PolicyEngine) -> list[Result]:
    results = []
    for row in rows:
        date = f"{int(row['period'].removeprefix('FY')) - 1}-10-01"  # FY2027 starts 2026-10-01
        parameter, region, official = row["parameter"], row["region"], _num(row["value"])
        size = int(row["household_size"]) if row["household_size"] else None
        if parameter == "max_allotment":
            rel = SNAP + "max_allotment.yaml"
            results.append(_exact(row, official, pe.value(rel, date, "main", region, size), rel))
        elif parameter == "max_allotment.additional_person":
            rel = SNAP + "max_allotment.yaml"
            results.append(_exact(row, official, pe.value(rel, date, "additional", region), rel))
        elif parameter == "standard_deduction":
            rel = SNAP + "income/deductions/standard.yaml"
            results.append(_exact(row, official, pe.value(rel, date, region, size), rel))
        elif parameter == "excess_shelter_deduction.cap":
            rel = SNAP + "income/deductions/excess_shelter_expense/cap.yaml"
            results.append(_exact(row, official, pe.value(rel, date, SHELTER_CAP_REGIONS.get(region, region)), rel))
        elif parameter == "homeless_shelter_deduction":
            rel = SNAP + "income/deductions/excess_shelter_expense/homeless/deduction.yaml"
            results.append(_cents(row, official, at(pe.load(rel), date), rel, "one national amount"))
        elif parameter.startswith("asset_limit."):
            rel = SNAP + "asset_test/limit.yaml"
            results.append(_exact(row, official, pe.value(rel, date, parameter.split(".", 1)[1]), rel))
        elif parameter.removesuffix(".additional_person") in INCOME_LIMIT_RATES:
            pe_value, rel = _snap_income_limit(pe, row, date)
            results.append(_exact(row, official, pe_value, rel, "derived: rate × poverty guideline ÷ 12, rounded up"))
        else:
            results.append(_result(row, row["raw"], None, "missing in PolicyEngine", "", "no mapping for this item"))
    return results


def _cents(row: dict, official, pe_value, rel: str, note: str = "") -> Result:
    if pe_value is None:
        return _result(row, row["raw"], None, "missing in PolicyEngine", rel, note)
    status = "match" if abs(official - pe_value) < 0.005 else "differ"
    return _result(row, row["raw"], pe_value, status, rel, note)


COMPARISONS: dict[str, Comparison] = {
    "hhs-poverty-guidelines": compare_fpg,
    "fns-snap-cola-fy27": compare_cola,
    "medicaid-eligibility-levels": compare_medicaid,
    "medicaid-eligibility-levels-current": compare_medicaid,
    "fns-snap-sua-fy26": compare_sua,
    "irs-eitc-rp-25-32": compare_eitc,
}


def check_source(source_id: str, data_dir: Path, comparison: Comparison) -> dict:
    processed = data_dir / "processed" / f"{source_id}.csv"
    if not processed.is_file():
        return {"id": source_id, "result": "not extracted yet", "counts": {}, "differences": []}
    with processed.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    results = comparison(rows, PolicyEngine(data_dir / PE_ROOT))

    out = data_dir / "processed" / "checks" / f"{source_id}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[f.name for f in fields(Result)])
        writer.writeheader()
        writer.writerows(asdict(r) for r in results)
    counts = {status: sum(r.status == status for r in results) for status in STATUSES}
    return {"id": source_id, "result": "checked", "counts": counts,
            "differences": [r for r in results if r.status == "differ"],
            "output": out.relative_to(data_dir).as_posix()}


def summary_markdown(reports: list[dict]) -> str:
    lines = ["# Official values vs PolicyEngine", "",
             "Generated by `python -m scraper check`. One CSV per source in this folder has every comparison.", "",
             "| Source | " + " | ".join(s[0].upper() + s[1:] for s in STATUSES) + " |",
             "|---|" + "---|" * len(STATUSES)]
    for report in reports:
        if report["result"] != "checked":
            lines.append(f"| `{report['id']}` | {report['result']} |" + " |" * (len(STATUSES) - 1))
            continue
        lines.append(f"| `{report['id']}` | " + " | ".join(str(report["counts"][s]) for s in STATUSES) + " |")
    for report in reports:
        if not report["differences"]:
            continue
        lines += ["", f"## Differences: `{report['id']}`", "",
                  "| Parameter | Region | Size | Official | PolicyEngine | Note |", "|---|---|---|---|---|---|"]
        for r in report["differences"]:
            note = r.note.replace("|", "\\|")
            lines.append(f"| {r.parameter} | {r.region} | {r.household_size} | {r.official} | {r.policyengine} | {note} |")
    return "\n".join(lines) + "\n"
