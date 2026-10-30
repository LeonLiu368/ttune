"""Documents as data. The text and PDF renderers draw the same blocks, so the two never disagree.

A document is a list of pages; a page is a list of blocks:

- {"type": "fields", "title": str | None, "rows": [[label, value], ...]}
- {"type": "table", "title": str | None, "columns": [...], "rows": [[...], ...], "numeric": [column indexes]}
- {"type": "text", "text": str}

Pages keep their original numbers ("Page 3 of 3"), so a missing page shows as a gap in the numbering.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from fractions import Fraction


@dataclass
class Page:
    number: int
    of: int
    blocks: list[dict]


@dataclass
class Document:
    kind: str  # application, pay_stub, earnings_ledger, benefit_letter, ... (see docgen.documents)
    title: str
    issuer: list[str]  # header lines: who sent it, their address
    date: str  # ISO date the document is dated
    pages: list[Page]
    about: str | None = None  # member id the document is about, if any
    name: str = ""  # file stem, set when the packet is numbered: "03-pay-stub"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Document:
        data = dict(data)
        data["pages"] = [Page(**p) for p in data["pages"]]
        return cls(**data)


@dataclass
class Issue:
    """Something injected on purpose. A gap leaves a fact the documents don't establish."""
    kind: str
    member: str | None
    detail: str  # what a careful reader should notice, in plain words
    gap: dict | None = None  # {"fact": "income"|"rent"|"childcare", "source": ..., "low": int, "high": int}
    flag: str | None = None  # the missing-information item a caseworker should request (gaps only)


@dataclass
class Packet:
    case_id: str
    documents: list[Document] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Packet:
        return cls(data["case_id"], [Document.from_dict(d) for d in data["documents"]],
                   [Issue(**i) for i in data["issues"]])

    @property
    def gaps(self) -> list[Issue]:
        return [i for i in self.issues if i.gap]


# --- money and dates -----------------------------------------------------------------------------

def dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def whole(amount: int) -> str:
    return f"${amount:,}"


def round_half_up(value: Fraction) -> int:
    """Nearest whole number, halves up. The documents' stated rule for turning averages into monthly dollars."""
    return int((value * 2 + 1) // 2)


def long_date(day: date) -> str:
    return f"{day:%B} {day.day}, {day.year}"


def short_date(day: date) -> str:
    return f"{day.month:02d}/{day.day:02d}/{day.year}"
