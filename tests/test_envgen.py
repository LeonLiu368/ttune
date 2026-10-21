"""Household samplers and case text. None of this needs PolicyEngine."""

from collections import Counter

import pytest

from envgen.describe import describe, money
from envgen.household import Household
from envgen.sample import (EDGE_OFFSET, EDGE_PROGRAMS, HELD_OUT_STATES, ID_STATES, OOD_FAMILIES, STATES, TWISTS,
                           poverty_line, sample)


def test_same_set_seed_index_gives_an_identical_household():
    for set_ in ("id", "ood"):
        for index in range(12):
            assert sample(set_, 1, index).to_dict() == sample(set_, 1, index).to_dict()
    assert sample("id", 1, 0).to_dict() != sample("id", 1, 1).to_dict()
    assert sample("id", 1, 0).to_dict() != sample("id", 2, 0).to_dict()
    assert sample("ood", 1, 1).to_dict() != sample("ood", 1, 1, attempt=1).to_dict()


def test_household_round_trips_through_json_dict():
    for index in range(9):
        h = sample("ood", 1, index)
        assert Household.from_dict(h.to_dict()).to_dict() == h.to_dict()


def test_states_split_into_id_and_held_out():
    assert len(STATES) == 51
    assert set(ID_STATES) | set(HELD_OUT_STATES) == set(STATES)
    assert not set(ID_STATES) & set(HELD_OUT_STATES)
    assert {"AK", "NY", "HI"} <= set(HELD_OUT_STATES)


def test_id_households_are_typical():
    for index in range(300):
        h = sample("id", 1, index)
        assert (h.shift, h.twists, h.edge) == ("none", [], None)
        assert h.state in ID_STATES and h.county is None
        assert 1 <= h.size <= 5
        adults = [m for m in h.members if m.relationship in ("head", "spouse")]
        assert all(18 <= m.age <= 64 for m in adults)
        assert h.head.income.get("wages", 0) > 0
        assert all(m.relationship != "parent" and m.citizenship == "citizen" for m in h.members)
        assert not any(m.pregnant or m.disabled or m.student for m in h.members)
        assert all(m.age <= 17 for m in h.members if m.relationship == "child")


def test_held_out_states_never_appear_in_the_id_set():
    assert not {sample("id", seed, i).state for seed in (1, 2) for i in range(400)} & set(HELD_OUT_STATES)


def test_ood_families_come_in_equal_thirds():
    households = [sample("ood", 1, i) for i in range(200)]
    assert Counter(h.shift for h in households) == {"rare_shape": 67, "threshold_edge": 67, "held_out_state": 66}
    for i, h in enumerate(households):
        assert h.shift == OOD_FAMILIES[i % 3]


def test_every_twist_appears_and_rare_shapes_stay_in_id_states():
    rare = [sample("ood", 1, i) for i in range(0, 200, 3)]
    assert {t for h in rare for t in h.twists} == set(TWISTS)
    assert all(1 <= len(h.twists) <= 2 and h.state in ID_STATES for h in rare)


def test_twists_change_the_household():
    rare = [sample("ood", 1, i) for i in range(0, 600, 3)]
    for h in rare:
        t = set(h.twists)
        if "multigenerational" in t:
            parents = [m for m in h.members if m.relationship == "parent"]
            assert parents and all(m.age >= 65 and m.income.get("social_security") for m in parents)
        if "large_household" in t:
            assert h.size >= 8
        if "college_student" in t:
            assert any(m.student and 18 <= m.age <= 22 for m in h.members)
        if "pregnant_member" in t:
            assert any(m.pregnant and m.age <= 44 for m in h.members)
        if "mixed_citizenship" in t:
            assert any(m.citizenship == "undocumented" for m in h.members)
            assert any(m.citizenship == "citizen" for m in h.members)
        if "self_employment" in t:
            assert h.head.income.get("self_employment", 0) > 0 and "wages" not in h.head.income
        if "disabled_member" in t:
            disabled = [m for m in h.members if m.disabled]
            assert disabled and all(m.id in h.expenses.medical for m in disabled)


def test_held_out_family_covers_every_held_out_state_with_counties_where_needed():
    held = [sample("ood", 1, i) for i in range(2, 200, 3)]
    assert {h.state for h in held} == set(HELD_OUT_STATES)
    for h in held:
        assert h.twists == []
        assert (h.county is not None) == (h.state in ("AK", "NY"))


def test_threshold_edge_households_record_their_target():
    edge = [sample("ood", 1, i) for i in range(1, 200, 3)]
    assert Counter(h.edge["program"] for h in edge) == {"snap": 23, "eitc": 22, "medicaid": 22}
    for h in edge:
        assert h.state in ID_STATES and h.twists == [f"edge_{h.edge['program']}"]
        assert EDGE_OFFSET[0] <= abs(h.edge["offset"]) <= EDGE_OFFSET[1]
        assert (h.edge["offset"] > 0) == (h.edge["side"] == "above")


def test_wages_spread_around_the_poverty_line():
    ratios = []
    for i in range(300):
        h = sample("id", 1, i)
        wages = sum(m.income.get("wages", 0) for m in h.members)
        ratios.append(12 * wages / poverty_line(h.state, h.size))
    assert 0.49 <= min(ratios) and max(ratios) <= 2.51
    assert sum(r < 1.3 for r in ratios) > 60 and sum(r > 1.3 for r in ratios) > 60


def test_poverty_line_uses_alaska_and_hawaii_guidelines():
    assert poverty_line("TX", 1) == 15960
    assert poverty_line("TX", 4) == 33000
    assert poverty_line("AK", 8) == 69650
    assert poverty_line("HI", 3) == 31420


@pytest.mark.parametrize(("set_", "index"), [("id", i) for i in range(40)] + [("ood", i) for i in range(60)])
def test_case_text_names_every_member_income_and_expense(set_, index):
    h = sample(set_, 1, index)
    text = describe(h)
    assert h.id in text
    for m in h.members:
        assert f"{m.name}, age {m.age}" in text
        for amount in m.income.values():
            assert f"{money(amount)} a month" in text
    assert f"Rent: {money(h.expenses.rent)}" in text
    assert ("paid separately" in text) == h.expenses.heating_cooling
    if h.expenses.childcare:
        assert f"Childcare: {money(h.expenses.childcare)}" in text
    for member_id, amount in h.expenses.medical.items():
        assert f"for {h.member(member_id).name}: {money(amount)}" in text
    if h.area:
        assert h.area in text


def test_case_text_flags_status_and_gives_no_answers():
    rare = [sample("ood", 1, i) for i in range(0, 200, 3)]
    texts = "\n".join(describe(h) for h in rare)
    for phrase in ("Pregnant.", "Has a disability.", "Full-time college student.", "Not a US citizen"):
        assert phrase in texts
    for word in ("SNAP", "Medicaid", "EITC", "WIC", "eligible", "poverty"):
        assert word not in texts
