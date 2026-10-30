"""Build one household's paperwork: an application plus a document for every fact it claims.

`build(household)` is deterministic for a household. Every amount is chosen so that docgen.rules gives back the
household's exact monthly figures; `established(packet)` reads them back the same way and tests check the two
agree. Issues from docgen.noise change what's on the page, never the household behind it.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from fractions import Fraction

from docgen import fixtures, noise, rules
from docgen.model import Document, Issue, Packet, Page, dollars, long_date, round_half_up, short_date, whole
from envgen.describe import STATE_NAMES
from envgen.household import Household, Member

APPLICATION_DATE = date(2026, 10, 2)  # applying for October 2026 SNAP, the period the truth uses
YEAR_START = date(2026, 1, 1)
FREQUENCY_WEIGHTS = {"weekly": 0.3, "biweekly": 0.4, "semimonthly": 0.2, "monthly": 0.1}
FREQUENCY_LABELS = {"weekly": "Weekly", "biweekly": "Every two weeks", "semimonthly": "Twice a month",
                    "monthly": "Monthly"}
STALE_BACK = {"weekly": 9, "biweekly": 5, "semimonthly": 9, "monthly": 4}  # pay periods back for a stale stub
INCOME_SOURCE_LABELS = {"wages": "Job", "self_employment": "Self-employment", "social_security": "Social Security",
                        "ssi": "SSI", "child_support": "Child support", "unemployment": "Unemployment benefits"}
RELATIONSHIP_LABELS = {"head": "Self", "spouse": "Spouse", "child": "Child", "parent": "Parent"}
LEDGER_MONTHS = (date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1))


def build(household: Household) -> Packet:
    rng = random.Random(f"docgen:{household.id}")
    plans = noise.choose(household, random.Random(f"docgen-noise:{household.id}"))
    return _Builder(household, rng, plans).build()


# --- pay periods ---------------------------------------------------------------------------------

def _month_end(day: date) -> date:
    first_next = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_next - timedelta(days=1)


def pay_periods(frequency: str, count: int, before: date = APPLICATION_DATE) -> list[tuple[date, date, date]]:
    """The `count` most recent (period start, period end, pay date) before `before`, newest first."""
    out: list[tuple[date, date, date]] = []
    if frequency in ("weekly", "biweekly"):
        step = 7 if frequency == "weekly" else 14
        pay = before - timedelta(days=(before.weekday() - 4) % 7 or 7)  # the last Friday before
        while len(out) < count:
            end = pay - timedelta(days=6)
            out.append((end - timedelta(days=step - 1), end, pay))
            pay -= timedelta(days=step)
        return out
    day = before - timedelta(days=1)
    while len(out) < count:
        end = _month_end(day)
        if frequency == "semimonthly":
            for start, stop in ((day.replace(day=16), end), (day.replace(day=1), day.replace(day=15))):
                if stop < before and len(out) < count:
                    out.append((start, stop, stop))
        elif end < before:
            out.append((day.replace(day=1), end, end))
        day = day.replace(day=1) - timedelta(days=1)
    return out


def periods_so_far(frequency: str, pay: date) -> int:
    if frequency == "weekly":
        return (pay - YEAR_START).days // 7 + 1
    if frequency == "biweekly":
        return (pay - YEAR_START).days // 14 + 1
    if frequency == "semimonthly":
        return 2 * (pay.month - 1) + (1 if pay.day <= 15 else 2)
    return pay.month


def split_cents(total: int, parts: int, rng: random.Random, spread: float) -> list[int]:
    """`parts` positive amounts that vary by about ±spread and add up to exactly `total`."""
    weights = [1 + rng.uniform(-spread, spread) for _ in range(parts)]
    amounts = [round(total * w / sum(weights)) for w in weights]
    amounts[-1] = total - sum(amounts[:-1])
    return amounts


# --- the builder ---------------------------------------------------------------------------------

class _Builder:
    def __init__(self, household: Household, rng: random.Random, plans: list[dict]):
        self.h, self.rng, self.plans = household, rng, plans
        self.state = STATE_NAMES[household.state]
        surname = rng.choice(fixtures.SURNAMES)
        self.surnames = {m.id: surname for m in household.members}
        for m in household.members:
            if m.relationship == "spouse" and rng.random() < 0.3:
                self.surnames[m.id] = rng.choice([s for s in fixtures.SURNAMES if s != surname])
        self.town = household.area or rng.choice(fixtures.TOWNS)
        unit = f", Apt {rng.randint(1, 4)}{rng.choice('ABCD')}" if rng.random() < 0.6 else ""
        self.street = f"{rng.randint(100, 9899)} {rng.choice(fixtures.STREETS)}{unit}"
        self.jobs: dict[str, dict] = {}
        self.documents: list[Document] = []
        self.issues: list[Issue] = []
        self.stated: dict = {"income": [], "notes": []}

    # names and places

    def full(self, m: Member) -> str:
        return f"{m.name} {self.surnames[m.id]}"

    def variant(self, m: Member) -> str:
        short = fixtures.NICKNAMES.get(m.name)
        return f"{short} {self.surnames[m.id]}" if short else f"{m.name[0]}. {self.surnames[m.id]}"

    def written_name(self, m: Member) -> str:
        if self._plan("name_variant", m.id):
            return self.variant(m)
        return self.full(m)

    def address(self) -> list[str]:
        return [self.street, f"{self.town}, {self.state}"]

    def _plan(self, kind: str, member: str | None = None, source: str | None = None) -> dict | None:
        for p in self.plans:
            if p["kind"] == kind and (member is None or p.get("member") == member) and \
                    (source is None or p.get("source") == source):
                return p
        return None

    def add(self, doc: Document) -> None:
        self.documents.append(doc)

    # the packet

    def build(self) -> Packet:
        h = self.h
        for m in h.members:
            for source, monthly in m.income.items():
                gap = self._plan("missing_income_doc", m.id, source)
                self.stated["income"].append(self._stated_income(m, source, monthly, gap is not None))
                if gap:
                    self._gap_income(m, source)
                    continue
                getattr(self, f"_income_{source}")(m, monthly)
            if m.pregnant:
                self.add(self._pregnancy(m))
            if m.student:
                self.add(self._enrollment(m))
            if m.disabled and not (m.income.get("social_security") and m.age < 65):
                self.add(self._disability(m))
            if h.expenses.medical.get(m.id):
                self.add(self._pharmacy(m, h.expenses.medical[m.id]))
        self._housing()
        self._childcare()
        if self._plan("partner_moved_out"):
            self._partner_moved_out()
        for plan in self.plans:
            if plan["kind"] == "name_variant":
                m = h.member(plan["member"])
                self.issues.append(Issue("name_variant", m.id, f"A document names {self.full(m)} as {self.variant(m)}."))
        application = self._application()
        ordered = [application, *sorted(self.documents, key=lambda d: (d.date, d.kind))]
        for n, doc in enumerate(ordered, start=1):
            doc.name = f"{n:02d}-{doc.kind.replace('_', '-')}"
        return Packet(h.id, ordered, self.issues)

    # income documents

    def _stated_income(self, m: Member, source: str, monthly: int, missing: bool) -> list[str]:
        payer = {"wages": None, "self_employment": None, "social_security": "Social Security Administration",
                 "ssi": "Social Security Administration", "child_support": f"{self.state} Child Support Payment Center",
                 "unemployment": f"{self.state} unemployment insurance"}[source]
        if source == "wages":
            payer = self._wage_job(m)["employer"]
        if source == "self_employment":
            payer = self._platform(m)
        if missing:
            amount = "Not given"
        elif source in ("wages", "self_employment"):
            amount = f"About {whole(50 * round(monthly * self.rng.uniform(0.88, 1.12) / 50))} a month"
        else:
            amount = f"{whole(monthly)} a month"
        return [self.full(m), INCOME_SOURCE_LABELS[source], payer, amount]

    def _wage_job(self, m: Member) -> dict:
        if (m.id, "wages") not in self.jobs:
            self.jobs[(m.id, "wages")] = self._job()
        return self.jobs[(m.id, "wages")]

    def _platform(self, m: Member) -> str:
        if (m.id, "self_employment") not in self.jobs:
            self.jobs[(m.id, "self_employment")] = {"platform": self.rng.choice(fixtures.PLATFORMS)}
        return self.jobs[(m.id, "self_employment")]["platform"]

    def _job(self) -> dict:
        frequency = self.rng.choices(list(FREQUENCY_WEIGHTS), list(FREQUENCY_WEIGHTS.values()))[0]
        return {"employer": self.rng.choice(fixtures.EMPLOYERS), "frequency": frequency,
                "hourly": frequency in ("weekly", "biweekly") or self.rng.random() < 0.4}

    def _income_wages(self, m: Member, monthly: int) -> None:
        job = self._wage_job(m)
        frequency = job["frequency"]
        total = rules.pay_total(monthly, frequency)
        periods = pay_periods(frequency, 2)
        weeks = {"weekly": 1, "biweekly": 2, "semimonthly": Fraction(13, 6), "monthly": Fraction(13, 3)}[frequency]
        if job["hourly"]:
            hours_per_week = self.rng.uniform(22, 40)
            rate = max(1100, round(total / 2 / (hours_per_week * float(weeks))))
            rate = min(rate, 6500)
            first_hours = round(total / 2 / rate * self.rng.uniform(0.9, 1.1) * 4) / 4
            gross = [round(first_hours * rate)]
            gross.append(total - gross[0])
            job["rate"] = rate
        else:
            gross = [total // 2, total - total // 2]
        for (start, end, pay), amount in zip(periods, gross):
            self.add(self._pay_stub(m, job, start, end, pay, amount, ytd_scale=self.rng.uniform(0.93, 1.04)))
        stale = self._plan("stale_stub", m.id)
        if stale:
            start, end, pay = pay_periods(frequency, STALE_BACK[frequency] + 1)[-1]
            old = round(total / 2 * self.rng.uniform(0.7, 0.9))
            if job["hourly"]:
                job = {**job, "rate": round(job["rate"] * self.rng.uniform(0.9, 0.96))}
            self.add(self._pay_stub(m, job, start, end, pay, old, ytd_scale=1.0))
            self.issues.append(Issue("stale_stub", m.id, f"An older pay stub ({long_date(pay)}) for {self.full(m)} "
                                     "sits next to the two current ones; only the current two count."))

    def _pay_stub(self, m: Member, job: dict, start: date, end: date, pay: date, gross: int,
                  ytd_scale: float, name: str | None = None) -> Document:
        rng = self.rng
        earnings = []
        if job["hourly"]:
            rate = job["rate"]
            quarters = round(gross * 4 / rate)
            if round(quarters * rate / 4) > gross:
                quarters -= 1
            hours, regular = quarters / 4, round(quarters * rate / 4)
            earnings.append(["Regular", f"{hours:.2f}", dollars(rate), dollars(regular)])
            if gross - regular:
                earnings.append(["Shift differential", "", "", dollars(gross - regular)])
        else:
            earnings.append(["Salary", "", "", dollars(gross)])
        earnings.append(["Gross pay", "", "", dollars(gross)])
        taxes = [("Federal income tax", rng.uniform(0.03, 0.09)), ("Social Security", 0.062), ("Medicare", 0.0145)]
        if self.h.state not in fixtures.NO_WAGE_TAX:
            taxes.append((f"{self.h.state} state income tax", rng.uniform(0.01, 0.045)))
        if rng.random() < 0.35:
            taxes.append(("Health insurance (pre-tax)", rng.uniform(0.02, 0.06)))
        deductions = [[label, dollars(round(gross * share))] for label, share in taxes]
        net = gross - sum(round(gross * share) for _, share in taxes)
        ytd = max(gross, round(gross * periods_so_far(job["frequency"], pay) * ytd_scale))
        return Document("pay_stub", "Earnings statement", [job["employer"], f"{self.town}, {self.state}"],
                        pay.isoformat(), [Page(1, 1, [
                            {"type": "fields", "title": None, "rows": [
                                ["Employee", name or self.written_name(m)],
                                ["Pay period", f"{short_date(start)} to {short_date(end)}"],
                                ["Pay date", short_date(pay)],
                                ["Pay frequency", FREQUENCY_LABELS[job["frequency"]]]]},
                            {"type": "table", "title": "Earnings", "columns": ["Description", "Hours", "Rate", "Current"],
                             "rows": earnings, "numeric": [1, 2, 3]},
                            {"type": "table", "title": "Deductions", "columns": ["Description", "Current"],
                             "rows": deductions, "numeric": [1]},
                            {"type": "fields", "title": None, "rows": [
                                ["Net pay", dollars(net)], ["Gross pay, year to date", dollars(ytd)]]},
                        ])], m.id)

    def _income_self_employment(self, m: Member, monthly: int) -> None:
        platform = self._platform(m)
        nets = split_cents(3 * monthly * 100, 3, self.rng, 0.25)
        rows = []
        for month, net in zip(LEDGER_MONTHS, nets):
            costs = round(net * self.rng.uniform(0.15, 0.4))
            rows.append([f"{month:%B %Y}", dollars(net + costs), dollars(costs), dollars(net)])
        self.add(Document("earnings_ledger", "Self-employment earnings log", [self.written_name(m), *self.address()],
                          date(2026, 10, 1).isoformat(), [Page(1, 1, [
                              {"type": "text", "text": f"Gig work through {platform}. Payouts are what {platform} "
                                                       "deposited; business costs are mileage, phone and supplies."},
                              {"type": "table", "title": None,
                               "columns": ["Month", "Payouts", "Business costs", "Net earnings"],
                               "rows": rows, "numeric": [1, 2, 3]},
                          ])], m.id))

    def _income_social_security(self, m: Member, monthly: int) -> None:
        kind = "retirement" if m.age >= 65 else "disability"
        self.add(Document("benefit_letter", "Notice of your Social Security benefit",
                          ["Social Security Administration", "Retirement, Survivors and Disability Insurance"],
                          date(2025, 12, 3).isoformat(), [Page(1, 1, [
                              {"type": "text", "text": f"Dear {self.written_name(m)}: Beginning January 2026, the "
                                                       f"amount of your monthly Social Security {kind} benefit is "
                                                       "shown below."},
                              {"type": "fields", "title": None, "rows": [
                                  ["Benefit type", f"Social Security {kind}"],
                                  ["Monthly benefit before deductions", dollars(monthly * 100)],
                                  ["Paid on", "The second Wednesday of each month"]]},
                          ])], m.id))

    def _income_ssi(self, m: Member, monthly: int) -> None:
        self.add(Document("benefit_letter", "Notice of your Supplemental Security Income payment",
                          ["Social Security Administration", "Supplemental Security Income"],
                          date(2025, 12, 3).isoformat(), [Page(1, 1, [
                              {"type": "fields", "title": None, "rows": [
                                  ["Recipient", self.written_name(m)],
                                  ["Monthly SSI payment", dollars(monthly * 100)]]},
                          ])], m.id))

    def _income_child_support(self, m: Member, monthly: int) -> None:
        rows = []
        for month, amount in zip(LEDGER_MONTHS, split_cents(3 * monthly * 100, 3, self.rng, 0.3)):
            if self.rng.random() < 0.4:
                first = round(amount * self.rng.uniform(0.4, 0.6))
                rows += [[short_date(month.replace(day=self.rng.randint(1, 10))), dollars(first)],
                         [short_date(month.replace(day=self.rng.randint(15, 25))), dollars(amount - first)]]
            else:
                rows.append([short_date(month.replace(day=self.rng.randint(1, 20))), dollars(amount)])
        self.add(Document("payment_history", "Child support payment history",
                          [f"{self.state} Child Support Payment Center"], date(2026, 10, 1).isoformat(), [Page(1, 1, [
                              {"type": "fields", "title": None, "rows": [
                                  ["Recipient", self.written_name(m)],
                                  ["Case number", f"CS-{self.rng.randint(100000, 999999)}"],
                                  ["Payments shown", "July 1, 2026 to September 30, 2026"]]},
                              {"type": "table", "title": "Payments received", "columns": ["Date", "Amount"],
                               "rows": rows, "numeric": [1]},
                          ])], m.id))

    def _income_unemployment(self, m: Member, monthly: int) -> None:
        weekly = rules.weekly_benefit(monthly)
        self.add(Document("benefit_letter", "Monetary determination",
                          [f"{self.state} Department of Labor", "Unemployment Insurance"],
                          date(2026, 9, 8).isoformat(), [Page(1, 1, [
                              {"type": "fields", "title": None, "rows": [
                                  ["Claimant", self.written_name(m)],
                                  ["Benefit year begins", long_date(date(2026, 8, 30))],
                                  ["Weekly benefit amount", dollars(weekly)],
                                  ["Maximum benefit amount", dollars(weekly * 26)],
                                  ["Payment schedule", f"Every two weeks, {dollars(2 * weekly)} per payment"]]},
                          ])], m.id))

    def _gap_income(self, m: Member, source: str) -> None:
        label = INCOME_SOURCE_LABELS[source].lower()
        need = {"wages": "Pay stubs", "self_employment": "Self-employment earnings records",
                "social_security": "Social Security benefit letter", "ssi": "SSI benefit letter",
                "child_support": "Child support payment history",
                "unemployment": "Unemployment benefit letter"}[source]
        self.issues.append(Issue(
            "missing_income_doc", m.id, f"The application lists {label} income for {self.full(m)} but the packet "
            "has no document showing the amount.",
            gap={"fact": "income", "member": m.id, "source": source, "range": list(noise.income_range(self.h))},
            flag=f"{need} for {self.full(m)}"))

    # other facts

    def _pregnancy(self, m: Member) -> Document:
        due = APPLICATION_DATE + timedelta(days=self.rng.randint(40, 230))
        return Document("medical_letter", "Pregnancy verification", [self.rng.choice(fixtures.CLINICS)],
                        date(2026, 9, self.rng.randint(1, 28)).isoformat(), [Page(1, 1, [
                            {"type": "text", "text": f"This letter confirms that {self.written_name(m)} is pregnant. "
                                                     f"Expected delivery date: {long_date(due)}."}])], m.id)

    def _enrollment(self, m: Member) -> Document:
        return Document("enrollment_letter", "Enrollment verification", [self.rng.choice(fixtures.COLLEGES),
                                                                         "Office of the Registrar"],
                        date(2026, 9, self.rng.randint(1, 28)).isoformat(), [Page(1, 1, [
                            {"type": "text", "text": f"{self.written_name(m)} is enrolled full-time (12 or more "
                                                     "credit hours) for the Fall 2026 term, August 24 to December 12, "
                                                     "2026."}])], m.id)

    def _disability(self, m: Member) -> Document:
        return Document("benefit_letter", "Notice of disability determination",
                        [f"{self.state} Disability Determination Services"],
                        date(2026, self.rng.randint(1, 8), self.rng.randint(1, 28)).isoformat(), [Page(1, 1, [
                            {"type": "text", "text": f"We have determined that {self.written_name(m)} meets the "
                                                     "disability requirements. This determination stays in effect "
                                                     "until a review."}])], m.id)

    def _pharmacy(self, m: Member, monthly: int) -> Document:
        rows = []
        for month, amount in zip(LEDGER_MONTHS, split_cents(3 * monthly * 100, 3, self.rng, 0.35)):
            rows.append([short_date(month.replace(day=self.rng.randint(2, 27))),
                         "Prescriptions and medical supplies", dollars(amount)])
        return Document("medical_bill", "Patient payment history", [self.rng.choice(fixtures.PHARMACIES)],
                        date(2026, 10, 1).isoformat(), [Page(1, 1, [
                            {"type": "fields", "title": None, "rows": [["Patient", self.written_name(m)]]},
                            {"type": "table", "title": "What you paid, July to September 2026",
                             "columns": ["Date", "Description", "You paid"], "rows": rows, "numeric": [2]},
                        ])], m.id)

    def _housing(self) -> None:
        h = self.h
        rent = h.expenses.rent
        landlord = self.rng.choice(fixtures.LANDLORDS)
        start = date(2026, self.rng.randint(1, 9), 1) if self.rng.random() < 0.6 else date(2025, self.rng.randint(10, 12), 1)
        adults = [m for m in h.members if m.age >= 18]
        tenants = [self.full(m) for m in adults]
        partner = self._plan("partner_moved_out")
        if partner:
            tenants.append(self._former_partner())
        heat = ("Tenant pays electricity and gas, including heating and air conditioning." if h.expenses.heating_cooling
                else "Landlord provides all utilities, including heat and air conditioning. Tenant pays for "
                     "internet and phone only.")
        pages = [
            Page(1, 3, [{"type": "fields", "title": "1. Parties and premises", "rows": [
                ["Landlord", landlord], ["Tenants", ", ".join(tenants)], ["Premises", ", ".join(self.address())],
                ["Term", f"12 months, {long_date(start)} to {long_date(start.replace(year=start.year + 1) - timedelta(days=1))}"],
                ["Occupants", ", ".join(self.full(m) for m in h.members)]]}]),
            Page(2, 3, [{"type": "text", "text": f"2. Rent. Tenant agrees to pay {dollars(rent * 100)} per month, due "
                                                 "on the 1st day of each month. A late fee of $35.00 applies after the "
                                                 "5th."},
                        {"type": "fields", "title": None, "rows": [["Monthly rent", dollars(rent * 100)],
                                                                   ["Security deposit", dollars(rent * 100)]]}]),
            Page(3, 3, [{"type": "text", "text": f"3. Utilities. {heat}"},
                        {"type": "fields", "title": "Signatures", "rows": [["Landlord", landlord]] +
                         [["Tenant", t] for t in tenants]}]),
        ]
        if self._plan("missing_lease_page"):
            pages = [pages[0], pages[2]]
            self.issues.append(Issue(
                "missing_lease_page", None, "Page 2 of the lease, which has the rent, is not in the packet, and the "
                "application leaves rent blank.",
                gap={"fact": "rent", "range": list(noise.RENT_RANGE)}, flag="Page 2 of the lease, showing the rent"))
        self.add(Document("lease", "Residential lease agreement", [landlord], (start - timedelta(days=12)).isoformat(),
                          pages))
        if h.expenses.heating_cooling:
            self.add(self._utility_bill())

    def _utility_bill(self) -> Document:
        head = self.h.head
        return Document("utility_bill", "Statement", [self.rng.choice(fixtures.UTILITIES)],
                        date(2026, 9, 24).isoformat(), [Page(1, 1, [
                            {"type": "fields", "title": None, "rows": [
                                ["Account holder", self.full(head)], ["Service address", ", ".join(self.address())],
                                ["Billing period", "August 20, 2026 to September 19, 2026"]]},
                            {"type": "table", "title": "Charges", "columns": ["Description", "Amount"],
                             "rows": [["Electric service", dollars(self.rng.randint(4500, 13000))],
                                      ["Gas service (heating)", dollars(self.rng.randint(1800, 9000))]],
                             "numeric": [1]},
                        ])])

    def _childcare(self) -> None:
        h = self.h
        amount = h.expenses.childcare
        if not amount:
            return
        if self._plan("missing_childcare_receipt"):
            self.issues.append(Issue(
                "missing_childcare_receipt", None, "The application says the household pays for childcare but gives "
                "no amount, and there is no invoice.",
                gap={"fact": "childcare", "range": list(noise.CHILDCARE_RANGE)},
                flag="Childcare invoice or receipt showing the monthly cost"))
            return
        kids = [m for m in h.members if m.relationship == "child" and m.age < 13]
        shares = split_cents(amount * 100, len(kids), self.rng, 0.2) if kids else [amount * 100]
        rows = [[self.full(k), dollars(s)] for k, s in zip(kids, shares)]
        self.add(Document("childcare_invoice", "Tuition invoice, October 2026", [self.rng.choice(fixtures.CHILDCARE)],
                          date(2026, 9, 25).isoformat(), [Page(1, 1, [
                              {"type": "fields", "title": None, "rows": [["Parent", self.full(h.head)]]},
                              {"type": "table", "title": None, "columns": ["Child", "Monthly tuition"], "rows": rows,
                               "numeric": [1]},
                              {"type": "fields", "title": None, "rows": [["Total due October 1", dollars(amount * 100)]]},
                          ])]))

    def _former_partner(self) -> str:
        if "partner" not in self.stated:
            first = self.rng.choice([n for n in ("Marcus", "Andre", "Kevin", "Grace", "Rosa", "Ivan", "Lena", "Ruth")
                                     if n not in {m.name for m in self.h.members}])
            self.stated["partner"] = f"{first} {self.rng.choice(fixtures.SURNAMES)}"
        return self.stated["partner"]

    def _partner_moved_out(self) -> None:
        partner = self._former_partner()
        job = self._job()
        job["hourly"], job["frequency"] = True, "biweekly"
        job["rate"] = self.rng.randint(1500, 2600)
        start, end, pay = pay_periods("biweekly", 5)[-1]
        gross = round(job["rate"] * self.rng.uniform(60, 80))
        stub = self._pay_stub(self.h.head, job, start, end, pay, gross, ytd_scale=1.0, name=partner)
        stub.about = None
        self.add(stub)
        self.stated["notes"].append(f"{partner} moved out in August 2026 and no longer lives with us.")
        self.issues.append(Issue(
            "partner_moved_out", None, f"The lease and an old pay stub name {partner}, who the application says "
            "moved out in August 2026; they are not part of the household."))

    def _application(self) -> Document:
        h = self.h
        yes = lambda flag: "Yes" if flag else "No"  # noqa: E731
        members = [[self.full(m), str(m.age), RELATIONSHIP_LABELS[m.relationship],
                    "Yes" if m.citizenship == "citizen" else "No (no lawful status, no SSN)",
                    yes(m.pregnant), yes(m.disabled), yes(m.student)] for m in h.members]
        income = self.stated["income"] or [["No one in the household has income", "", "", ""]]
        no_income = [[self.full(m), "No income", "", ""] for m in h.members
                     if m.relationship in ("head", "spouse") and not m.income]
        rent = h.expenses.rent
        mismatch = self._plan("rent_mismatch")
        if self._plan("missing_lease_page"):
            rent_stated = "Not given (see lease)"
        elif mismatch:
            stated = rent + self.rng.choice([-1, 1]) * 5 * self.rng.randint(8, 30)
            rent_stated = whole(max(100, stated))
            self.issues.append(Issue("rent_mismatch", None, f"The application says rent is {rent_stated}; the signed "
                                     f"lease says {whole(rent)}. The lease wins."))
        else:
            rent_stated = whole(rent)
        childcare = h.expenses.childcare
        childcare_stated = ("Yes, amount not given" if self._plan("missing_childcare_receipt")
                            else whole(childcare) if childcare else "None")
        medical = [[self.full(h.member(mid)), f"About {whole(10 * round(v / 10))} a month"]
                   for mid, v in h.expenses.medical.items()]
        blocks = [
            {"type": "fields", "title": "Applicant", "rows": [
                ["Name", self.full(h.head)], ["Home address", ", ".join(self.address())],
                ["Date signed", long_date(APPLICATION_DATE)]]},
            {"type": "table", "title": "Who lives in your home and buys and prepares food with you",
             "columns": ["Name", "Age", "Relationship", "US citizen", "Pregnant", "Disability", "Full-time student"],
             "rows": members, "numeric": [1]},
            {"type": "table", "title": "Income", "columns": ["Who", "Type", "Paid by", "Amount"],
             "rows": income + no_income, "numeric": []},
            {"type": "fields", "title": "Housing and other costs", "rows": [
                ["Rent", rent_stated],
                ["Heating or cooling paid separately from rent", yes(h.expenses.heating_cooling)],
                ["Childcare", childcare_stated]]},
        ]
        if medical:
            blocks.append({"type": "table", "title": "Medical costs (for members 60 or older or with a disability)",
                           "columns": ["Who", "Amount"], "rows": medical, "numeric": [1]})
        blocks.append({"type": "fields", "title": "Savings and other assets",
                       "rows": [["Cash, bank accounts, other assets", "Under $500 in all"]]})
        if self.stated["notes"]:
            blocks.append({"type": "text", "text": "Notes from the applicant: " + " ".join(self.stated["notes"])})
        return Document("application", f"Application for benefits, {self.state}",
                        [f"{self.state} Department of Human Services"], APPLICATION_DATE.isoformat(),
                        [Page(1, 1, blocks)])


# --- reading the facts back ----------------------------------------------------------------------

def _cents(value: str) -> int:
    sign = -1 if value.startswith("-") else 1
    digits = value.lstrip("-$").replace(",", "")
    whole_part, _, frac = digits.partition(".")
    return sign * (int(whole_part) * 100 + int((frac + "00")[:2]))


def established(packet: Packet, household: Household) -> dict:
    """{(member id, source): monthly dollars} and expenses, read from the documents by docgen.rules.

    Used by tests and the build to prove the paperwork says what the household says. Gaps come back as None.
    """
    out: dict = {"income": {}, "rent": None, "childcare": None, "medical": {}}
    stubs: dict[str, list[Document]] = {}
    for doc in packet.documents:
        if doc.kind == "pay_stub" and doc.about:
            stubs.setdefault(doc.about, []).append(doc)
    for member_id, docs in stubs.items():
        docs.sort(key=lambda d: d.date, reverse=True)
        current = docs[:2]
        fields = dict(current[0].pages[0].blocks[0]["rows"])
        frequency = next(k for k, v in FREQUENCY_LABELS.items() if v == fields["Pay frequency"])
        gross = [_cents(dict((r[0], r[-1]) for r in d.pages[0].blocks[1]["rows"])["Gross pay"]) for d in current]
        out["income"][(member_id, "wages")] = rules.monthly_from_pay(gross, frequency)
    for doc in packet.documents:
        blocks = [b for p in doc.pages for b in p.blocks]
        fields = {k: v for b in blocks if b["type"] == "fields" for k, v in b["rows"]}
        if doc.kind == "earnings_ledger":
            nets = [_cents(r[3]) for r in blocks[1]["rows"]]
            out["income"][(doc.about, "self_employment")] = rules.monthly_average(nets)
        elif doc.kind == "benefit_letter" and "Monthly benefit before deductions" in fields:
            out["income"][(doc.about, "social_security")] = _cents(fields["Monthly benefit before deductions"]) // 100
        elif doc.kind == "benefit_letter" and "Monthly SSI payment" in fields:
            out["income"][(doc.about, "ssi")] = _cents(fields["Monthly SSI payment"]) // 100
        elif doc.kind == "benefit_letter" and "Weekly benefit amount" in fields:
            out["income"][(doc.about, "unemployment")] = rules.monthly_from_weekly(_cents(fields["Weekly benefit amount"]))
        elif doc.kind == "payment_history":
            table = next(b for b in blocks if b["type"] == "table")
            by_month: dict[str, int] = {}
            for day, amount in table["rows"]:
                by_month[day[:2]] = by_month.get(day[:2], 0) + _cents(amount)
            out["income"][(doc.about, "child_support")] = rules.monthly_average(list(by_month.values()))
        elif doc.kind == "lease" and "Monthly rent" in fields:
            out["rent"] = _cents(fields["Monthly rent"]) // 100
        elif doc.kind == "childcare_invoice":
            out["childcare"] = _cents(fields["Total due October 1"]) // 100
        elif doc.kind == "medical_bill":
            table = next(b for b in blocks if b["type"] == "table")
            out["medical"][doc.about] = rules.monthly_average([_cents(r[2]) for r in table["rows"]])
    if not household.expenses.childcare and out["childcare"] is None and not any(i.kind == "missing_childcare_receipt"
                                                                                 for i in packet.issues):
        out["childcare"] = 0
    return out


def expected(household: Household, packet: Packet) -> dict:
    """What `established` should return: the household's own figures, with gaps as None."""
    out = {"income": {(m.id, s): v for m in household.members for s, v in m.income.items()},
           "rent": household.expenses.rent, "childcare": household.expenses.childcare,
           "medical": dict(household.expenses.medical)}
    for issue in packet.gaps:
        gap = issue.gap
        if gap["fact"] == "income":
            del out["income"][(gap["member"], gap["source"])]
        else:
            out[gap["fact"]] = None
    return out


__all__ = ["APPLICATION_DATE", "build", "established", "expected", "pay_periods", "round_half_up"]
