"""Write a Harbor task directory for one document case. Deterministic: the same case gives the same files."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from string import Template

from docgen.model import Packet
from docgen.rules import RULES
from envgen.describe import STATE_NAMES
from harbortask import verify

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).resolve().parent / "templates"
POLICYENGINE_US = "2.50.1"  # pinned in requirements-envgen.txt; the answers were computed with it
REWARDKIT = "0.2.3"


def task_id(case_id: str) -> str:
    """Opaque, so the task doesn't name the case (whose answers are public in this repo)."""
    return "benefits-" + hashlib.sha256(f"ttune-task:{case_id}".encode()).hexdigest()[:10]


def truth_file(row: dict) -> dict:
    names = {m["id"]: m["name"] for m in row["household"]["members"]}
    return {"truth": row["truth"], "names": names,
            "missing_information": verify.missing_items(row["packet"]["issues"], names)}


def difficulty(row: dict) -> str:
    issues = row["packet"]["issues"]
    if any(i["gap"] for i in issues) or row["household"]["shift"] == "threshold_edge":
        return "hard"
    return "medium" if issues or row["household"]["shift"] != "none" else "easy"


def _fill(name: str, **values) -> str:
    return Template((TEMPLATES / name).read_text()).substitute(**values)


def _write(path: Path, text: str | bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text) if isinstance(text, bytes) else path.write_text(text)
    if mode:
        path.chmod(mode)


def _calc_data() -> dict:
    from envgen.sample import COUNTIES
    from scraper.parsers.regions import STATE_CODES

    return {"states": dict(sorted(STATE_CODES.items())),
            "counties": {state: [list(c) for c in counties] for state, counties in sorted(COUNTIES.items())}}


def instruction(row: dict) -> str:
    rules = RULES.splitlines()
    section = "## " + rules[0].rstrip(":") + "\n\n" + "\n".join(rules[1:])
    state = STATE_NAMES[row["household"]["state"]]
    return _fill("instruction.md", state=state, n_documents=len(row["packet"]["documents"]), rules=section,
                 categories=", ".join(f"`{c}`" for c in verify.CATEGORIES))


def solve_sh(truth: dict) -> str:
    answer = json.dumps(verify.oracle(truth), indent=2, sort_keys=True)
    return ("#!/bin/bash\n# The reference answer, for Harbor's Oracle agent. It never enters the agent's image.\n"
            f"cat > /app/answer.json <<'EOF'\n{answer}\nEOF\n")


def readme(tid: str, row: dict, truth: dict, audit: dict | None) -> str:
    h, packet = row["household"], row["packet"]
    issues = [i["kind"] for i in packet["issues"]] or ["none"]
    lines = [
        f"# {tid}", "",
        f"Screen one household for SNAP, EITC, Medicaid and WIC from its paperwork: an application and "
        f"{len(packet['documents']) - 1} documents as PDFs in `/app/case/`. The agent writes `/app/answer.json` "
        "([instruction.md](instruction.md)).", "",
        f"- **Built from:** `{row['id']}` in `data/documents/{h['set']}/cases.jsonl` by `python -m harbortask build`. "
        "Don't edit by hand.",
        f"- **Household:** {len(h['members'])} people in {STATE_NAMES[h['state']]}; shift `{h['shift']}`"
        + (f", twists {', '.join(h['twists'])}" if h["twists"] else "") + f"; injected issues: {', '.join(issues)}.",
        f"- **Missing information a perfect answer lists:** {len(truth['missing_information'])}.",
        "", "## Environment", "",
        f"- **Agent image:** `python:3.12-slim` with `poppler-utils` (for `pdftotext`), `jq` and `policyengine-us=={POLICYENGINE_US}`.",
        "- **Calculator:** `benefits-calc` turns the household's facts into PolicyEngine's answers. It runs the code that "
        "wrote the answer key, so correct facts give the right answer.",
        "- **No network.** The image holds only the PDFs and the calculator; the answer key and grading code are in the "
        "verifier's separate image.",
        "", "## Verifier", "",
        f"A separate container (`tests/Dockerfile`, harbor-rewardkit {REWARDKIT}, offline) scores `/app/answer.json`, "
        "which Harbor copies over as an artifact. The scoring lives in `/opt/ttune/verify.py`, a copy of ttune's "
        "`harbortask/verify.py` and `evals/score.py`.",
        "",
        "| Dimension | What it measures | Weight |",
        "|---|---|---|",
        "| `eligibility` | Each program's yes/no (per member for Medicaid and WIC). A wrong \"not eligible\" costs double; "
        "\"unknown\" is right only where a missing document leaves the answer open | "
        f"{verify.WEIGHTS['eligibility']} |",
        "| `amount` | SNAP and EITC amounts when truly eligible: full credit within 5% or $10, none at 25% off. With no "
        f"amount to score, it equals eligibility | {verify.WEIGHTS['amount']} |",
        "| `missing_info` | Share of truly missing documents listed, minus 0.25 per wrong item | "
        f"{verify.WEIGHTS['missing_info']} |",
        "| `reward` | Weighted mean | |",
        "",
        "A missing or unreadable answer scores 0 on every dimension.",
        "", "## Layout", "", "```",
        f"{tid}/",
        "├── task.toml            # config; [metadata] records the source case and policyengine-us version",
        "├── instruction.md       # what the agent reads",
        "├── environment/         # agent image: Dockerfile, calc/ (benefits-calc), case/ (the PDFs)",
        "├── tests/               # verifier image: Dockerfile, test.sh, criteria/<dimension>/, support/, truth.json",
        "└── solution/solve.sh    # the reference answer, for the Oracle",
        "```",
        "", "## Running", "", "```bash",
        f"harbor run -p tasks/{tid} -a oracle -e docker        # should score reward 1.0",
        f"harbor run -p tasks/{tid} -a terminus-2 -m <model>   # a real agent",
        "```",
    ]
    if audit:
        lines += ["", f"## Reward-hack audit ({audit['date']})", "",
                  "Run over all 400 document cases with `python -m harbortask audit`; the full report is in "
                  "[tasks/README.md](../README.md#reward-hack-audit).", "",
                  "| Check | Result | Notes |", "|---|---|---|"]
        lines += [f"| {c['check']} | {c['result']} | {c['notes']} |" for c in audit["checks"]]
    return "\n".join(lines) + "\n"


def build(row: dict, out_dir: Path, audit: dict | None = None) -> Path:
    from docgen import render_pdf

    tid = task_id(row["id"])
    task = out_dir / tid
    if task.exists():
        shutil.rmtree(task)
    truth = truth_file(row)
    h = row["household"]
    tags = [h["set"], h["shift"], *h["twists"], *sorted({i["kind"] for i in row["packet"]["issues"]})]
    _write(task / "task.toml", _fill("task.toml", task_id=tid, difficulty=difficulty(row),
                                     tags=", ".join(json.dumps(t) for t in tags), case_id=row["id"],
                                     households=f"data/documents/{h['set']}/cases.jsonl",
                                     policyengine_us=POLICYENGINE_US))
    _write(task / "instruction.md", instruction(row))

    env = task / "environment"
    _write(env / "Dockerfile", _fill("environment.Dockerfile", policyengine_us=POLICYENGINE_US))
    _write(env / "calc" / "calc.py", (Path(__file__).parent / "calc.py").read_text())
    _write(env / "calc" / "envgen" / "__init__.py", '"""Household schema and PolicyEngine answers, from ttune."""\n')
    for name in ("household.py", "truth.py"):
        _write(env / "calc" / "envgen" / name, (ROOT / "envgen" / name).read_text())
    _write(env / "calc" / "data.json", json.dumps(_calc_data(), indent=1, sort_keys=True) + "\n")
    for doc in Packet.from_dict(row["packet"]).documents:
        _write(env / "case" / f"{doc.name}.pdf", render_pdf.render(doc))

    tests = task / "tests"
    _write(tests / "Dockerfile", _fill("tests.Dockerfile", rewardkit=REWARDKIT))
    _write(tests / "test.sh", (TEMPLATES / "test.sh").read_text(), 0o755)
    for dimension in verify.WEIGHTS:  # one folder per dimension, so each is its own key in reward.json
        _write(tests / "criteria" / dimension / "check.py", (TEMPLATES / "criteria" / dimension / "check.py").read_text())
    _write(tests / "criteria" / "reward.toml", _fill("criteria/reward.toml", **{
        f"w_{k}": v for k, v in verify.WEIGHTS.items()}))
    support = tests / "support"
    _write(support / "evals" / "__init__.py", '"""ttune\'s answer parser and scorer."""\n')
    for name in ("answer.py", "score.py"):
        _write(support / "evals" / name, (ROOT / "evals" / name).read_text())
    _write(support / "verify.py", (Path(__file__).parent / "verify.py").read_text())
    _write(support / "task_score.py", (TEMPLATES / "task_score.py").read_text())
    _write(tests / "truth.json", json.dumps(truth, indent=1, sort_keys=True) + "\n")

    _write(task / "solution" / "solve.sh", solve_sh(truth), 0o755)
    _write(task / "README.md", readme(tid, row, truth, audit))
    return task


def pick_samples(rows: list[dict]) -> list[dict]:
    """A handful of tasks covering the shapes that matter: clean, a distractor, each gap kind, and OOD shifts."""
    def first(pred):
        return next(r for r in rows if pred(r))

    kinds = lambda r: {i["kind"] for i in r["packet"]["issues"]}  # noqa: E731
    chosen = [
        first(lambda r: r["household"]["set"] == "id" and not kinds(r)),
        first(lambda r: r["household"]["set"] == "id" and kinds(r) == {"partner_moved_out"}),
        first(lambda r: "missing_income_doc" in kinds(r) and r["household"]["set"] == "id"),
        first(lambda r: "missing_lease_page" in kinds(r)),
        first(lambda r: "missing_childcare_receipt" in kinds(r)),
        first(lambda r: r["household"]["shift"] == "rare_shape" and "stale_stub" in kinds(r)),
    ]
    assert len({r["id"] for r in chosen}) == len(chosen)
    return chosen
