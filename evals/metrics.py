"""Aggregate scored results into the numbers compare.md reports."""

from __future__ import annotations

import random
from collections.abc import Callable

from evals.answer import AMOUNT_KEYS, PROGRAMS, parse_answer
from evals.score import score

BOOTSTRAP_SAMPLES = 2000


def scored(results: list[dict]) -> list[dict]:
    """Results that count: everything except cases the API never answered."""
    return [r for r in results if r["status"] == "ok"]


def _rate(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def summarize(results: list[dict]) -> dict:
    rows = scored(results)
    out: dict = {"n": len(rows), "api_errors": len(results) - len(rows)}
    if not rows:
        return out
    amounts = [r["score"]["amount"] for r in rows if r["score"]["amount"] is not None]
    out.update({
        "reward": sum(r["score"]["reward"] for r in rows) / len(rows),
        "eligibility": sum(r["score"]["eligibility"] for r in rows) / len(rows),
        "amount": _rate(sum(amounts), len(amounts)),
        "malformed": sum(r["score"]["malformed"] for r in rows) / len(rows),
        "programs": {},
    })
    for program in PROGRAMS:
        details = [r["score"]["programs"][program] for r in rows]
        total = lambda key: sum(d[key] for d in details)  # noqa: E731
        eligible = total("truly_eligible")
        stats = {
            "decisions": total("decisions"),
            "accuracy": _rate(total("correct"), total("decisions")),
            "balanced_accuracy": _balanced(details),
            "false_denial_rate": _rate(total("false_denials"), eligible),
            "false_approval_rate": _rate(total("false_approvals"), total("decisions") - eligible),
            "unknown_rate": _rate(total("unknown"), total("decisions")),
        }
        if program in AMOUNT_KEYS:
            stats["amount_within_tolerance"] = _rate(sum(bool(d["amount_ok"]) for d in details), eligible)
        out["programs"][program] = stats
    return out


def _balanced(details: list[dict]) -> float | None:
    """Mean of accuracy on truly eligible and on truly ineligible decisions. Unlike plain accuracy, it doesn't
    move when one set simply has more eligible households: answering "no" to everything scores 50% on any set."""
    eligible = sum(d["truly_eligible"] for d in details)
    ineligible = sum(d["decisions"] for d in details) - eligible
    if not eligible or not ineligible:
        return None
    return (sum(d["true_approvals"] for d in details) / eligible + sum(d["true_denials"] for d in details) / ineligible) / 2


def program_balanced_accuracy(program: str) -> Callable[[list[dict]], float | None]:
    def stat(rows: list[dict]) -> float | None:
        return _balanced([r["score"]["programs"][program] for r in rows])
    return stat


def mean_reward(rows: list[dict]) -> float | None:
    return _rate(sum(r["score"]["reward"] for r in rows), len(rows))


def bootstrap_change(a: list[dict], b: list[dict], stat: Callable[[list[dict]], float | None],
                     samples: int = BOOTSTRAP_SAMPLES, seed: int = 0) -> tuple[float, float, float] | None:
    """stat(b) − stat(a), with a 95% interval from resampling households in each set."""
    a, b = scored(a), scored(b)
    base_a, base_b = stat(a), stat(b)
    if not a or not b or base_a is None or base_b is None:
        return None
    rng = random.Random(seed)
    diffs = []
    for _ in range(samples):
        sa = stat([rng.choice(a) for _ in a])
        sb = stat([rng.choice(b) for _ in b])
        if sa is not None and sb is not None:
            diffs.append(sb - sa)
    diffs.sort()
    low, high = diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]
    return base_b - base_a, low, high


def floors(households: list[dict]) -> dict[str, float]:
    """What blanket answers score on this set: the floor any real model has to beat."""
    import json

    def blanket(names: dict, yes: bool) -> str:
        body = {"snap": {"eligible": yes, "monthly_benefit": 0}, "eitc": {"eligible": yes, "annual_amount": 0},
                "medicaid": {"eligible_members": list(names) if yes else []},
                "wic": {"eligible_members": list(names) if yes else []}}
        return json.dumps(body)

    out = {}
    for label, yes in (("always_yes", True), ("always_no", False)):
        total = 0.0
        for row in households:
            members = row["household"]["members"]
            names = {m["name"]: m["id"] for m in members}
            answer, _ = parse_answer(blanket(names, yes), names)
            total += score(answer, row["truth"], [m["id"] for m in members])["reward"]
        out[label] = round(total / len(households), 4) if households else 0.0
    return out
