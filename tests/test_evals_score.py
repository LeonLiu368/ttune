"""Answer parsing and scoring. No network, no PolicyEngine."""

import json
from pathlib import Path

import pytest

from evals.answer import parse_answer
from evals.score import amount_score, oracle_answer, score

SETS = Path(__file__).resolve().parents[1] / "data" / "households"

NAMES = {"Maria": "p1", "Luis": "p2", "Ana Sofia": "p3"}
IDS = ["p1", "p2", "p3"]
TRUTH = {
    "snap": {"eligible": True, "monthly_benefit": 400.0},
    "eitc": {"eligible": True, "annual_amount": 4000.0},
    "medicaid": {"eligible_members": ["p2", "p3"]},
    "wic": {"eligible_members": ["p3"]},
    "chip": {"eligible_members": []},
}


def reply(snap=(True, 400), eitc=(True, 4000), medicaid=("Luis", "Ana Sofia"), wic=("Ana Sofia",), prefix=""):
    body = {"snap": {"eligible": snap[0], "monthly_benefit": snap[1]},
            "eitc": {"eligible": eitc[0], "annual_amount": eitc[1]},
            "medicaid": {"eligible_members": list(medicaid)},
            "wic": {"eligible_members": list(wic)}}
    return f"{prefix}```json\n{json.dumps(body)}\n```"


def run(text, truth=TRUTH):
    answer, error = parse_answer(text, NAMES)
    return score(answer, truth, IDS), error


def test_perfect_answer_scores_one():
    result, error = run(reply(prefix="Working: gross income is below the limit...\n"))
    assert error is None
    assert (result["reward"], result["eligibility"], result["amount"], result["malformed"]) == (1.0, 1.0, 1.0, False)


def test_false_denial_costs_double_a_false_approval():
    denied, _ = run(reply(snap=(False, 0)))  # SNAP truly eligible, answered no
    truth = {**TRUTH, "eitc": {"eligible": False, "annual_amount": 0.0}}
    approved, _ = run(reply(eitc=(True, 100)), truth)  # EITC truly ineligible, answered yes
    assert denied["programs"]["snap"]["false_denials"] == 1
    assert approved["programs"]["eitc"]["false_approvals"] == 1
    assert denied["eligibility"] == pytest.approx((3 - 2) / 4)
    assert approved["eligibility"] == pytest.approx(3 / 4)


def test_member_programs_split_their_weight_across_members():
    result, _ = run(reply(medicaid=("Luis",)))  # misses Ana Sofia: 2 of 3 right, 1 false denial
    medicaid = result["programs"]["medicaid"]
    assert (medicaid["decisions"], medicaid["correct"], medicaid["false_denials"]) == (3, 2, 1)
    assert result["eligibility"] == pytest.approx((3 + 2 / 3 - 2 / 3) / 4)


def test_eligibility_is_clipped_at_zero():
    result, _ = run(reply(snap=(False, 0), eitc=(False, 0), medicaid=(), wic=()))
    assert result["eligibility"] == 0.0 and result["reward"] == 0.0


@pytest.mark.parametrize(("given", "true", "expected"), [
    (400, 400, 1.0), (420, 400, 1.0), (380, 400, 1.0),  # ±5%
    (56, 46, 1.0), (57, 46, pytest.approx(1 / 3)), (58, 46, 0.0),  # small amounts: ±$10, zero at 25% ($11.50)
    (440, 400, 0.75), (460, 400, 0.5), (500, 400, 0.0), (300, 400, 0.0),  # linear 5% -> 25%
    (None, 400, 0.0),
])
def test_amount_tolerance(given, true, expected):
    assert amount_score(given, true) == pytest.approx(expected)


def test_amount_counts_only_when_truly_eligible_and_answered_yes():
    result, _ = run(reply(snap=(True, 460)))
    assert result["programs"]["snap"]["amount_score"] == pytest.approx(0.5)
    assert result["amount"] == pytest.approx(0.75)
    denied, _ = run(reply(snap=(False, 400)))
    assert denied["programs"]["snap"]["amount_score"] == 0.0
    no_amounts, _ = run(reply(), {**TRUTH, "snap": {"eligible": False, "monthly_benefit": 0.0},
                                  "eitc": {"eligible": False, "annual_amount": 0.0}})
    assert no_amounts["amount"] is None


def test_unknown_earns_nothing_and_is_not_a_denial():
    result, error = run(reply(snap=("unknown", 0)))
    assert error is None
    snap = result["programs"]["snap"]
    assert (snap["correct"], snap["false_denials"], snap["unknown"]) == (0, 0, 1)


def test_names_match_ignoring_case_and_spaces_and_unknown_names_are_kept():
    answer, _ = parse_answer(reply(medicaid=("luis", "ana  sofia", "Nobody")), NAMES)
    assert answer["medicaid"] == {"members": ["p2", "p3"], "unknown_names": ["Nobody"]}


def test_amounts_given_as_strings_are_read():
    answer, error = parse_answer(reply(snap=(True, "$1,234")), NAMES)
    assert error is None and answer["snap"]["amount"] == 1234.0


@pytest.mark.parametrize(("text", "message"), [
    ("I think they qualify for SNAP.", "no JSON object"),
    ('```json\n{"snap": {"eligible": true}}\n```', "'eitc' is missing"),
    (reply().replace('"eligible": true', '"eligible": "yes"', 1), "must be true, false"),
    (reply().replace('["Luis", "Ana Sofia"]', '"Luis"'), "must be a list of names"),
])
def test_malformed_answers_score_zero_and_say_why(text, message):
    result, error = run(text)
    assert message in error
    assert result["malformed"] and result["reward"] == 0.0
    assert all(p["correct"] == 0 and p["false_denials"] == 0 for p in result["programs"].values())


def test_last_json_block_wins():
    text = reply(snap=(False, 0)) + "\nOn reflection:\n" + reply()
    assert run(text)[0]["reward"] == 1.0
    unfenced = "Answer: " + reply().removeprefix("```json\n").removesuffix("\n```")
    assert run(unfenced)[0]["reward"] == 1.0


def load(set_):
    rows = [json.loads(line) for line in (SETS / set_ / "households.jsonl").open()]
    return [({m["name"]: m["id"] for m in r["household"]["members"]}, r["truth"]) for r in rows]


def mean_reward(answer_fn, rows):
    total = 0.0
    for names, truth in rows:
        answer, error = parse_answer("```json\n" + json.dumps(answer_fn(names, truth)) + "\n```", names)
        assert error is None
        total += score(answer, truth, sorted(names.values(), key=lambda m: int(m[1:])))["reward"]
    return total / len(rows)


def test_oracle_scores_one_on_both_real_sets():
    for set_ in ("id", "ood"):
        assert mean_reward(lambda names, truth: oracle_answer(truth, names), load(set_)) == 1.0


def everyone(names, truth, eligible):
    return {"snap": {"eligible": eligible, "monthly_benefit": 0}, "eitc": {"eligible": eligible, "annual_amount": 0},
            "medicaid": {"eligible_members": list(names) if eligible else []},
            "wic": {"eligible_members": list(names) if eligible else []}}


def test_degenerate_answers_score_low_on_the_real_sets():
    # The reward-hack-audit rule: blanket answers must not pay. "Always no" isn't zero, because about a third
    # of ID households truly qualify for nothing; compare.md prints these floors next to every model.
    for set_ in ("id", "ood"):
        rows = load(set_)
        assert mean_reward(lambda n, t: everyone(n, t, True), rows) < 0.4
        assert mean_reward(lambda n, t: everyone(n, t, False), rows) < 0.4
        assert mean_reward(lambda n, t: {p: ({"eligible": "unknown"} if p in ("snap", "eitc")
                                             else {"eligible_members": []}) for p in ("snap", "eitc", "medicaid", "wic")},
                           rows) < 0.4
