"""Parse a model's reply into an answer. A reply that can't be read is malformed, and scored as wrong."""

from __future__ import annotations

import json
import re

PROGRAMS = ("snap", "eitc", "medicaid", "wic")
AMOUNT_KEYS = {"snap": "monthly_benefit", "eitc": "annual_amount"}  # programs with one household-level decision
MEMBER_PROGRAMS = ("medicaid", "wic")  # one decision per member
UNKNOWN = "unknown"
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


class Malformed(ValueError):
    pass


def _key(name: str) -> str:
    return "".join(name.split()).casefold()


def last_json_object(text: str) -> dict:
    """The last JSON object in the reply: the last ```json block if there is one, else the last {...} that parses."""
    blocks = FENCE.findall(text)
    for block in reversed(blocks):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    # No usable fence: take the last top-level {...} that parses, skipping objects nested inside it.
    decoder = json.JSONDecoder()
    found, i = None, text.find("{")
    while i >= 0:
        try:
            value, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
            continue
        if isinstance(value, dict):
            found = value
        i = text.find("{", end)
    if found is None:
        raise Malformed("no JSON object in the reply")
    return found


def parse_answer(text: str, names: dict[str, str]) -> tuple[dict | None, str | None]:
    """(answer, None) or (None, why it's malformed). `names` maps each member's name to their id.

    The answer uses member ids:
    {"snap": {"eligible": True|False|"unknown", "amount": float|None}, "eitc": {...},
     "medicaid": {"members": [ids], "unknown": [ids], "unknown_names": [...]}, "wic": {...}}

    "unknown" holds members listed under "unknown_members" (document cases) and not also listed as eligible.
    """
    try:
        return _parse(last_json_object(text or ""), names), None
    except Malformed as exc:
        return None, str(exc)


def _parse(data: dict, names: dict[str, str]) -> dict:
    lookup = {_key(name): member_id for name, member_id in names.items()}
    answer: dict = {}
    for program in PROGRAMS:
        part = data.get(program)
        if not isinstance(part, dict):
            raise Malformed(f"'{program}' is missing or not an object")
        if program in AMOUNT_KEYS:
            eligible = part.get("eligible")
            if isinstance(eligible, str) and eligible.strip().lower() == UNKNOWN:
                eligible = UNKNOWN
            elif not isinstance(eligible, bool):
                raise Malformed(f"'{program}.eligible' must be true, false or \"unknown\", got {eligible!r}")
            amount = part.get(AMOUNT_KEYS[program])
            if isinstance(amount, str):
                amount = _number(amount)
            if amount is not None and (isinstance(amount, bool) or not isinstance(amount, (int, float))):
                raise Malformed(f"'{program}.{AMOUNT_KEYS[program]}' must be a number, got {amount!r}")
            answer[program] = {"eligible": eligible, "amount": None if amount is None else float(amount)}
        else:
            listed = part.get("eligible_members")
            if not isinstance(listed, list) or not all(isinstance(n, str) for n in listed):
                raise Malformed(f"'{program}.eligible_members' must be a list of names")
            undecided = part.get("unknown_members", [])
            if not isinstance(undecided, list) or not all(isinstance(n, str) for n in undecided):
                raise Malformed(f"'{program}.unknown_members' must be a list of names")
            members, maybe, unknown = [], [], []
            for name, bucket in [*((n, members) for n in listed), *((n, maybe) for n in undecided)]:
                member_id = lookup.get(_key(name))
                if member_id is None:
                    unknown.append(name)
                elif member_id not in members and member_id not in bucket:
                    bucket.append(member_id)
            answer[program] = {"members": members, "unknown": [m for m in maybe if m not in members],
                               "unknown_names": unknown}
    return answer


def _number(text: str) -> float | None:
    cleaned = text.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
