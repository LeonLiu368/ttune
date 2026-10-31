"""A synthetic household: the facts a caseworker would have, in a JSON-friendly shape. All amounts are whole dollars."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

SETS = ("id", "ood")
SHIFTS = ("none", "rare_shape", "threshold_edge", "held_out_state")
RELATIONSHIPS = ("head", "spouse", "child", "parent")  # "parent" = a parent of the head (a grandparent)
CITIZENSHIP = ("citizen", "undocumented")
# Monthly income by type. "ssi" is in the schema but no sampler uses it yet: PolicyEngine computes SSI itself.
INCOME_TYPES = ("wages", "self_employment", "social_security", "ssi", "child_support", "unemployment")


@dataclass
class Member:
    id: str  # p1, p2, ... in the order the case text lists them
    name: str
    age: int
    relationship: str
    pregnant: bool = False
    disabled: bool = False
    student: bool = False  # full-time college student
    citizenship: str = "citizen"
    income: dict[str, int] = field(default_factory=dict)  # monthly, nonzero types only

    def __post_init__(self):
        if self.relationship not in RELATIONSHIPS:
            raise ValueError(f"{self.id}: unknown relationship {self.relationship!r}")
        if self.citizenship not in CITIZENSHIP:
            raise ValueError(f"{self.id}: unknown citizenship {self.citizenship!r}")
        unknown = set(self.income) - set(INCOME_TYPES)
        if unknown:
            raise ValueError(f"{self.id}: unknown income types {sorted(unknown)}")


@dataclass
class Expenses:
    rent: int  # monthly
    heating_cooling: bool  # pays for heating or cooling separately from rent
    childcare: int = 0  # monthly
    medical: dict[str, int] = field(default_factory=dict)  # monthly out-of-pocket, by member id (60+ or disabled)


@dataclass
class Household:
    id: str
    set: str
    seed: int
    index: int
    state: str  # postal code
    members: list[Member]
    expenses: Expenses
    county: str | None = None  # PolicyEngine county code, only where SNAP has sub-state regions (AK, NY)
    area: str | None = None  # the county or city in plain words, for the case text
    shift: str = "none"
    twists: list[str] = field(default_factory=list)
    edge: dict | None = None  # threshold_edge only: which cutoff, which side, how far (see envgen/edges.py)

    def __post_init__(self):
        if self.set not in SETS:
            raise ValueError(f"{self.id}: unknown set {self.set!r}")
        if self.shift not in SHIFTS:
            raise ValueError(f"{self.id}: unknown shift {self.shift!r}")

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def head(self) -> Member:
        return self.members[0]

    def member(self, member_id: str) -> Member:
        return next(m for m in self.members if m.id == member_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Household:
        data = dict(data)
        data["members"] = [Member(**m) for m in data["members"]]
        data["expenses"] = Expenses(**data["expenses"])
        return cls(**data)
