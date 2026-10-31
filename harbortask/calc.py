"""benefits-calc: PolicyEngine as a caseworker's calculator, inside a task's container.

    benefits-calc household.json      # or - for stdin
    benefits-calc --example           # a filled-in input to start from

It takes the household's facts, as read from the documents, and returns SNAP, EITC, WIC and Medicaid for the
task's periods. It runs the same code (envgen.truth) that computed the answer key, so correct facts give exactly
the right answer. Reading the documents, applying the conversion rules and spotting what's missing is the job.

In a task image this file sits next to envgen/ (household.py, truth.py) and data.json (state and area names).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXAMPLE = {
    "state": "OH",
    "area": None,
    "members": [
        {"name": "Ana", "age": 30, "relationship": "head", "income": {"wages": 1800}},
        {"name": "Leo", "age": 3, "relationship": "child"},
    ],
    "expenses": {"rent": 900, "heating_cooling": True, "childcare": 0, "medical": {}},
}
HELP = """Input (JSON):
  state           postal code ("OH") or name ("Ohio")
  area            only in Alaska and New York: the city or county as the documents print it, e.g. "Anchorage"
  members         list, the head first. Each member:
    name          first name
    age           whole years
    relationship  head, spouse, child, or parent (a parent of the head)
    pregnant, disabled, student (full-time college): true/false, default false
    citizenship   citizen (default) or undocumented
    income        monthly dollars by type: wages, self_employment, social_security, ssi, child_support, unemployment
  expenses
    rent          monthly dollars
    heating_cooling  true if heating or cooling is paid separately from rent
    childcare     monthly dollars
    medical       {"<name>": monthly out-of-pocket dollars}, for members 60 or older or with a disability

All amounts are whole dollars a month. Output: each program's answer for the task's periods
(SNAP October 2026, EITC tax year 2026, WIC October 2026, Medicaid 2026)."""


class InputError(ValueError):
    pass


def _data() -> dict:
    return json.loads((Path(__file__).resolve().parent / "data.json").read_text())


def to_household(facts: dict, data: dict | None = None):
    from envgen.household import Expenses, Household, Member

    data = data or _data()
    if not isinstance(facts, dict):
        raise InputError("the input must be a JSON object; run benefits-calc --example")
    state = str(facts.get("state", "")).strip()
    codes = {name.casefold(): code for name, code in data["states"].items()}
    state = state.upper() if state.upper() in data["states"].values() else codes.get(state.casefold())
    if not state:
        raise InputError(f"unknown state {facts.get('state')!r}: use a postal code like \"OH\"")
    county = area = None
    if state in data["counties"]:
        area = facts.get("area")
        match = [code for code, name in data["counties"][state] if area and str(area).casefold() in name.casefold()]
        if len(match) != 1:
            names = ", ".join(name for _, name in data["counties"][state])
            raise InputError(f"{state} needs \"area\", one of: {names}")
        county = match[0]
    members_in = facts.get("members")
    if not isinstance(members_in, list) or not members_in:
        raise InputError("\"members\" must be a non-empty list, the head first")
    members, ids = [], {}
    for n, m in enumerate(members_in, start=1):
        if not isinstance(m, dict) or "name" not in m or "age" not in m:
            raise InputError(f"member {n} needs at least a name and an age")
        income = {k: int(round(v)) for k, v in (m.get("income") or {}).items() if v}
        try:
            member = Member(f"p{n}", str(m["name"]), int(m["age"]), m.get("relationship", "head" if n == 1 else "child"),
                            bool(m.get("pregnant", False)), bool(m.get("disabled", False)), bool(m.get("student", False)),
                            m.get("citizenship", "citizen"), income)
        except (ValueError, TypeError) as exc:
            raise InputError(f"member {n}: {exc}") from None
        members.append(member)
        ids[member.name.casefold()] = member.id
    if members[0].relationship != "head":
        raise InputError("the first member must be the head of household")
    e = facts.get("expenses") or {}
    medical = {}
    for name, amount in (e.get("medical") or {}).items():
        if str(name).casefold() not in ids:
            raise InputError(f"medical costs for {name!r}, who isn't a member")
        medical[ids[str(name).casefold()]] = int(round(amount))
    expenses = Expenses(int(round(e.get("rent", 0))), bool(e.get("heating_cooling", False)),
                        int(round(e.get("childcare", 0))), medical)
    return Household("calc", "id", 0, 0, state, members, expenses, county, area)


def calculate(facts: dict, data: dict | None = None) -> dict:
    from envgen import truth

    household = to_household(facts, data)
    result = truth.compute([household])[0]
    names = {m.id: m.name for m in household.members}
    for program in ("medicaid", "wic", "chip"):
        result[program]["eligible_members"] = [names[i] for i in result[program]["eligible_members"]]
    return result


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[0].strip() + "\n\n" + HELP)
        return 0
    if args[0] == "--example":
        print(json.dumps(EXAMPLE, indent=2))
        return 0
    try:
        text = sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text()
        facts = json.loads(text)
        print(json.dumps(calculate(facts), indent=2))
        return 0
    except FileNotFoundError:
        print(f"error: no such file: {args[0]}", file=sys.stderr)
    except json.JSONDecodeError as exc:
        print(f"error: not valid JSON: {exc}", file=sys.stderr)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
