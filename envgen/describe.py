"""Plain-text case summary: the facts a caseworker would have, with no eligibility hints."""

from __future__ import annotations

from envgen.household import Household, Member
from scraper.parsers.regions import STATE_CODES

STATE_NAMES = {code: name for name, code in STATE_CODES.items()}
INCOME_LABELS = {
    "wages": "Wages from a job",
    "self_employment": "Self-employment earnings, after business costs",
    "social_security": "Social Security benefits",
    "ssi": "Supplemental Security Income (SSI)",
    "child_support": "Child support received",
    "unemployment": "Unemployment benefits",
}
RELATIONSHIP_LABELS = {"spouse": "spouse", "child": "child", "parent": "parent"}


def money(amount: int) -> str:
    return f"${amount:,}"


def describe(household: Household) -> str:
    state = STATE_NAMES[household.state]
    where = f"{state}, in {household.area}" if household.area else state
    head = household.head
    together = ("1 person who lives alone and buys and prepares their own food." if household.size == 1 else
                f"{household.size} people who live together and buy and prepare food together.")
    lines = [
        f"Case {household.id}",
        f"Lives in: {where}",
        f"Household: {together}",
        "Everyone is a US citizen unless noted.",
        "",
        "Members:",
    ]
    for member in household.members:
        lines.append(f"- {_member_line(member, head)}")
        for kind, amount in member.income.items():
            lines.append(f"    {INCOME_LABELS[kind]}: {money(amount)} a month")

    expenses = household.expenses
    lines += ["", "Monthly expenses:", f"- Rent: {money(expenses.rent)}"]
    lines.append("- Heating or cooling: paid separately from rent" if expenses.heating_cooling
                 else "- Heating or cooling: included in rent")
    if expenses.childcare:
        lines.append(f"- Childcare: {money(expenses.childcare)}")
    for member_id, amount in expenses.medical.items():
        lines.append(f"- Out-of-pocket medical costs for {household.member(member_id).name}: {money(amount)}")
    lines += ["", "No one has savings or other assets beyond a little cash."]
    return "\n".join(lines) + "\n"


def _member_line(member: Member, head: Member) -> str:
    who = "head of household" if member.relationship == "head" else \
        f"{head.name}'s {RELATIONSHIP_LABELS[member.relationship]}"
    facts = [f"{member.name}, age {member.age}, {who}."]
    if member.pregnant:
        facts.append("Pregnant.")
    if member.disabled:
        facts.append("Has a disability.")
    if member.student:
        facts.append("Full-time college student.")
    if member.citizenship == "undocumented":
        facts.append("Not a US citizen; has no lawful immigration status and no Social Security number.")
    if not member.income and member.relationship in ("head", "spouse"):
        facts.append("No income.")
    return " ".join(facts)
