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


def paired_change(a: list[dict], b: list[dict], stat, n_boot: int = 2000, seed: int = 0):
    """stat(b) - stat(a) over the households scored in both runs, with a 95% bootstrap interval over households."""
    import random

    left, right = {r["id"]: r for r in scored(a)}, {r["id"]: r for r in scored(b)}
    ids = sorted(set(left) & set(right))
    if not ids:
        return None, 0, (None, None)

    def diff(sample):
        x, y = stat([left[i] for i in sample]), stat([right[i] for i in sample])
        return None if x is None or y is None else y - x

    base = stat([left[i] for i in ids]), stat([right[i] for i in ids])
    d = diff(ids)
    if d is None:
        return None, len(ids), base
    rng = random.Random(seed)
    boots = sorted(v for v in (diff([rng.choice(ids) for _ in ids]) for _ in range(n_boot)) if v is not None)
    return (d, boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]), len(ids), base


def _agent_section(sets: dict, id_rows: list[dict], ood_rows: list[dict], compare_to: str | None,
                   results_dir: Path) -> list[str]:
    agent = {k: sets.get(k, {}).get("agent", {}) for k in ("id", "ood")}

    def row(label: str, key: str, fmt=num) -> str:
        return f"| {label} | {fmt(agent['id'].get(key))} | {fmt(agent['ood'].get(key))} |"

    count = lambda v: "–" if v is None else str(v)  # noqa: E731
    lines = ["", "## The agent", "",
             "The task's own reward adds the missing-information list (weights 0.60 eligibility, 0.25 amount, 0.15 "
             "missing information), as the task verifier scores it. The mean reward above uses the evals scorer, so "
             "it compares directly with one-shot runs.", "",
             "| | ID | OOD |", "|---|---|---|",
             row("Task reward, with missing information (0–1)", "task_reward"),
             row("Missing-information score", "task_missing_info"),
             row("Timed out", "agent_timeouts", count),
             row("Wrote no answer file", "no_answer", count),
             row("Errors before the verifier (not scored)", "errors", count),
             row("Not run (shard out of time; not scored)", "not_run", count),
             row("Median turns", "median_turns", count),
             row("Median minutes per task", "median_minutes", count)]
    mismatched = agent["id"].get("harbor_reward_mismatches", []) + agent["ood"].get("harbor_reward_mismatches", [])
    lines += ["", "Harbor's verifier and the stored answer agree on every task's reward." if not mismatched else
              f"**Harbor's verifier disagrees with the stored answer on {len(mismatched)} tasks** "
              f"({', '.join(mismatched[:5])}): check the verifier image."]
    other = results_dir / compare_to if compare_to else None
    if other and (other / "summary.json").is_file():
        lines += ["", f"## Against the one-shot run `{compare_to}`", "",
                  "The same households: there the model read the documents as text in one prompt and answered in one reply. "
                  "Changes are agent minus one-shot, with 95% bootstrap intervals over households.", "",
                  "| | ID | OOD |", "|---|---|---|"]
        pairs = {s: (load(other, s), rows) for s, rows in (("id", id_rows), ("ood", ood_rows))}
        cells = {s: paired_change(*pairs[s], mean_reward) for s in pairs}
        lines.append("| Households in both | " + " | ".join(str(cells[s][1]) for s in ("id", "ood")) + " |")
        lines.append("| Mean reward | " + " | ".join(
            f"{num(cells[s][2][0])} → {num(cells[s][2][1])}: {change_ci(cells[s][0], points=False)}"
            for s in ("id", "ood")) + " |")
        for p in PROGRAMS:
            stat = program_balanced_accuracy(p)
            cell = {s: paired_change(*pairs[s], stat) for s in pairs}
            lines.append(f"| {PROGRAM_NAMES[p]} balanced accuracy | " + " | ".join(
                f"{pct(cell[s][2][0])} → {pct(cell[s][2][1])}: {change_ci(cell[s][0], points=True)}"
                for s in ("id", "ood")) + " |")
    return lines


def comparison_markdown(run_dir: Path) -> str:
    summary = json.loads((run_dir / "summary.json").read_text())
    id_rows, ood_rows = load(run_dir, "id"), load(run_dir, "ood")
    sid, sood = summarize(id_rows), summarize(ood_rows)
    sets = summary.get("sets", {})
    pe = {s.get("policyengine_us") for s in sets.values()} - {None}
    cost = sum(s.get("cost_usd") or 0 for s in sets.values())
    harness = summary.get("harness")
    if harness:
        setup = (f"Harbor {harness.get('harbor', '?')} agent `{harness.get('agent', '?')}` on the {harness.get('tasks', '')} "
                 f"tasks: the model reads the PDFs, runs `benefits-calc` and writes `/app/answer.json`"
                 f"{' · up to ' + str(harness['max_turns']) + ' turns' if harness.get('max_turns') else ''}"
                 f"{' · ' + str(round(harness['agent_timeout_sec'] / 60)) + ' min per task' if harness.get('agent_timeout_sec') else ''}"
                 f"{' · temperature ' + str(harness['temperature']) if harness.get('temperature') is not None else ''} · ")
    else:
        setup = (f"{'document cases (application and paperwork, data/documents) · document ' if summary.get('case_format') == 'documents' else ''}"
                 f"prompt v{summary['prompt_version']} (`{summary['prompt_hash']}`) · ")
    lines = [
        f"# Eval: `{summary['model']}`",
        "",
        f"Run `{summary['run_id']}` · {setup}"
        f"answers from policyengine-us {', '.join(sorted(pe)) or '?'}"
        f"{' · max tokens ' + str(summary['max_tokens']) if summary.get('max_tokens') else ''}"
        f"{' · reasoning effort ' + summary['reasoning_effort'] if summary.get('reasoning_effort') else ''} · cost ${cost:.4f}",
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
    if sid["n"] and sood["n"]:
        cut = {k: sets.get(k, {}).get("cut_off", 0) for k in ("id", "ood")}
        lines.append(f"| Cut off at the token limit | {cut['id']} | {cut['ood']} | |")
    floors = {k: sets.get(k, {}).get("floors", {}) for k in ("id", "ood")}
    for key, label in (("always_no", "Floor: always \"no\""), ("always_yes", "Floor: always \"yes\", $0")):
        lines.append(f"| {label} | {num(floors['id'].get(key))} | {num(floors['ood'].get(key))} | |")
    api_errors = sid.get("api_errors", 0) + sood.get("api_errors", 0)
    if api_errors:
        lines += ["", f"{api_errors} cases got no answer from the API and aren't scored; see the result files."]

    if harness:
        lines += _agent_section(sets, id_rows, ood_rows, summary.get("compare_to"), run_dir.parent)

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
