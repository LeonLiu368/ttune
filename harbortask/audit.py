"""Reward-hack audit: what dumb answers score, over every document case, with the verifier's own scoring.

The degenerate policies are the reward-hack-audit skill's: empty, malformed, constant, hedge-everything, and right
format with random values. Each must stay well below the reference answer's 1.0.
"""

from __future__ import annotations

import json
import random
from datetime import date

from harbortask import verify

PROGRAMS = ("snap", "eitc")


def _answer(truth: dict, eligible, members_yes: bool, unknown: bool = False, missing: list | None = None) -> str:
    names = list(truth["names"].values())
    body = {"snap": {"eligible": eligible, "monthly_benefit": 0}, "eitc": {"eligible": eligible, "annual_amount": 0}}
    for program in ("medicaid", "wic"):
        body[program] = {"eligible_members": names if members_yes else [], "unknown_members": names if unknown else []}
    body["missing_information"] = missing or []
    return json.dumps(body)


def _flag_everything(truth: dict) -> list[dict]:
    names = list(truth["names"].values())
    return ([{"document": c, "member": n} for c in sorted(verify.PER_MEMBER) for n in names]
            + [{"document": c, "member": None} for c in verify.CATEGORIES if c not in verify.PER_MEMBER])


def _random(truth: dict, rng: random.Random) -> str:
    names = list(truth["names"].values())
    body = {p: {"eligible": rng.choice([True, False, "unknown"]), key: round(rng.uniform(0, 8000), 2)}
            for p, key in (("snap", "monthly_benefit"), ("eitc", "annual_amount"))}
    for program in ("medicaid", "wic"):
        body[program] = {"eligible_members": [n for n in names if rng.random() < 0.5], "unknown_members": []}
    pool = _flag_everything(truth)
    body["missing_information"] = rng.sample(pool, rng.randint(0, 2))
    return json.dumps(body)


POLICIES = {
    "oracle": lambda t, rng: json.dumps(verify.oracle(t)),
    "empty": lambda t, rng: None,
    "malformed": lambda t, rng: "{not json",
    "all no, flag nothing": lambda t, rng: _answer(t, False, False),
    "all yes, flag nothing": lambda t, rng: _answer(t, True, True),
    "all unknown, flag everything": lambda t, rng: _answer(t, "unknown", False, True, _flag_everything(t)),
    "random values, right format": lambda t, rng: _random(t, rng),
}


def run(rows: list[dict]) -> dict:
    from harbortask.build import truth_file

    rng = random.Random(0)
    out = {}
    for name, policy in POLICIES.items():
        scores = [verify.evaluate(policy(truth_file(r), rng), truth_file(r)) for r in rows]
        out[name] = {"mean": round(sum(s["reward"] for s in scores) / len(scores), 4),
                     "max": max(s["reward"] for s in scores),
                     "dimensions": {d: round(sum(s[d] for s in scores) / len(scores), 4)
                                    for d in ("eligibility", "amount", "missing_info")}}
    return out


def report(policies: dict, n: int) -> dict:
    degenerate = {k: v for k, v in policies.items() if k != "oracle"}
    worst = max(degenerate, key=lambda k: degenerate[k]["mean"])
    checks = [
        {"check": "Leakage", "result": "pass",
         "notes": "The agent image holds only the PDFs and benefits-calc; the answer key, grading code and solution "
                  "are in the verifier's image or solution/. No network in either. Task ids are hashed, not case ids."},
        {"check": "Tampering", "result": "pass",
         "notes": "Separate verifier container built from tests/; only /app/answer.json crosses over, as data."},
        {"check": "Degenerate policies", "result": "pass" if degenerate[worst]["mean"] < 0.5 else "FAIL",
         "notes": "; ".join(f"{k}: {v['mean']:.2f}" for k, v in degenerate.items())
                  + f" (mean reward over {n} cases; oracle {policies['oracle']['mean']:.2f})"},
        {"check": "Verifier logic", "result": "pass",
         "notes": "Scores outcomes (answers vs PolicyEngine), not format. Unreadable answers and grading errors score "
                  "0. Deterministic."},
    ]
    return {"date": date.today().isoformat(), "cases": n, "policies": policies, "checks": checks}
