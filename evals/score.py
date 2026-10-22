"""Score one answer against PolicyEngine's truth. Pure functions, no I/O: the Harbor verifier will import this.

Follows the reward in the `benefits-task` skill (docs/04), adapted to programs decided per member:

- Decisions: SNAP and EITC are one decision each; Medicaid and WIC are one per household member.
- eligibility = max(0, (Σ correct_p/n_p − 2 · Σ false_denials_p/n_p) / 4). Each program weighs 1, split
  across its decisions. A false "not eligible" costs double: it's the error that costs people food or care.
  A false "eligible" just earns nothing. "unknown" earns nothing and isn't a denial.
- amount (SNAP and EITC, only when truly eligible): 1 within ±5% or ±$10, whichever is larger, falling
  linearly to 0 at ±25%. 0 if the answer denied, said unknown or gave no amount.
- reward = 2/3 · eligibility + 1/3 · amount, or eligibility alone when neither SNAP nor EITC is truly
  eligible. These are the skill's weights (0.5 and 0.25) renormalized: its missing-information and
  unknown-use dimensions need documents, which these cases don't have yet.
- A malformed answer scores 0, and every decision counts as wrong.
"""

from __future__ import annotations

from evals.answer import AMOUNT_KEYS, MEMBER_PROGRAMS, PROGRAMS, UNKNOWN

DENIAL_WEIGHT = 2
TOLERANCE = 0.05
TOLERANCE_DOLLARS = 10.0
ZERO_AT = 0.25
WEIGHTS = {"eligibility": 2 / 3, "amount": 1 / 3}
TRUTH_AMOUNT = {"snap": "monthly_benefit", "eitc": "annual_amount"}


def amount_score(given: float | None, true: float) -> float:
    if given is None:
        return 0.0
    error = abs(given - true)
    tolerance = max(TOLERANCE * true, TOLERANCE_DOLLARS)
    zero = max(ZERO_AT * true, tolerance)
    if error <= tolerance:
        return 1.0
    if error >= zero:
        return 0.0
    return (zero - error) / (zero - tolerance)


def _decisions(program: str, answer: dict | None, truth: dict, member_ids: list[str]) -> list[tuple[bool, object]]:
    """(truly eligible, answered) per decision; answered is True, False, "unknown", or None if malformed."""
    if program in AMOUNT_KEYS:
        given = None if answer is None else answer[program]["eligible"]
        return [(bool(truth[program]["eligible"]), given)]
    eligible = set(truth[program]["eligible_members"])
    listed = None if answer is None else set(answer[program]["members"])
    return [(m in eligible, None if listed is None else m in listed) for m in member_ids]


def score(answer: dict | None, truth: dict, member_ids: list[str]) -> dict:
    """Score a parsed answer (None if malformed). `member_ids` lists every household member, p1, p2, ..."""
    programs = {}
    correct_w = denial_w = 0.0
    amounts = []
    for program in PROGRAMS:
        decisions = _decisions(program, answer, truth, member_ids)
        n = len(decisions)
        correct = sum(given is not None and given != UNKNOWN and given == true for true, given in decisions)
        denials = sum(true and given is False for true, given in decisions)
        approvals = sum((not true) and given is True for true, given in decisions)
        unknown = sum(given == UNKNOWN for _, given in decisions)
        detail = {"decisions": n, "correct": correct, "false_denials": denials, "false_approvals": approvals,
                  "unknown": unknown, "truly_eligible": sum(true for true, _ in decisions),
                  "true_approvals": sum(true and given is True for true, given in decisions),
                  "true_denials": sum((not true) and given is False for true, given in decisions)}
        correct_w += correct / n
        denial_w += denials / n
        if program in AMOUNT_KEYS:
            detail["amount_score"] = detail["amount_ok"] = None
            if truth[program]["eligible"]:
                true_amount = float(truth[program][TRUTH_AMOUNT[program]])
                said_yes = answer is not None and answer[program]["eligible"] is True
                a = amount_score(answer[program]["amount"], true_amount) if said_yes else 0.0
                detail["amount_score"], detail["amount_ok"] = round(a, 4), a == 1.0
                amounts.append(a)
        programs[program] = detail

    eligibility = max(0.0, (correct_w - DENIAL_WEIGHT * denial_w) / len(PROGRAMS))
    amount = sum(amounts) / len(amounts) if amounts else None
    reward = eligibility if amount is None else WEIGHTS["eligibility"] * eligibility + WEIGHTS["amount"] * amount
    if answer is None:
        reward = eligibility = 0.0
        amount = None if amount is None else 0.0
    return {"reward": round(reward, 4), "eligibility": round(eligibility, 4),
            "amount": None if amount is None else round(amount, 4),
            "malformed": answer is None, "programs": programs}


def oracle_answer(truth: dict, names: dict[str, str]) -> dict:
    """The JSON a perfect model would send, by member name. For tests and the mock server."""
    by_id = {member_id: name for name, member_id in names.items()}
    out = {}
    for program in PROGRAMS:
        if program in AMOUNT_KEYS:
            out[program] = {"eligible": truth[program]["eligible"],
                            AMOUNT_KEYS[program]: truth[program][TRUTH_AMOUNT[program]]}
        else:
            out[program] = {"eligible_members": [by_id[m] for m in truth[program]["eligible_members"]]}
    return out


assert set(MEMBER_PROGRAMS) | set(AMOUNT_KEYS) == set(PROGRAMS)
