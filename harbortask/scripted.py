"""Scripted demonstrations for the SFT warm-start, at $0: the work a careful caseworker does, written out as
terminus-2 conversations.

For each training case, the demonstration reads every document with `pdftotext`, works out the facts by the stated
rules, writes `household.json`, runs `benefits-calc`, decides which answers a missing document could change, and
writes `/app/answer.json`. Nothing in it comes from outside the agent's view:

- every terminal output is real: `pdftotext` on the task's own PDFs, and PolicyEngine on the facts as written;
- the facts are what docgen's `established()` reads off the documents, so a missing document stays missing (left
  out of the calculation and flagged), never filled in from the hidden household.

Each demonstration is checked before it's kept. The answer must score 1.0 with the task's own verifier, and the
calculator output shown must agree with every answer the documents settle. A case that fails either check is
dropped and counted.

The prompt and the observation wording copy Harbor 0.25.0's terminus-2 (templates/terminus/, Apache-2.0), so the
student is trained on the same conversation shape it sees at evaluation.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import tempfile
from collections import Counter
from fractions import Fraction
from pathlib import Path

from docgen import rules
from docgen.documents import FREQUENCY_LABELS, _cents, established
from docgen.model import Document, Packet
from envgen.household import Household
from harbortask import build, calc, verify

TEMPLATE = Path(__file__).resolve().parent / "templates" / "terminus" / "terminus-json-plain.txt"
WIDTH = 160  # terminus-2's tmux pane
OUTPUT_LIMIT = 10_000  # terminus-2 cuts longer observations
BATCH_LIMIT = 8_000  # documents read per turn, so an observation stays under the cut
CONFIRM = ("Are you sure you want to mark the task as complete? This will trigger your solution to be graded and "
           "you won't be able to make any further corrections. If so, include \"task_complete\": true in your JSON "
           "response again.")
RELATIONSHIP = {"head": "the applicant", "spouse": "spouse", "child": "child", "parent": "parent"}
PROGRAM_NAMES = {"snap": "SNAP", "eitc": "the EITC", "medicaid": "Medicaid", "wic": "WIC"}
GAP_DEPENDS = {"income": "income", "rent": "rent", "childcare": "childcare costs"}


class ScriptError(Exception):
    pass


def dollars(cents: int | Fraction) -> str:
    return f"${float(cents) / 100:,.2f}"


def whole(amount: int | float) -> str:
    return f"${round(amount):,}"


def day(iso: str) -> str:
    from datetime import date

    d = date.fromisoformat(iso)
    return f"{d:%B} {d.day}"


def lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


COUNTS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def first(name: str) -> str:
    return name.split()[0]


# --- the terminal --------------------------------------------------------------------------------------------------

def pdf_text(doc: Document) -> str:
    from docgen import render_pdf

    with tempfile.NamedTemporaryFile(suffix=".pdf") as fh:
        fh.write(render_pdf.render(doc))
        fh.flush()
        out = subprocess.run(["pdftotext", "-layout", fh.name, "-"], capture_output=True, text=True, check=True)
    return out.stdout.replace("\f", "")


def wrap(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        while len(line) > WIDTH:
            lines.append(line[:WIDTH])
            line = line[WIDTH:]
        lines.append(line)
    return "\n".join(lines)


class Terminal:
    """What the agent's tmux pane shows: each command after the prompt, then its output."""

    def __init__(self, host: str):
        self.prompt = f"caseworker@{host}:/app$ "

    def screen(self) -> str:
        return "Current Terminal Screen:\n" + self.prompt.rstrip()

    def run(self, steps: list[tuple[str, str]]) -> str:
        """[(keystrokes, output)] -> the new terminal output after running them."""
        parts = []
        for keys, output in steps:
            typed = keys.rstrip("\n").split("\n")
            parts.append(self.prompt + typed[0])
            parts += ["> " + line for line in typed[1:]]
            if output:
                parts.append(output.rstrip("\n"))
        parts.append(self.prompt.rstrip())
        text = wrap("\n".join(parts))
        if len(text.encode()) > OUTPUT_LIMIT:
            raise ScriptError("an observation would be cut")
        return "New Terminal Output:\n" + text


def reply(analysis: str, plan: str, commands: list[str], complete: bool = False) -> str:
    body = {"analysis": analysis, "plan": plan,
            "commands": [{"keystrokes": c, "duration": 1.0 if c.startswith("benefits-calc") else 0.1}
                         for c in commands]}
    if complete:
        body["task_complete"] = True
    return json.dumps(body, indent=2)


def heredoc(path: str, content: str) -> str:
    return f"cat > {path} << 'EOF'\n{content}\nEOF\n"


# --- reading the documents -----------------------------------------------------------------------------------------

def _fields(doc: Document) -> dict:
    return {k: v for p in doc.pages for b in p.blocks if b["type"] == "fields" for k, v in b["rows"]}


def _tables(doc: Document) -> list[dict]:
    return [b for p in doc.pages for b in p.blocks if b["type"] == "table"]


def reading_notes(household: Household, packet: Packet) -> list[str]:
    """How each fact follows from the documents, by the stated rules: the working a caseworker writes down."""
    names = {m.id: first(m.name) for m in household.members}
    notes: list[str] = []
    stubs: dict[str, list[Document]] = {}
    for doc in packet.documents:
        if doc.kind == "pay_stub" and doc.about:
            stubs.setdefault(doc.about, []).append(doc)
    for member_id, docs in stubs.items():
        if member_id not in names:
            continue  # someone who no longer lives here (an old stub)
        docs.sort(key=lambda d: d.date, reverse=True)
        current = docs[:2]
        frequency = next(k for k, v in FREQUENCY_LABELS.items() if v == _fields(current[0])["Pay frequency"])
        gross = [_cents(dict((r[0], r[-1]) for r in d.pages[0].blocks[1]["rows"])["Gross pay"]) for d in current]
        average = Fraction(sum(gross), len(gross))
        factor = rules.FREQUENCIES[frequency]
        notes.append(f"Wages, {names[member_id]}: the two most recent pay stubs ({day(current[0].date)} and "
                     f"{day(current[1].date)}) show gross pay of {dollars(gross[0])} and {dollars(gross[1])}, paid "
                     f"{FREQUENCY_LABELS[frequency].lower()}. Average {dollars(average)} x {float(factor):g} = "
                     f"{whole(rules.monthly_from_pay(gross, frequency))} a month."
                     + (f" An older stub ({day(docs[2].date)}) doesn't count." if len(docs) > 2 else ""))
    for doc in packet.documents:
        f, who = _fields(doc), names.get(doc.about or "", "")
        if doc.kind == "earnings_ledger":
            nets = [_cents(r[3]) for r in _tables(doc)[0]["rows"]]
            notes.append(f"Self-employment, {who}: net earnings of {', '.join(dollars(n) for n in nets)} over the last "
                         f"three months average {whole(rules.monthly_average(nets))} a month.")
        elif doc.kind == "benefit_letter" and "Monthly benefit before deductions" in f:
            notes.append(f"Social Security, {who}: {f['Monthly benefit before deductions']} a month before deductions.")
        elif doc.kind == "benefit_letter" and "Monthly SSI payment" in f:
            notes.append(f"SSI, {who}: {f['Monthly SSI payment']} a month.")
        elif doc.kind == "benefit_letter" and "Weekly benefit amount" in f:
            weekly = _cents(f["Weekly benefit amount"])
            notes.append(f"Unemployment, {who}: {dollars(weekly)} a week x 4.3 = "
                         f"{whole(rules.monthly_from_weekly(weekly))} a month.")
        elif doc.kind == "payment_history":
            by_month: dict[str, int] = {}
            for when, amount in _tables(doc)[0]["rows"]:
                by_month[when[:2]] = by_month.get(when[:2], 0) + _cents(amount)
            months = list(by_month.values())
            notes.append(f"Child support, {who}: {', '.join(dollars(m) for m in months)} received in the last three "
                         f"months, an average of {whole(rules.monthly_average(months))} a month.")
        elif doc.kind == "lease" and "Monthly rent" in f:
            notes.append(f"Rent: the lease says {f['Monthly rent']} a month.")
        elif doc.kind == "utility_bill":
            notes.append("A utility bill shows heating or cooling is paid separately from rent.")
        elif doc.kind == "childcare_invoice":
            notes.append(f"Childcare: the invoice totals {f['Total due October 1']} a month.")
        elif doc.kind == "medical_bill":
            paid = [_cents(r[2]) for r in _tables(doc)[0]["rows"]]
            notes.append(f"Medical costs, {who}: {', '.join(dollars(p) for p in paid)} paid over three months, an "
                         f"average of {whole(rules.monthly_average(paid))} a month.")
    if not any(d.kind == "utility_bill" for d in packet.documents):
        notes.append("There's no utility bill, so heating and cooling aren't paid separately from rent.")
    for issue in packet.issues:
        notes.append(issue.detail + (" That document is missing, so I'll leave this out of the calculation and check "
                                     "which answers it could change." if issue.gap else ""))
    return notes


def facts(household: Household, packet: Packet) -> dict:
    """The calculator's input, from what the documents establish: a missing figure is left out."""
    seen = established(packet, household)
    names = {m.id: first(m.name) for m in household.members}
    members = []
    for m in household.members:
        member = {"name": names[m.id], "age": m.age, "relationship": m.relationship}
        for flag in ("pregnant", "disabled", "student"):
            if getattr(m, flag):
                member[flag] = True
        if m.citizenship != "citizen":
            member["citizenship"] = m.citizenship
        income = {source: amount for (mid, source), amount in seen["income"].items() if mid == m.id and amount}
        if income:
            member["income"] = income
        members.append(member)
    return {"state": household.state, "area": household.area, "members": members,
            "expenses": {"rent": seen["rent"] or 0, "heating_cooling": household.expenses.heating_cooling,
                         "childcare": seen["childcare"] or 0,
                         "medical": {names[k]: v for k, v in seen["medical"].items() if v and k in names}}}


# --- the answer and its checks -------------------------------------------------------------------------------------

def answer(row: dict, truth: dict) -> dict:
    """The reference answer, with members by first name as the instruction asks, and a plain explanation."""
    out = verify.oracle(truth)
    for program in ("medicaid", "wic"):
        for key in ("eligible_members", "unknown_members"):
            out[program][key] = [first(n) for n in out[program].get(key, [])]
    for item in out["missing_information"]:
        if item["member"]:
            item["member"] = first(item["member"])
    out["explanation"] = explanation(out)
    return out


def explanation(ans: dict) -> str:
    said = []
    for program, key in (("snap", "monthly_benefit"), ("eitc", "annual_amount")):
        e = ans[program]["eligible"]
        name = PROGRAM_NAMES[program]
        if e == "unknown":
            said.append(f"we can't decide {name} until the missing paperwork comes in")
        elif e:
            per = "a month" if program == "snap" else "for the year"
            said.append(f"you qualify for {name}, about {whole(ans[program][key])} {per}")
        else:
            said.append(f"you don't qualify for {name}")
    for program in ("medicaid", "wic"):
        who, unknown = ans[program]["eligible_members"], ans[program]["unknown_members"]
        name = PROGRAM_NAMES[program]
        if who:
            said.append(f"{', '.join(who)} {'qualifies' if len(who) == 1 else 'qualify'} for {name}")
        elif not unknown:
            said.append(f"no one qualifies for {name}")
        if unknown:
            said.append(f"{name} for {', '.join(unknown)} depends on the missing paperwork")
    text = "Based on your documents, " + "; ".join(said) + "."
    if ans["missing_information"]:
        text += " Please bring the missing documents so we can finish."
    return text[0].upper() + text[1:]


def agrees(result: dict, truth: dict, names: dict[str, str]) -> list[str]:
    """Where the calculator output contradicts an answer the documents settle (should be nothing)."""
    t = truth["truth"]
    bad = []
    for program, key in (("snap", "monthly_benefit"), ("eitc", "annual_amount")):
        if t[program]["eligible"] == "unknown":
            continue
        if bool(result[program]["eligible"]) != bool(t[program]["eligible"]):
            bad.append(f"{program} eligibility")
        elif t[program][key] is not None and abs(result[program][key] - t[program][key]) > 0.5:
            bad.append(f"{program} amount")
    for program in ("medicaid", "wic"):
        got = {first(n) for n in result[program]["eligible_members"]}
        sure = {first(names[i]) for i in t[program]["eligible_members"]}
        maybe = {first(names[i]) for i in t[program].get("unknown_members", [])}
        if not sure <= got or not got <= sure | maybe:
            bad.append(f"{program} members")
    return bad


def unknown_notes(row: dict, truth: dict, packet: Packet) -> list[str]:
    t, names = truth["truth"], truth["names"]
    open_ = [PROGRAM_NAMES[p] for p in ("snap", "eitc") if t[p]["eligible"] == "unknown"]
    open_ += [f"{PROGRAM_NAMES[p]} for {', '.join(first(names[i]) for i in t[p]['unknown_members'])}"
              for p in ("medicaid", "wic") if t[p].get("unknown_members")]
    notes = []
    for issue in packet.gaps:
        what = GAP_DEPENDS[issue.gap["fact"]]
        if open_:
            notes.append(f"Without {lower_first(issue.flag)}, I can't pin down the {what}. Trying the plausible range, "
                         f"{' and '.join(open_)} could change, so {'that is' if len(open_) == 1 else 'those are'} "
                         "unknown. The other answers come out the same either way.")
        else:
            notes.append(f"Without {lower_first(issue.flag)}, the {what} isn't known, but no answer changes across the "
                         "plausible range, so every answer stands. It still goes on the missing-information list.")
    return notes


def summarize(result: dict) -> str:
    s, e = result["snap"], result["eitc"]
    parts = [f"SNAP {'eligible, ' + whole(s['monthly_benefit']) + ' a month' if s['eligible'] else 'not eligible'}",
             f"EITC {'eligible, ' + whole(e['annual_amount']) + ' for the year' if e['eligible'] else 'not eligible'}"]
    for program in ("medicaid", "wic"):
        who = result[program]["eligible_members"]
        parts.append(f"{PROGRAM_NAMES[program]}: {', '.join(first(n) for n in who) if who else 'no one'}")
    return "; ".join(parts)


# --- one demonstration ---------------------------------------------------------------------------------------------

def demonstration(row: dict, result: dict, texts: dict[str, str] | None = None) -> dict:
    """{"task", "messages"} for one case, given the calculator's output on `facts(...)`. Raises ScriptError."""
    household = Household.from_dict(row["household"])
    packet = Packet.from_dict(row["packet"])
    truth = build.truth_file(row)
    tid = build.task_id(row["id"])
    bad = agrees(result, truth, truth["names"])
    if bad:
        raise ScriptError(f"calculator disagrees with the settled answers: {', '.join(bad)}")
    ans = answer(row, truth)
    if verify.evaluate(json.dumps(ans), truth)["reward"] != 1.0:
        raise ScriptError("the answer doesn't score 1.0")

    rng = random.Random(f"scripted:{tid}")
    term = Terminal(hashlib.sha256(tid.encode()).hexdigest()[:12])
    texts = texts or {d.name: pdf_text(d) for d in packet.documents}
    docs = [d.name for d in packet.documents]
    ls = "  ".join(f"{d}.pdf" for d in docs)
    instruction = build.instruction(row)
    messages = [{"role": "user", "content": TEMPLATE.read_text().format(instruction=instruction,
                                                                       terminal_state=term.screen())}]

    def step(analysis: str, plan: str, commands: list[tuple[str, str]], complete: bool = False) -> None:
        messages.append({"role": "assistant", "content": reply(analysis, plan, [c for c, _ in commands], complete)})
        out = term.run(commands)
        messages.append({"role": "user", "content": (f"Current terminal state:\n{out}\n\n{CONFIRM}" if complete
                                                     else out)})

    # 1. The folder and the application.
    app = f"pdftotext -layout /app/case/{docs[0]}.pdf -\n"
    step(rng.choice(["I'm in /app with nothing read yet. The household's paperwork is in /app/case/.",
                     "The terminal is at /app and nothing has been done yet. The case documents are in /app/case/."]),
         "List the case folder, then read the application in full to see who lives in the home and what they "
         "report for income and costs.",
         [("ls /app/case/\n", ls), (app, texts[docs[0]])])

    # 2. Every other document, in full.
    people = "; ".join(f"{first(m.name)}, {m.age} ({RELATIONSHIP[m.relationship]})" for m in household.members)
    rest, batches, size = docs[1:], [], 0
    for name in rest:
        if not batches or size + len(texts[name]) > BATCH_LIMIT:
            batches.append([])
            size = 0
        batches[-1].append(name)
        size += len(texts[name])
    for i, batch in enumerate(batches):
        if i == 0:
            analysis = (f"The application lists {COUNTS.get(len(household.members), len(household.members))} "
                        f"{'person' if len(household.members) == 1 else 'people'} in the household: {people}. "
                        "Its income and cost figures are what they report, but the amounts have to come from the "
                        "documents.")
        else:
            analysis = "Read those documents. There are more to go before working out the facts."
        step(analysis, f"Read {'the remaining' if i else 'every other'} document in full: "
             + ", ".join(f"{n}.pdf" for n in batch) + ".",
             [(f"pdftotext -layout /app/case/{n}.pdf -\n", texts[n]) for n in batch])

    # 3. The facts, the household file and the calculator.
    fact_json = json.dumps(facts(household, packet), indent=2)
    result_json = json.dumps(result, indent=2)
    step("I've read every document. Working out the facts by the rules:\n- " + "\n- ".join(reading_notes(household, packet)),
         "Write these facts to /app/household.json in the calculator's format and run benefits-calc on it.",
         [(heredoc("/app/household.json", fact_json), ""), ("benefits-calc /app/household.json\n", result_json)])

    # 4. What could change, and the answer.
    notes = unknown_notes(row, truth, packet)
    missing = ans["missing_information"]
    analysis = (f"The calculator says: {summarize(result)}. "
                + (" ".join(notes) + " " if notes else "Nothing the rules need is missing, so every answer stands. ")
                + (f"Missing information: {', '.join(i['document'] + (' for ' + i['member'] if i['member'] else '') for i in missing)}."
                   if missing else "No documents are missing."))
    step(analysis, "Write /app/answer.json with these answers and check that it parses.",
         [(heredoc("/app/answer.json", json.dumps(ans, indent=2)), ""),
          ("jq -e . /app/answer.json > /dev/null && echo valid\n", "valid")], complete=True)

    # 5. Confirm.
    messages.append({"role": "assistant", "content": reply(
        "/app/answer.json is written and valid, with every program, the missing information and an explanation.",
        "The task is complete.", [], complete=True)})
    return {"task": tid, "messages": messages}


def build_all(rows: list[dict], out: Path, data: dict | None = None) -> dict:
    """Write one demonstration per case that passes its checks. Returns counts (aggregate only)."""
    from envgen import truth as pe

    data = data or build._calc_data()
    inputs = []
    for i, row in enumerate(rows):
        h = calc.to_household(facts(Household.from_dict(row["household"]), Packet.from_dict(row["packet"])), data)
        h.id = f"calc-{i}"
        inputs.append(h)
    results = []
    for start in range(0, len(inputs), 200):
        results += pe.compute(inputs[start:start + 200])
    counts: Counter = Counter()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for row, h, result in zip(rows, inputs, results):
            names = {m.id: m.name for m in h.members}
            for program in ("medicaid", "wic", "chip"):
                result[program]["eligible_members"] = [names[i] for i in result[program]["eligible_members"]]
            try:
                demo = demonstration(row, result)
            except ScriptError as exc:
                counts[f"dropped: {exc}"] += 1
                continue
            fh.write(json.dumps(demo) + "\n")
            counts["kept"] += 1
            counts["with a gap"] += bool(row["packet"]["issues"]) and any(i.get("gap") for i in row["packet"]["issues"])
            counts["turns"] += sum(m["role"] == "assistant" for m in demo["messages"])
    return dict(counts)


def generated_cases(split: str, n_cases: int, secret: str) -> list[dict]:
    from harbortask.split import generated_rows

    return generated_rows(split, n_cases, secret)


def summary(counts: dict[str, dict]) -> str:
    """Aggregate numbers only, safe to publish."""
    lines = ["# Scripted demonstrations", "",
             "Terminus-2 conversations written by `python -m harbortask scripted` from the secret training split. "
             "No model and no API: $0. Each kept demonstration's answer scores 1.0 with the task verifier, and its "
             "calculator output agrees with every answer the documents settle.", "",
             "| Split | Cases | Kept | With a missing document | Dropped | Assistant turns per demonstration |",
             "|---|---|---|---|---|---|"]
    for split, c in counts.items():
        kept = c.get("kept", 0)
        dropped = sum(v for k, v in c.items() if k.startswith("dropped"))
        lines.append(f"| {split} | {kept + dropped} | {kept} | {c.get('with a gap', 0)} | {dropped} | "
                     f"{c.get('turns', 0) / kept:.1f} |" if kept else f"| {split} | {dropped} | 0 | 0 | {dropped} | – |")
    reasons = Counter()
    for c in counts.values():
        reasons.update({k: v for k, v in c.items() if k.startswith("dropped")})
    if reasons:
        lines += ["", "Dropped: " + "; ".join(f"{k.removeprefix('dropped: ')} ({v})" for k, v in reasons.items())]
    return "\n".join(lines) + "\n"
