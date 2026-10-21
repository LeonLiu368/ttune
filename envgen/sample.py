"""Seeded household samplers for the in-distribution (ID) and out-of-distribution (OOD) sets.

`sample(set, seed, index)` always returns the same household. Nothing here needs PolicyEngine; the
threshold-edge family only records which cutoff to target, and `envgen.edges` moves the income there.
"""

from __future__ import annotations

import csv
import random
from functools import cache
from pathlib import Path

from envgen.household import Expenses, Household, Member
from scraper.parsers.regions import STATE_CODES

FPG_CSV = Path(__file__).resolve().parents[1] / "data" / "processed" / "hhs-poverty-guidelines.csv"

STATES = sorted(code for code in STATE_CODES.values() if code not in ("GU", "VI"))  # 50 states + DC
# Never used by the ID set. AK and NY have sub-state SNAP regions; AK and HI have their own poverty guidelines.
HELD_OUT_STATES = ("AK", "HI", "NY", "DC", "ME", "MS", "ND", "NM", "OR", "VT")
ID_STATES = tuple(s for s in STATES if s not in HELD_OUT_STATES)

# County codes as PolicyEngine names them, with the plain name the case text uses.
COUNTIES = {
    "AK": [("ANCHORAGE_MUNICIPALITY_AK", "Anchorage"),
           ("FAIRBANKS_NORTH_STAR_BOROUGH_AK", "Fairbanks North Star Borough"),
           ("JUNEAU_CITY_AND_BOROUGH_AK", "Juneau"),
           ("KENAI_PENINSULA_BOROUGH_AK", "Kenai Peninsula Borough"),
           ("BETHEL_CENSUS_AREA_AK", "Bethel Census Area"),
           ("NOME_CENSUS_AREA_AK", "Nome Census Area")],
    "NY": [("KINGS_COUNTY_NY", "Brooklyn (Kings County), New York City"),
           ("QUEENS_COUNTY_NY", "Queens County, New York City"),
           ("BRONX_COUNTY_NY", "the Bronx (Bronx County), New York City"),
           ("NASSAU_COUNTY_NY", "Nassau County"),
           ("SUFFOLK_COUNTY_NY", "Suffolk County"),
           ("ALBANY_COUNTY_NY", "Albany County"),
           ("ERIE_COUNTY_NY", "Erie County"),
           ("MONROE_COUNTY_NY", "Monroe County")],
}

OOD_FAMILIES = ("rare_shape", "threshold_edge", "held_out_state")  # assigned by index % 3: equal thirds
TWISTS = ("multigenerational", "self_employment", "disabled_member", "college_student",
          "large_household", "pregnant_member", "mixed_citizenship")
EDGE_PROGRAMS = ("snap", "eitc", "medicaid")
EDGE_OFFSET = (0.003, 0.01)  # income lands 0.3%-1% above or below the cutoff

SHAPES = ("single_adult", "couple", "single_parent", "two_parents")
SHAPE_WEIGHTS = (0.3, 0.15, 0.25, 0.3)

NAMES = (
    "Maria", "James", "Aisha", "Luis", "Mei", "David", "Fatima", "Carlos", "Grace", "Andre", "Priya", "Kevin",
    "Rosa", "Tyrone", "Linh", "Daniel", "Amara", "Jose", "Hannah", "Omar", "Keisha", "Miguel", "Sofia", "Brian",
    "Yesenia", "Ahmed", "Emily", "Malik", "Ana", "Tomas", "Nia", "Ethan", "Leilani", "Diego", "Chloe", "Samuel",
    "Imani", "Victor", "Hoa", "Marcus", "Elena", "Jamal", "Lucia", "Noah", "Zainab", "Ricardo", "Olivia", "Kofi",
    "Isabel", "Tariq", "Mariana", "Jordan", "Esperanza", "Wei", "Destiny", "Mateo", "Ruth", "Hector", "Kiara",
    "Ivan", "Naomi", "Andres", "Jasmine", "Pedro", "Abigail", "Mohammed", "Gloria", "Xavier", "Lena", "Dmitri",
)


@cache
def poverty_guidelines() -> dict[str, tuple[float, float]]:
    """{region: (first person, each additional person)} from the parsed 2026 HHS guidelines."""
    with FPG_CSV.open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["parameter"] in ("first_person", "additional_person")]
    values = {(r["region"], r["parameter"]): float(r["value"]) for r in rows}
    return {region: (values[(region, "first_person")], values[(region, "additional_person")])
            for region in ("CONTIGUOUS_US", "AK", "HI")}


def poverty_line(state: str, size: int) -> float:
    first, extra = poverty_guidelines()[state if state in ("AK", "HI") else "CONTIGUOUS_US"]
    return first + (size - 1) * extra


def sample(set_: str, seed: int, index: int, attempt: int = 0) -> Household:
    """The household at `index` in set `set_` ("id" or "ood") for `seed`. Deterministic.

    `attempt` > 0 draws a replacement, used when a threshold-edge household turns out to have no cutoff.
    """
    rng = random.Random(f"ttune:{set_}:{seed}:{index}" + (f":{attempt}" if attempt else ""))
    builder = _Builder(rng, set_, seed, index)
    if set_ == "id":
        return builder.typical(rng.choice(ID_STATES))
    if set_ != "ood":
        raise ValueError(f"unknown set {set_!r}")
    family, k = OOD_FAMILIES[index % 3], index // 3
    if family == "rare_shape":
        first = TWISTS[k % len(TWISTS)]  # cycle so every twist appears
        twists = [first]
        if rng.random() < 0.4:
            twists.append(rng.choice([t for t in TWISTS if t != first]))
        return builder.rare(rng.choice(ID_STATES), twists)
    if family == "threshold_edge":
        program = EDGE_PROGRAMS[k % len(EDGE_PROGRAMS)]
        return builder.at_edge(rng.choice(ID_STATES), program)
    return builder.typical(HELD_OUT_STATES[k % len(HELD_OUT_STATES)], shift="held_out_state")


class _Builder:
    """Shared building blocks. Every random choice goes through one rng, in a fixed order."""

    def __init__(self, rng: random.Random, set_: str, seed: int, index: int):
        self.rng, self.set, self.seed, self.index = rng, set_, seed, index
        self.names = rng.sample(NAMES, len(NAMES))

    # --- people -------------------------------------------------------------------------------

    def person(self, age: int, relationship: str, **kwargs) -> Member:
        n = len(self._members) + 1
        member = Member(f"p{n}", self.names[n - 1], age, relationship, **kwargs)
        self._members.append(member)
        return member

    def children(self, count: int, youngest_parent_age: int) -> None:
        oldest = max(0, min(17, youngest_parent_age - 16))
        for age in sorted((self.rng.randint(0, oldest) for _ in range(count)), reverse=True):
            self.person(age, "child")

    def shape(self, shape: str, n_children: int, min_head_age: int = 18) -> None:
        rng = self.rng
        head_age = rng.randint(max(min_head_age, 20 if n_children else 18), 64)
        self.person(head_age, "head")
        partner_age = None
        if shape in ("couple", "two_parents"):
            partner_age = max(18, min(64, head_age + rng.randint(-6, 6)))
            self.person(partner_age, "spouse")
        if n_children:
            self.children(n_children, min(head_age, partner_age or head_age))

    def random_shape(self, max_size: int = 5, with_children: bool | None = None) -> None:
        rng = self.rng
        while True:
            shape = rng.choices(SHAPES, SHAPE_WEIGHTS)[0]
            has_children = shape in ("single_parent", "two_parents")
            if with_children is None or has_children == with_children:
                break
        adults = 2 if shape in ("couple", "two_parents") else 1
        n_children = rng.randint(1, max_size - adults) if has_children else 0
        self.shape(shape, n_children)

    # --- money --------------------------------------------------------------------------------

    def wages(self, state: str, low: float = 0.5, high: float = 2.5) -> None:
        """Spread total wages over `low`-`high` times the poverty line for the household's size."""
        rng = self.rng
        adults = [m for m in self._members if m.relationship in ("head", "spouse")]
        earners = adults[:1] + [m for m in adults[1:] if rng.random() < 0.6]
        total = rng.uniform(low, high) * poverty_line(state, len(self._members)) / 12
        share = rng.uniform(0.3, 0.7) if len(earners) == 2 else 1.0
        for earner, part in zip(earners, (share, 1 - share)):
            earner.income["wages"] = max(1, round(total * part))

    def expenses(self) -> Expenses:
        rng = self.rng
        size = len(self._members)
        rent = min(2600, rng.randint(550, 1400) + 150 * (size - 1))
        rent = 5 * round(rent / 5)
        heating = rng.random() < 0.6
        adults = [m for m in self._members if m.relationship in ("head", "spouse")]
        young = any(m.relationship == "child" and m.age < 13 for m in self._members)
        all_work = all(m.income.get("wages") or m.income.get("self_employment") for m in adults)
        childcare = 10 * round(rng.randint(150, 900) / 10) if young and all_work and rng.random() < 0.5 else 0
        medical = {m.id: 10 * round(rng.randint(30, 400) / 10)
                   for m in self._members if m.age >= 60 or m.disabled}
        return Expenses(rent, heating, childcare, medical)

    def child_support(self) -> None:
        head = self._members[0]
        kids = any(m.relationship == "child" for m in self._members)
        spouse = any(m.relationship == "spouse" for m in self._members)
        if kids and not spouse and self.rng.random() < 0.25:
            head.income["child_support"] = 10 * round(self.rng.randint(100, 600) / 10)

    # --- whole households ---------------------------------------------------------------------

    def _start(self) -> None:
        self._members: list[Member] = []

    def _finish(self, state: str, shift: str, twists: list[str] | None = None, edge: dict | None = None) -> Household:
        county = area = None
        if state in COUNTIES:
            county, area = self.rng.choice(COUNTIES[state])
        expenses = self.expenses()
        return Household(f"{self.set}-{self.seed}-{self.index:04d}", self.set, self.seed, self.index, state,
                         self._members, expenses, county, area, shift, twists or [], edge)

    def typical(self, state: str, shift: str = "none") -> Household:
        """1-5 people, adults 18-64 on wages, one of four common shapes."""
        self._start()
        self.random_shape()
        self.wages(state)
        self.child_support()
        return self._finish(state, shift)

    def at_edge(self, state: str, program: str) -> Household:
        """A typical household whose wages `envgen.edges` will move to within 1% of `program`'s cutoff."""
        self._start()
        # EITC and Medicaid cutoffs are clearest with children (childless adults under 25 get no EITC,
        # and childless adults have no Medicaid group in non-expansion states).
        self.random_shape(with_children=True if program in ("eitc", "medicaid") else None)
        self.wages(state)
        side = self.rng.choice(("below", "above"))
        offset = round(self.rng.uniform(*EDGE_OFFSET), 4)
        edge = {"program": program, "side": side, "offset": offset if side == "above" else -offset}
        return self._finish(state, "threshold_edge", [f"edge_{program}"], edge)

    def rare(self, state: str, twists: list[str]) -> Household:
        """A typical household reshaped by one or two twists (applied in TWISTS order)."""
        rng = self.rng
        self._start()
        twists = sorted(twists, key=TWISTS.index)
        if "large_household" in twists:
            head_age = rng.randint(30, 55)
            self.person(head_age, "head")
            spouse_age = max(25, min(64, head_age + rng.randint(-5, 5)))
            self.person(spouse_age, "spouse")
            self.children(rng.randint(6, 10), min(head_age, spouse_age))
        elif "college_student" in twists or "mixed_citizenship" in twists:
            self.random_shape(max_size=5, with_children=True)
        else:
            self.random_shape()
        self.wages(state)
        self.child_support()
        adults = [m for m in self._members if m.relationship in ("head", "spouse")]
        for twist in twists:
            if twist == "multigenerational":
                for _ in range(rng.choice((1, 1, 2))):
                    grandparent = self.person(rng.randint(65, 88), "parent")
                    grandparent.income["social_security"] = 10 * round(rng.randint(900, 2000) / 10)
            elif twist == "self_employment":
                worker = adults[0]
                earnings = worker.income.pop("wages", 0) or round(poverty_line(state, len(self._members)) / 12)
                worker.income["self_employment"] = max(100, round(earnings * rng.uniform(0.6, 1.1)))
            elif twist == "disabled_member":
                member = rng.choice(self._members)
                member.disabled = True
                # Most disabled adults stop working and draw disability benefits; the self-employed keep working.
                if member.relationship in ("head", "spouse") and "self_employment" not in member.income \
                        and rng.random() < 0.7:
                    member.income.pop("wages", None)
                    member.income["social_security"] = 10 * round(rng.randint(800, 1800) / 10)
            elif twist == "college_student":
                parent_age = min(m.age for m in adults)
                if parent_age < 38:
                    for m in adults:
                        m.age = rng.randint(38, 55)
                student = self.person(rng.randint(18, 22), "child", student=True)
                if rng.random() < 0.5:
                    student.income["wages"] = 10 * round(rng.randint(300, 900) / 10)
            elif twist == "pregnant_member":
                candidates = [m for m in adults if m.age <= 44] or [adults[0]]
                mother = rng.choice(candidates)
                mother.age = min(mother.age, 44)
                mother.pregnant = True
            elif twist == "mixed_citizenship":
                (adults[1] if len(adults) > 1 else adults[0]).citizenship = "undocumented"
        return self._finish(state, "rare_shape", twists)
