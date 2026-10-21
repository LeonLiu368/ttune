"""Correct answers from PolicyEngine. Many households run in one simulation, which is far faster than one each."""

from __future__ import annotations

from functools import cache
from importlib import metadata

from envgen.household import Household, Member

YEAR = "2026"  # inputs are annual for calendar 2026 (monthly amounts × 12)
PERIODS = {"snap": "2026-10", "wic": "2026-10", "eitc": 2026, "medicaid": 2026}  # SNAP Oct 2026 = FY2027 rules

# ttune field -> PolicyEngine input variable. Checked against the installed package before any simulation.
PERSON_INPUTS = {
    "age": "age",
    "pregnant": "is_pregnant",
    "disabled": "is_disabled",
    "student": "is_full_time_college_student",
    "student_for_tax": "is_full_time_student",
    "citizenship": "immigration_status",
    "ssn": "ssn_card_type",
    "wages": "employment_income",
    "self_employment": "self_employment_income",
    "social_security_retirement": "social_security_retirement",  # social_security for members 65+
    "social_security_disability": "social_security_disability",  # social_security for members under 65
    "ssi": "ssi",
    "child_support": "child_support_received",
    "unemployment": "unemployment_compensation",
    "rent": "rent",
    "medical": "other_medical_expenses",
    "tax_head": "is_tax_unit_head",
    "tax_spouse": "is_tax_unit_spouse",
    "tax_dependent": "is_tax_unit_dependent",
    "takes_up_ssi": "takes_up_ssi_if_eligible",
}
SPM_INPUTS = {
    "childcare": "childcare_expenses",
    "heating_cooling": "has_heating_cooling_expense",
    "takes_up_tanf": "takes_up_tanf_if_eligible",
    "takes_up_snap": "takes_up_snap_if_eligible",
}
HOUSEHOLD_INPUTS = {"state": "state_code_str", "county": "county"}
OUTPUTS = {
    "snap": "snap",
    "snap_eligible": "is_snap_eligible",
    # Each person's unearned income for SNAP before any proration for excluded members (e.g. undocumented).
    "snap_unearned_income_person": "snap_unearned_income_person",
    "eitc": "eitc",
    "wic": "wic",
    "wic_eligible": "is_wic_eligible",
    "medicaid_eligible": "is_medicaid_eligible",
    "chip_eligible": "is_chip_eligible",
    "snap_gross_income_fpg_ratio": "snap_gross_income_fpg_ratio",
    "medicaid_income_level": "medicaid_income_level",
}
CITIZENSHIP = {"citizen": ("CITIZEN", "CITIZEN"), "undocumented": ("UNDOCUMENTED", "NONE")}
UNEARNED = ("social_security", "ssi", "child_support", "unemployment")
# SNAP income sources that come from the case's own inputs. Every other source PolicyEngine can compute
# (state SSI supplements, Colorado's Old Age Pension, TANF, ...) is pinned to $0: the case lists all income.
DECLARED_SOURCES = {"ssi", "social_security", "total_unemployment_compensation"}


class TruthError(Exception):
    pass


@cache
def system():
    from policyengine_us import CountryTaxBenefitSystem

    tbs = CountryTaxBenefitSystem()
    names = [*PERSON_INPUTS.values(), *SPM_INPUTS.values(), *HOUSEHOLD_INPUTS.values(), *OUTPUTS.values()]
    missing = sorted({n for n in names if n not in tbs.variables})
    if missing:
        raise TruthError(f"policyengine-us {version()} has no variables named {missing}; update envgen/truth.py")
    return tbs


def version() -> str:
    return metadata.version("policyengine-us")


@cache
def undeclared_sources() -> dict[str, list[tuple[str, str]]]:
    """{entity: [(variable, period), ...]} for SNAP income sources PolicyEngine computes but no case declares."""
    tbs = system()
    p = tbs.parameters(f"{PERIODS['snap']}-01").gov.usda.snap.income.sources
    out: dict[str, list[tuple[str, str]]] = {"person": [], "spm_unit": []}
    for name in [*p.unearned, *p.unearned_spm_unit]:
        variable = tbs.variables[name]
        if name in DECLARED_SOURCES or not (variable.formulas or variable.adds):
            continue
        out[variable.entity.key].append((name, str(variable.definition_period)))
    return out


def _zero(period: str) -> dict:
    if period == "month":
        return {f"{YEAR}-{month:02d}": 0 for month in range(1, 13)}
    return _year(0)


# --- building the situation ---------------------------------------------------------------------

def tax_units(household: Household) -> list[list[Member]]:
    """The head's unit (head, spouse, children under 19 or students under 24), then one unit per other adult."""
    main, others = [], []
    for m in household.members:
        if m.relationship in ("head", "spouse") or (m.relationship == "child" and (m.age < 19 or (m.student and m.age < 24))):
            main.append(m)
        else:
            others.append([m])
    return [main, *others]


def _year(value) -> dict:
    return {YEAR: value}


def _person(household: Household, m: Member, role: str) -> dict:
    immigration, ssn = CITIZENSHIP[m.citizenship]
    inc = m.income
    social_security = inc.get("social_security", 0) * 12
    person = {
        PERSON_INPUTS["age"]: _year(m.age),
        PERSON_INPUTS["pregnant"]: _year(m.pregnant),
        PERSON_INPUTS["disabled"]: _year(m.disabled),
        PERSON_INPUTS["student"]: _year(m.student),
        PERSON_INPUTS["student_for_tax"]: _year(m.student),
        PERSON_INPUTS["citizenship"]: _year(immigration),
        PERSON_INPUTS["ssn"]: _year(ssn),
        PERSON_INPUTS["wages"]: _year(inc.get("wages", 0) * 12),
        PERSON_INPUTS["self_employment"]: _year(inc.get("self_employment", 0) * 12),
        PERSON_INPUTS["social_security_retirement"]: _year(social_security if m.age >= 65 else 0),
        PERSON_INPUTS["social_security_disability"]: _year(0 if m.age >= 65 else social_security),
        PERSON_INPUTS["child_support"]: _year(inc.get("child_support", 0) * 12),
        PERSON_INPUTS["unemployment"]: _year(inc.get("unemployment", 0) * 12),
        PERSON_INPUTS["rent"]: _year(household.expenses.rent * 12 if m.relationship == "head" else 0),
        PERSON_INPUTS["medical"]: _year(household.expenses.medical.get(m.id, 0) * 12),
        PERSON_INPUTS["tax_head"]: _year(role == "head"),
        PERSON_INPUTS["tax_spouse"]: _year(role == "spouse"),
        PERSON_INPUTS["tax_dependent"]: _year(role == "dependent"),
        # SSI is only counted when the case says the person receives it: PolicyEngine would otherwise add it.
        PERSON_INPUTS["takes_up_ssi"]: _year(False),
    }
    if inc.get("ssi"):
        person[PERSON_INPUTS["ssi"]] = {f"{YEAR}-{month:02d}": inc["ssi"] for month in range(1, 13)}
    for name, period in undeclared_sources()["person"]:
        person[name] = _zero(period)
    return person


def situation(households: list[Household]) -> dict:
    """One PolicyEngine situation holding every household. Entity ids are prefixed with the household id."""
    sit = {k: {} for k in ("people", "tax_units", "spm_units", "households", "families", "marital_units")}
    for h in households:
        pid = lambda m: f"{h.id}:{m.id}"  # noqa: E731
        units = tax_units(h)
        for n, unit in enumerate(units):
            for m in unit:
                role = "head" if m is unit[0] else "spouse" if m.relationship == "spouse" else "dependent"
                sit["people"][pid(m)] = _person(h, m, role)
            sit["tax_units"][f"{h.id}:tax{n}"] = {"members": [pid(m) for m in unit]}
        everyone = [pid(m) for m in h.members]
        sit["spm_units"][f"{h.id}:spm"] = {
            "members": everyone,
            SPM_INPUTS["childcare"]: _year(h.expenses.childcare * 12),
            SPM_INPUTS["heating_cooling"]: _year(h.expenses.heating_cooling),
            SPM_INPUTS["takes_up_tanf"]: _year(False),  # TANF cash isn't in the case; don't let it appear
            SPM_INPUTS["takes_up_snap"]: _year(True),
            **{name: _zero(period) for name, period in undeclared_sources()["spm_unit"]},
        }
        hh = {"members": everyone, HOUSEHOLD_INPUTS["state"]: _year(h.state)}
        if h.county:
            hh[HOUSEHOLD_INPUTS["county"]] = _year(h.county)
        sit["households"][f"{h.id}:hh"] = hh
        sit["families"][f"{h.id}:family"] = {"members": everyone}
        couple = [m for m in h.members if m.relationship in ("head", "spouse")]
        if len(couple) == 2:
            sit["marital_units"][f"{h.id}:couple"] = {"members": [pid(m) for m in couple]}
        for m in h.members:
            if len(couple) != 2 or m not in couple:
                sit["marital_units"][f"{h.id}:{m.id}:single"] = {"members": [pid(m)]}
    # People must be listed in the order their units list them, so slices line up per household.
    order = [p for unit in sit["tax_units"].values() for p in unit["members"]]
    sit["people"] = {p: sit["people"][p] for p in order}
    return sit


# --- running it ---------------------------------------------------------------------------------

def simulate(households: list[Household]):
    from policyengine_us import Simulation

    system()  # fail early on renamed variables
    return Simulation(situation=situation(households))


def _person_order(households: list[Household]) -> list[tuple[Household, Member]]:
    return [(h, m) for h in households for unit in tax_units(h) for m in unit]


def compute(households: list[Household]) -> list[dict]:
    """The correct answer for each household, in order."""
    if not households:
        return []
    sim = simulate(households)
    calc = lambda name, period: sim.calculate(OUTPUTS[name], period)  # noqa: E731
    snap, snap_eligible = calc("snap", PERIODS["snap"]), calc("snap_eligible", PERIODS["snap"])
    unearned = calc("snap_unearned_income_person", PERIODS["snap"])
    eitc = calc("eitc", PERIODS["eitc"])
    wic, wic_eligible = calc("wic", PERIODS["wic"]), calc("wic_eligible", PERIODS["wic"])
    medicaid, chip = calc("medicaid_eligible", PERIODS["medicaid"]), calc("chip_eligible", PERIODS["medicaid"])

    people = _person_order(households)
    by_household: dict[str, dict[str, list]] = {
        h.id: {"wic": [], "wic_eligible": [], "medicaid": [], "chip": [], "unearned": []} for h in households}
    for i, (h, m) in enumerate(people):
        row = by_household[h.id]
        row["unearned"].append(float(unearned[i]))
        row["wic"].append(float(wic[i]))
        if wic_eligible[i]:
            row["wic_eligible"].append(m.id)
        if medicaid[i]:
            row["medicaid"].append(m.id)
        if chip[i]:
            row["chip"].append(m.id)

    results, unit = [], 0
    for n, h in enumerate(households):
        units = len(tax_units(h))
        eitc_total = float(sum(eitc[unit:unit + units]))
        unit += units
        row = by_household[h.id]
        declared = sum(m.income.get(k, 0) for m in h.members for k in UNEARNED)
        counted = sum(row["unearned"])
        if abs(counted - declared) > 1:
            raise TruthError(f"{h.id}: PolicyEngine counts ${counted:,.2f}/month of unearned income for SNAP, "
                             f"but the case declares ${declared:,}; something it computed is leaking in")
        results.append({
            "snap": {"eligible": bool(snap_eligible[n]) and float(snap[n]) > 0,
                     "monthly_benefit": round(float(snap[n]), 2)},
            "eitc": {"eligible": eitc_total > 0, "annual_amount": round(eitc_total, 2)},
            "wic": {"eligible_members": sorted(row["wic_eligible"], key=_member_key),
                    "monthly_value": round(sum(row["wic"]), 2)},
            "medicaid": {"eligible_members": sorted(row["medicaid"], key=_member_key)},
            "chip": {"eligible_members": sorted(row["chip"], key=_member_key)},
        })
    return results


def _member_key(member_id: str) -> int:
    return int(member_id.removeprefix("p"))


def eligible(truth: dict, program: str) -> bool:
    """One yes/no per program per household, for balance checks."""
    if program in ("snap", "eitc"):
        return truth[program]["eligible"]
    return bool(truth[program]["eligible_members"])
