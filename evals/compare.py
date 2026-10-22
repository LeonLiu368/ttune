"""Compare a run's ID and OOD results and write comparison.md."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from evals.answer import AMOUNT_KEYS, PROGRAMS
from evals.metrics import bootstrap_change, mean_reward, program_balanced_accuracy, scored, summarize

PROGRAM_NAMES = {"snap": "SNAP", "eitc": "EITC", "medicaid": "Medicaid", "wic": "WIC"}
FAMILY_NAMES = {"rare_shape": "Rare household shapes", "threshold_edge": "Threshold edge cases",
                "held_out_state": "Held-out states"}


def pct(value: float | None) -> str:
    return "–" if value is None else f"{100 * value:.0f}%"


def num(value: float | None) -> str:
    return "–" if value is None else f"{value:.2f}"


def change(a: float | None, b: float | None, points: bool) -> str:
    if a is None or b is None:
        return "–"
    d = b - a
    return f"{100 * d:+.0f} pts" if points else f"{d:+.2f}"


def change_ci(result: tuple[float, float, float] | None, points: bool) -> str:
    if result is None:
        return "–"
    d, low, high = result
    if points:
        return f"{100 * d:+.0f} pts ({100 * low:+.0f} to {100 * high:+.0f})"
    return f"{d:+.2f} ({low:+.2f} to {high:+.2f})"


def load(run_dir: Path, set_: str) -> list[dict]:
    path = run_dir / f"{set_}.jsonl"
    return [json.loads(line) for line in path.open()] if path.is_file() else []


def _group_table(groups: list[tuple[str, list[dict]]]) -> list[str]:
    head = "| Group | n | Mean reward | " + " | ".join(f"{PROGRAM_NAMES[p]} balanced acc." for p in PROGRAMS) + \
           " | False denials | Malformed |"
    lines = [head, "|---|---|---|" + "---|" * len(PROGRAMS) + "---|---|"]
    for label, rows in groups:
        s = summarize(rows)
        if not s["n"]:
            continue
        details = [d for r in scored(rows) for d in r["score"]["programs"].values()]
        denial_rate = sum(d["false_denials"] for d in details) / max(1, sum(d["truly_eligible"] for d in details))
        accuracies = " | ".join(pct(s["programs"][p]["balanced_accuracy"]) for p in PROGRAMS)
        lines.append(f"| {label} | {s['n']} | {num(s['reward'])} | {accuracies} | {pct(denial_rate)} | "
                     f"{pct(s['malformed'])} |")
    return lines


def comparison_markdown(run_dir: Path) -> str:
    summary = json.loads((run_dir / "summary.json").read_text())
    id_rows, ood_rows = load(run_dir, "id"), load(run_dir, "ood")
    sid, sood = summarize(id_rows), summarize(ood_rows)
    sets = summary.get("sets", {})
    pe = {s.get("policyengine_us") for s in sets.values()} - {None}
    cost = sum(s.get("cost_usd") or 0 for s in sets.values())
    lines = [
        f"# Eval: `{summary['model']}`",
        "",
        f"Run `{summary['run_id']}` · prompt v{summary['prompt_version']} (`{summary['prompt_hash']}`) · "
        f"answers from policyengine-us {', '.join(sorted(pe)) or '?'} · cost ${cost:.4f}",
        "",
        "Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 "
        "households per OOD family, small gaps can be noise.",
        "",
        "**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the "
        "OOD set has more eligible households than the ID set. Answering \"no\" to everything already scores "
        "differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible "
        "and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.",
        "",
        "## Overall",
        "",
        "| | ID | OOD | Change |",
        "|---|---|---|---|",
    ]
    if sid["n"] and sood["n"]:
        lines += [
            f"| Households scored | {sid['n']} | {sood['n']} | |",
            f"| Mean reward (0–1) | {num(sid['reward'])} | {num(sood['reward'])} | "
            f"{change_ci(bootstrap_change(id_rows, ood_rows, mean_reward), points=False)} |",
            f"| Eligibility score | {num(sid['eligibility'])} | {num(sood['eligibility'])} | "
            f"{change(sid['eligibility'], sood['eligibility'], False)} |",
            f"| Amount score | {num(sid['amount'])} | {num(sood['amount'])} | {change(sid['amount'], sood['amount'], False)} |",
            f"| Malformed answers | {pct(sid['malformed'])} | {pct(sood['malformed'])} | "
            f"{change(sid['malformed'], sood['malformed'], True)} |",
        ]
    floors = {k: sets.get(k, {}).get("floors", {}) for k in ("id", "ood")}
    for key, label in (("always_no", "Floor: always \"no\""), ("always_yes", "Floor: always \"yes\", $0")):
        lines.append(f"| {label} | {num(floors['id'].get(key))} | {num(floors['ood'].get(key))} | |")
    api_errors = sid.get("api_errors", 0) + sood.get("api_errors", 0)
    if api_errors:
        lines += ["", f"{api_errors} cases got no answer from the API and aren't scored; see the result files."]

    lines += ["", "## By program", "", "| Program | Measure | ID | OOD | Change |", "|---|---|---|---|---|"]
    for p in PROGRAMS:
        if not (sid["n"] and sood["n"]):
            break
        a, b = sid["programs"][p], sood["programs"][p]
        name = PROGRAM_NAMES[p]
        lines.append(f"| {name} | **Balanced accuracy** | {pct(a['balanced_accuracy'])} | {pct(b['balanced_accuracy'])} | "
                     f"{change_ci(bootstrap_change(id_rows, ood_rows, program_balanced_accuracy(p)), points=True)} |")
        lines.append(f"| {name} | Accuracy | {pct(a['accuracy'])} | {pct(b['accuracy'])} | "
                     f"{change(a['accuracy'], b['accuracy'], True)} |")
        lines.append(f"| {name} | False denials (of truly eligible) | {pct(a['false_denial_rate'])} | "
                     f"{pct(b['false_denial_rate'])} | {change(a['false_denial_rate'], b['false_denial_rate'], True)} |")
        lines.append(f"| {name} | False approvals (of truly ineligible) | {pct(a['false_approval_rate'])} | "
                     f"{pct(b['false_approval_rate'])} | {change(a['false_approval_rate'], b['false_approval_rate'], True)} |")
        if p in AMOUNT_KEYS:
            lines.append(f"| {name} | Amount within ±5% or ±$10 (of truly eligible) | "
                         f"{pct(a['amount_within_tolerance'])} | {pct(b['amount_within_tolerance'])} | "
                         f"{change(a['amount_within_tolerance'], b['amount_within_tolerance'], True)} |")
    lines.append("")
    lines.append("Medicaid and WIC accuracy count one decision per household member.")

    families = defaultdict(list)
    twists = defaultdict(list)
    for r in ood_rows:
        families[r["shift"]].append(r)
        for t in r["twists"]:
            twists[t].append(r)
    groups = [("ID (reference)", id_rows)] + [(FAMILY_NAMES.get(f, f), families[f]) for f in FAMILY_NAMES if f in families]
    lines += ["", "## OOD by shift family", "", *_group_table(groups)]
    lines += ["", "## OOD by twist", "", "Rare-shape households have one or two twists, so a household can appear in two rows.",
              "", *_group_table([("ID (reference)", id_rows)] + sorted(twists.items()))]
    return "\n".join(lines) + "\n"


def compare(run_dir: Path) -> Path:
    out = run_dir / "comparison.md"
    out.write_text(comparison_markdown(run_dir))
    return out
