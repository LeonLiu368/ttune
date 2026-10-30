"""The fixed list of injected issues, and which ones a household gets.

Distractors leave the facts alone: a careful reader who follows docgen.rules.RULES still gets every number.
Gaps remove a fact, so some answers may become "unknown" (docgen.truth decides which).
"""

from __future__ import annotations

import math
import random

from envgen.household import Household
from envgen.sample import poverty_line

DISTRACTORS = ("stale_stub", "rent_mismatch", "partner_moved_out", "name_variant")
GAPS = ("missing_income_doc", "missing_lease_page", "missing_childcare_receipt")
KINDS = DISTRACTORS + GAPS
P_DISTRACTOR = 0.5
P_GAP = 0.35
# The range a missing fact could plausibly take. Truth tries values across it (docgen.truth).
RENT_RANGE = (0, 4000)
CHILDCARE_RANGE = (0, 2000)
INCOME_MULTIPLE = 3  # up to 300% of the poverty line for the household's size, a month


def income_range(household: Household) -> tuple[int, int]:
    return 0, math.ceil(INCOME_MULTIPLE * poverty_line(household.state, household.size) / 12)


def _candidates(kind: str, h: Household) -> list[dict]:
    adults = [m for m in h.members if m.age >= 18]
    if kind == "stale_stub":
        return [{"member": m.id} for m in h.members if m.income.get("wages")]
    if kind == "rent_mismatch":
        return [{}]
    if kind == "partner_moved_out":
        alone = not any(m.relationship == "spouse" for m in h.members)
        return [{"member": h.head.id}] if alone and h.head.age >= 20 else []
    if kind == "name_variant":
        return [{"member": m.id} for m in adults if m.income]
    if h.shift == "threshold_edge":  # gaps would blur the cutoff the household was placed at
        return []
    if kind == "missing_income_doc":
        return [{"member": m.id, "source": source} for m in h.members for source in m.income]
    if kind == "missing_lease_page":
        return [{}]
    if kind == "missing_childcare_receipt":
        return [{}] if h.expenses.childcare else []
    raise ValueError(kind)


def choose(household: Household, rng: random.Random) -> list[dict]:
    """0 to 2 issues: at most one gap, then at most one distractor that doesn't clash with it."""
    plans: list[dict] = []
    if rng.random() < P_GAP:
        options = [{"kind": k, **c} for k in GAPS for c in _candidates(k, household)]
        if options:
            plans.append(rng.choice(options))
    if rng.random() < P_DISTRACTOR:
        options = [{"kind": k, **c} for k in DISTRACTORS for c in _candidates(k, household)
                   if not any(_clash(p, {"kind": k, **c}) for p in plans)]
        if options:
            plans.append(rng.choice(options))
    return plans


def _clash(gap: dict, distractor: dict) -> bool:
    if gap["kind"] == "missing_lease_page" and distractor["kind"] in ("rent_mismatch", "partner_moved_out"):
        return True
    if gap["kind"] == "missing_income_doc" and distractor.get("member") == gap["member"]:
        return True  # no stale stub or nickname on documents that aren't there
    return False
