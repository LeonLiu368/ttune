"""The prompt sent for every case. Changing the wording changes PROMPT_VERSION's hash, recorded with each run."""

from __future__ import annotations

import hashlib

PROMPT_VERSION = 1

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



def messages(case: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{case}\n\n{ANSWER_FORMAT}"}]


def prompt_hash() -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}\n{SYSTEM}\n{ANSWER_FORMAT}".encode()).hexdigest()[:16]
