"""Score one task's /app/answer.json. Pure functions over the answer text and the task's truth.json.

The verifier image runs this through Reward Kit (tests/*.py, one criterion per dimension); tests and the reward-hack
audit call `evaluate` directly. Eligibility and amount are evals/score.py's, unchanged, so a task and an eval case
score the same answer the same way. missing_info is new here: the evals can't see what a model would ask for.
"""

from __future__ import annotations

import json

from evals.answer import Malformed, _key, last_json_object, parse_answer
from evals.score import score

# What a household could be asked to bring. A gap's category comes from docgen (fact, and income source).
CATEGORIES = ("pay_stubs", "self_employment_records", "social_security_letter", "ssi_letter",
              "child_support_history", "unemployment_letter", "lease_rent_page", "childcare_receipt")
SOURCE_CATEGORY = {"wages": "pay_stubs", "self_employment": "self_employment_records",
                   "social_security": "social_security_letter", "ssi": "ssi_letter",
                   "child_support": "child_support_history", "unemployment": "unemployment_letter"}
FACT_CATEGORY = {"rent": "lease_rent_page", "childcare": "childcare_receipt"}
PER_MEMBER = set(SOURCE_CATEGORY.values())  # these name whose document is missing; the rest are per household
SPURIOUS_PENALTY = 0.25
WEIGHTS = {"eligibility": 0.60, "amount": 0.25, "missing_info": 0.15}


def missing_items(issues: list[dict], names: dict[str, str]) -> list[dict]:
    """The missing-information items a perfect answer lists, from a docgen packet's issues. `names` maps id -> name."""
    items = []
    for issue in issues:
        gap = issue.get("gap")
        if not gap:
            continue
        if gap["fact"] == "income":
            items.append({"document": SOURCE_CATEGORY[gap["source"]], "member": names[gap["member"]]})
        else:
            items.append({"document": FACT_CATEGORY[gap["fact"]], "member": None})
    return items


def _item_key(item: dict, lookup: dict[str, str]) -> tuple[str, str | None] | None:
    """(category, member id) for a listed item, or None if it can't match anything (a spurious flag)."""
    if not isinstance(item, dict) or item.get("document") not in CATEGORIES:
        return None
    if item["document"] not in PER_MEMBER:
        return item["document"], None
    name = item.get("member")
    if not isinstance(name, str):
        return None
    member = lookup.get(_key(name)) or (lookup.get(_key(name.split()[0])) if name.split() else None)
    return (item["document"], member) if member else None


def missing_info_score(listed: list, truth_items: list[dict], names: dict[str, str]) -> float:
    """Share of true gaps flagged, minus SPURIOUS_PENALTY per flag that matches none, clipped to 0-1."""
    lookup = {_key(name): member_id for member_id, name in names.items()}
    want = {(i["document"], lookup[_key(i["member"])] if i["member"] else None) for i in truth_items}
    given, spurious = set(), 0
    for item in listed:
        key = _item_key(item, lookup)
        if key is None or key not in want:
            spurious += 1
        elif key not in given:
            given.add(key)
    recall = len(given) / len(want) if want else 1.0
    return max(0.0, min(1.0, recall - SPURIOUS_PENALTY * spurious))


def evaluate(answer_text: str | None, truth: dict) -> dict:
    """{"eligibility", "amount", "missing_info", "reward", "malformed"} for one answer.

    `truth` is a task's truth.json: {"truth": PolicyEngine's answers (docgen), "names": {id: name},
    "missing_information": [...]}. A missing or unreadable answer scores 0 on every dimension.
    """
    names = truth["names"]
    zero = {"eligibility": 0.0, "amount": 0.0, "missing_info": 0.0, "reward": 0.0, "malformed": True}
    if not answer_text:
        return zero
    answer, error = parse_answer(answer_text, {name: member_id for member_id, name in names.items()})
    if answer is None:
        return {**zero, "error": error}
    try:
        listed = last_json_object(answer_text).get("missing_information", [])
    except Malformed:
        listed = []
    if not isinstance(listed, list):
        return {**zero, "error": "'missing_information' must be a list"}
    s = score(answer, truth["truth"], list(names))
    eligibility = s["eligibility"]
    amount = eligibility if s["amount"] is None else s["amount"]  # no amount to score: as in the evals
    missing = missing_info_score(listed, truth["missing_information"], names)
    reward = (WEIGHTS["eligibility"] * eligibility + WEIGHTS["amount"] * amount + WEIGHTS["missing_info"] * missing)
    return {"eligibility": round(eligibility, 4), "amount": round(amount, 4), "missing_info": round(missing, 4),
            "reward": round(reward, 4), "malformed": False}


def oracle(truth: dict) -> dict:
    """The answer a perfect agent writes."""
    from evals.score import oracle_answer

    names = truth["names"]
    out = oracle_answer(truth["truth"], {name: member_id for member_id, name in names.items()})
    for program in ("medicaid", "wic"):
        out[program].setdefault("unknown_members", [])
    out["missing_information"] = truth["missing_information"]
    out["explanation"] = "Reference answer."
    return out


def load(path) -> dict:
    with open(path) as fh:
        return json.load(fh)
