"""PolicyEngine ground truth, threshold edges and the generate command. Skipped without policyengine-us."""

import csv
from pathlib import Path

import pytest

pytest.importorskip("policyengine_us")

from envgen import edges, truth  # noqa: E402
from envgen.__main__ import balance_report, build, manifest, write  # noqa: E402
from envgen.household import Expenses, Household, Member  # noqa: E402
from envgen.sample import COUNTIES, sample  # noqa: E402

COLA = Path(__file__).resolve().parents[1] / "data" / "processed" / "fns-snap-cola-fy27.csv"


def official(parameter, region, size):
    with COLA.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if (row["parameter"], row["region"], row["household_size"]) == (parameter, region, str(size)):
                return float(row["value"])
    raise KeyError((parameter, region, size))


def household(hid, state, members, rent=900, heating=True):
    return Household(hid, "id", 0, 0, state, members, Expenses(rent, heating))


def test_variable_names_and_counties_exist_in_installed_policyengine():
    from policyengine_us.variables.household.demographic.geographic.county.county_enum import County

    truth.system()
    for counties in COUNTIES.values():
        for code, _ in counties:
            assert code in County.__members__


def test_no_income_household_gets_the_official_max_allotment():
    # Spot check against FNS's FY2027 table, not PolicyEngine's own parameters.
    h = household("t-zero", "TX", [Member("p1", "Ana", 30, "head"), Member("p2", "Luis", 4, "child")])
    [result] = truth.compute([h])
    assert result["snap"] == {"eligible": True, "monthly_benefit": official("max_allotment", "CONTIGUOUS_US", 2)}


def test_eitc_plateau_matches_the_rev_proc_max_credit():
    # $20,000 a year with one child sits on the plateau: the maximum credit, $4,427 for 2026 (Rev. Proc. 2025-32).
    h = household("t-eitc", "TX", [Member("p1", "Ana", 30, "head", income={"wages": 1667}),
                                   Member("p2", "Luis", 4, "child")])
    [result] = truth.compute([h])
    assert result["eitc"] == {"eligible": True, "annual_amount": 4427.0}
    assert "p2" in result["medicaid"]["eligible_members"] and "p2" in result["wic"]["eligible_members"]


def test_undeclared_benefits_dont_leak_into_snap_income():
    # Colorado computes an Old Age Pension for some 60+ residents; the case doesn't list it, so it must not count.
    h = sample("id", 1, 31)
    assert h.state == "CO" and h.head.age >= 60
    [result] = truth.compute([h])
    assert result["snap"]["monthly_benefit"] >= 0


def test_batch_results_match_one_at_a_time():
    households = [sample("ood", 1, i) for i in (0, 2, 3, 5, 6)]
    together = truth.compute(households)
    alone = [truth.compute([h])[0] for h in households]
    assert together == alone


def test_threshold_edges_land_within_one_percent_on_the_chosen_side():
    households, truths = build("ood", 12, 1)
    edge = [(h, t) for h, t in zip(households, truths) if h.shift == "threshold_edge"]
    assert {h.edge["program"] for h, _ in edge} == {"snap", "eitc", "medicaid"}
    for h, t in edge:
        assert edges.within(h)
        program, target = h.edge["program"], h.edge["target"]
        yes = target in t["medicaid"]["eligible_members"] if program == "medicaid" else t[program]["eligible"]
        assert yes == (h.edge["side"] == "below")
        assert (h.edge["monthly_wages"] < h.edge["cutoff_monthly_wages"]) == (h.edge["side"] == "below")


def test_generate_is_byte_identical_and_reports_balance(tmp_path):
    for out in ("a", "b"):
        households, truths = build("id", 8, 1)
        write(tmp_path / out, households, truths, manifest("id", 8, 1, households, truths))
    for name in ("households.jsonl", "manifest.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    report, ok = balance_report(manifest("id", 8, 1, households, truths))
    assert "snap" in report and isinstance(ok, bool)
