"""The prompt sent for every case. Changing the wording changes PROMPT_VERSION's hash, recorded with each run."""

from __future__ import annotations

import hashlib

from docgen.rules import RULES

PROMPT_VERSION = 1
DOCUMENT_PROMPT_VERSION = 1

SYSTEM = """You are an experienced public-benefits caseworker in the United States. You read a household's case \
and decide which federal benefits it qualifies for, using the rules in effect for these periods:

- SNAP: October 2026 (federal fiscal year 2027 rules, plus the household's state rules). Give the monthly benefit.
- EITC: federal earned income tax credit for tax year 2026. Give the annual credit for the household (add up all \
tax filers in the household).
- Medicaid: 2026, under the household's state rules. Medicaid only, not CHIP. List each member who qualifies.
- WIC: October 2026. List each member who qualifies.

Assume the household applies for every program, and that the case lists all of its income and expenses."""

ANSWER_FORMAT = """Answer format (end your reply with exactly one ```json block like this):

```json
{
  "snap": {"eligible": true, "monthly_benefit": 0},
  "eitc": {"eligible": true, "annual_amount": 0},
  "medicaid": {"eligible_members": ["First name", "..."]},
  "wic": {"eligible_members": ["First name", "..."]}
}
```

- "eligible" is true or false. Use "unknown" only if the case truly doesn't let you decide.
- Amounts are in US dollars. Give 0 when not eligible.
- Name members exactly as the case does. Use an empty list when no one qualifies.
- You may think step by step before the JSON block."""

# For cases built by docgen: the household's application and the documents they handed in.
DOCUMENT_SYSTEM = SYSTEM.replace(
    "Assume the household applies for every program, and that the case lists all of its income and expenses.",
    "The case is the household's application and the documents they handed in. Assume the household applies "
    "for every program.\n\n" + RULES)

DOCUMENT_ANSWER_FORMAT = """Answer format (end your reply with exactly one ```json block like this):

```json
{
  "snap": {"eligible": true, "monthly_benefit": 0},
  "eitc": {"eligible": true, "annual_amount": 0},
  "medicaid": {"eligible_members": ["First name", "..."], "unknown_members": []},
  "wic": {"eligible_members": ["First name", "..."], "unknown_members": []}
}
```

- "eligible" is true, false or "unknown". Say "unknown" only when a missing document could change the answer.
- "unknown_members" lists members whose Medicaid or WIC answer a missing document could change.
- Amounts are in US dollars. Give 0 when not eligible or unknown.
- Name members by first name, as the application does. Use an empty list when no one qualifies.
- You may think step by step before the JSON block."""


def _parts(documents: bool) -> tuple[str, str, str]:
    if documents:
        return f"documents-{DOCUMENT_PROMPT_VERSION}", DOCUMENT_SYSTEM, DOCUMENT_ANSWER_FORMAT
    return str(PROMPT_VERSION), SYSTEM, ANSWER_FORMAT


def messages(case: str, documents: bool = False) -> list[dict]:
    _, system, answer_format = _parts(documents)
    return [{"role": "system", "content": system}, {"role": "user", "content": f"{case}\n\n{answer_format}"}]


def version(documents: bool = False) -> int:
    return DOCUMENT_PROMPT_VERSION if documents else PROMPT_VERSION


def prompt_hash(documents: bool = False) -> str:
    tag, system, answer_format = _parts(documents)
    return hashlib.sha256(f"{tag}\n{system}\n{answer_format}".encode()).hexdigest()[:16]
