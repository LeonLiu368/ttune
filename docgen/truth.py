"""The right answer for a document packet: PolicyEngine on what the documents establish.

With no gap, that is the household's own truth (docgen.documents proves the paperwork gives back the household's
exact figures). With a gap, the missing fact is tried at GRID points across its plausible range, plus its real
value. A decision that comes out the same every time stands; one that changes is "unknown". A grid rather than
the two ends, because the EITC rises and then falls with income.
"""

from __future__ import annotations

from envgen import truth as pe
from envgen.household import Household
from docgen.model import Packet

GRID = 9
CHUNK = 200  # households per PolicyEngine simulation
UNKNOWN = "unknown"
AMOUNTS = {"snap": "monthly_benefit", "eitc": "annual_amount"}
MEMBER_PROGRAMS = ("medicaid", "wic", "chip")


def grid(low: int, high: int, n: int = GRID) -> list[int]:
    return sorted({round(low + (high - low) * i / (n - 1)) for i in range(n)})


def variants(household: Household, packet: Packet) -> list[Household]:
    """The household with each gap's fact set to each grid value. Ids get a ~n suffix to stay unique."""
    out = []
    for issue in packet.gaps:
        gap = issue.gap
        for value in grid(*gap["range"]):
            v = Household.from_dict(household.to_dict())
            v.id = f"{household.id}~{len(out)}"
            if gap["fact"] == "income":
                v.member(gap["member"]).income[gap["source"]] = value
                if not value:
                    del v.member(gap["member"]).income[gap["source"]]
            elif gap["fact"] == "rent":
                v.expenses.rent = value
            elif gap["fact"] == "childcare":
                v.expenses.childcare = value
            else:
                raise ValueError(gap)
            out.append(v)
    return out


def combine(base: dict, others: list[dict], member_ids: list[str], flags: list[str]) -> dict:
    """One truth from the real value's answer and the answers at every grid point."""
    every = [base, *others]
    out: dict = {}
    for program, amount_key in AMOUNTS.items():
        answers = {t[program]["eligible"] for t in every}
        amounts = {round(t[program][amount_key], 2) for t in every}
        settled = len(answers) == 1
        out[program] = {"eligible": base[program]["eligible"] if settled else UNKNOWN,
                        amount_key: base[program][amount_key] if settled and len(amounts) == 1 else None}
    for program in MEMBER_PROGRAMS:
        sets = [set(t[program]["eligible_members"]) for t in every]
        always, ever = set.intersection(*sets), set.union(*sets)
        order = [m for m in member_ids]
        out[program] = {"eligible_members": [m for m in order if m in always],
                        "unknown_members": [m for m in order if m in ever - always]}
    values = {round(t["wic"]["monthly_value"], 2) for t in every}
    out["wic"]["monthly_value"] = base["wic"]["monthly_value"] if len(values) == 1 else None
    out["missing_information"] = flags
    return out


def compute(rows: list[tuple[Household, Packet, dict]]) -> list[dict]:
    """[(household, packet, the household's own truth)] -> the packet's truth, in order."""
    jobs = [(h, p, variants(h, p)) for h, p, _ in rows]
    flat = [v for _, _, vs in jobs for v in vs]
    results: list[dict] = []
    for start in range(0, len(flat), CHUNK):
        results += pe.compute(flat[start:start + CHUNK])
    out, at = [], 0
    for (h, p, vs), (_, _, base) in zip(jobs, rows):
        others = results[at:at + len(vs)]
        at += len(vs)
        out.append(combine(base, others, [m.id for m in h.members], [i.flag for i in p.gaps]))
    return out


def eligible(truth: dict, program: str) -> str:
    """yes, no or unknown per program per household, for balance checks."""
    if program in AMOUNTS:
        value = truth[program]["eligible"]
        return UNKNOWN if value == UNKNOWN else ("yes" if value else "no")
    if truth[program]["eligible_members"]:
        return "yes"
    return UNKNOWN if truth[program]["unknown_members"] else "no"
