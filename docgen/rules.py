"""How the documents turn into monthly figures. The model reads these rules (evals/prompt.py), and the renderer
picks every printed number so that applying them gives back the household's exact monthly amounts."""

from __future__ import annotations

from fractions import Fraction

from docgen.model import round_half_up

# Pay periods to months: the standard SNAP conversion factors.
FREQUENCIES = {"weekly": Fraction(43, 10), "biweekly": Fraction(43, 20), "semimonthly": Fraction(2), "monthly": Fraction(1)}
WEEKS_PER_MONTH = Fraction(43, 10)

RULES = """How to read the documents:
- Current income comes from the most recent documents. Older pay stubs and past-year figures don't count.
- Wages: average the gross pay (before deductions) on the two most recent pay stubs, then convert to a month: \
weekly × 4.3, every two weeks × 2.15, twice a month × 2, monthly × 1.
- Self-employment: average the last three months of net earnings (payouts minus business costs).
- Child support and medical costs: average the last three months.
- Unemployment: the weekly benefit amount × 4.3.
- Social Security: the monthly benefit amount before any deductions.
- Round each monthly figure to the nearest dollar.
- When the application and a document disagree, the document wins. The household is the people the \
application says live there now.
- If something needed is missing from the packet, say so: answer "unknown" where the gap could change the \
answer."""


def monthly_from_pay(gross_cents: list[int], frequency: str) -> int:
    return round_half_up(Fraction(sum(gross_cents), 100 * len(gross_cents)) * FREQUENCIES[frequency])


def monthly_average(cents: list[int]) -> int:
    return round_half_up(Fraction(sum(cents), 100 * len(cents)))


def monthly_from_weekly(weekly_cents: int) -> int:
    return round_half_up(Fraction(weekly_cents, 100) * WEEKS_PER_MONTH)


def pay_total(monthly: int, frequency: str, stubs: int = 2) -> int:
    """Total gross cents across `stubs` pay stubs whose average converts back to exactly `monthly` dollars."""
    guess = round_half_up(Fraction(monthly * 100 * stubs) / FREQUENCIES[frequency])
    for delta in sorted(range(-stubs * 50, stubs * 50 + 1), key=abs):
        if round_half_up(Fraction(guess + delta, 100 * stubs) * FREQUENCIES[frequency]) == monthly:
            return guess + delta
    raise ValueError(f"no pay total converts back to ${monthly} for {frequency} pay")


def weekly_benefit(monthly: int) -> int:
    """Weekly benefit cents that convert back to exactly `monthly` dollars."""
    guess = round_half_up(Fraction(monthly * 100) / WEEKS_PER_MONTH)
    for delta in sorted(range(-50, 51), key=abs):
        if monthly_from_weekly(guess + delta) == monthly:
            return guess + delta
    raise ValueError(f"no weekly amount converts back to ${monthly}")
