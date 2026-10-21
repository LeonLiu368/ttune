"""Move threshold-edge households to just below or just above a real cutoff, found with PolicyEngine.

The cutoff is where PolicyEngine's answer flips as the household's wages rise, everything else held fixed:
- snap: the SNAP benefit drops to $0. In most states that is the 130% gross income limit; in states with
  broad-based categorical eligibility it is that state's higher limit or the point where the benefit runs out.
- eitc: the EITC is fully phased out.
- medicaid: the target member (the head if they can qualify, otherwise the youngest child who can) loses
  Medicaid. That is the state's limit for the member's group (expansion adult, parent, child, pregnant).

Searching the cutoff this way reads it from the installed PolicyEngine, including every state rule.
All edge households are searched together, one simulation per round.
"""

from __future__ import annotations

import math

from envgen import truth
from envgen.household import Household

LOW, HIGH = 50, 40_000  # total monthly wages searched
GRID = 40


def _with_wages(h: Household, total: int, tag: str) -> Household:
    """A copy of `h` whose wages add up to `total`, split between earners as in `h`."""
    copy = Household.from_dict(h.to_dict())
    copy.id = f"{h.id}~{tag}"
    earners = [m for m in copy.members if m.relationship in ("head", "spouse") and m.income.get("wages")]
    base = sum(m.income["wages"] for m in earners)
    left = total
    for i, m in enumerate(earners):
        part = left if i == len(earners) - 1 else round(total * m.income["wages"] / base)
        m.income["wages"] = part
        left -= part
    return copy


def _says_yes(row: dict, program: str, target: str | None) -> bool:
    if program == "medicaid":
        return target in row["medicaid"]["eligible_members"]
    return row[program]["eligible"]


def _targets(h: Household) -> list[str | None]:
    if h.edge["program"] != "medicaid":
        return [None]
    children = sorted((m for m in h.members if m.relationship == "child"), key=lambda m: m.age)
    return [h.head.id, *(m.id for m in children)]


def find_cutoffs(households: list[Household]) -> list[tuple[int, str | None] | None]:
    """For each household, (first total monthly wages at which the program says no, target member), or None."""
    # One search per (household, target); the first target with a cutoff wins.
    searches = [(i, target) for i, h in enumerate(households) for target in _targets(h)]
    grids = {s: _geometric() for s in searches}
    brackets: dict[tuple, tuple[int, int] | None] = {}
    while grids:
        batch, keys = [], []
        for (i, target), grid in grids.items():
            for w in grid:
                batch.append(_with_wages(households[i], w, f"{target}:{w}"))
                keys.append(((i, target), w))
        rows = truth.compute(batch)
        answers: dict[tuple, list[tuple[int, bool]]] = {}
        for (key, w), row in zip(keys, rows):
            answers.setdefault(key, []).append((w, _says_yes(row, households[key[0]].edge["program"], key[1])))
        grids = {}
        for key, points in answers.items():
            flip = next((n for n in range(1, len(points)) if points[n - 1][1] and not points[n][1]), None)
            if not points[0][1] or flip is None:
                brackets[key] = None  # never yes, or never flips to no within the range
                continue
            lo, hi = points[flip - 1][0], points[flip][0]
            if hi - lo <= 1:
                brackets[key] = (lo, hi)
            else:
                grids[key] = _linear(lo, hi)
    results = []
    for i, h in enumerate(households):
        found = next(((brackets[(i, t)][1], t) for t in _targets(h) if brackets.get((i, t))), None)
        results.append(found)
    return results


def _geometric() -> list[int]:
    ratio = (HIGH / LOW) ** (1 / (GRID - 1))
    return sorted({round(LOW * ratio ** n) for n in range(GRID)})


def _linear(lo: int, hi: int) -> list[int]:
    step = (hi - lo) / (GRID - 1)
    return sorted({lo, hi, *(round(lo + step * n) for n in range(GRID))})


def place(households: list[Household]) -> list[Household | None]:
    """Each household with wages moved to its edge, or None if PolicyEngine shows no cutoff for it."""
    placed: list[Household | None] = []
    for h, found in zip(households, find_cutoffs(households)):
        if found is None:
            placed.append(None)
            continue
        cutoff, target = found
        offset = h.edge["offset"]
        wages = round(cutoff * (1 + offset))
        wages = min(wages, cutoff - 1) if offset < 0 else max(wages, cutoff)  # stay on the chosen side
        moved = _with_wages(h, wages, "edge")
        moved.id = h.id
        moved.edge = {**h.edge, "target": target, "cutoff_monthly_wages": cutoff, "monthly_wages": wages,
                      "actual_offset": round(wages / cutoff - 1, 5)}
        placed.append(moved)
    return placed


def within(h: Household, limit: float = 0.01) -> bool:
    """Whether the household's wages are within `limit` (as a fraction) of its recorded cutoff."""
    return math.isclose(h.edge["monthly_wages"], h.edge["cutoff_monthly_wages"], rel_tol=limit)
