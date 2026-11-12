"""Experiments and tasks for the viewer: what the Experiments and Tasks sections read.

  data/experiments.json                         every experiment: title, runs and headline numbers
  data/experiments/<exp>.json                   one experiment: summary, leaderboard, the task x run grid
  data/tasks.json                               every task: metadata to search and filter on, and its results
  data/tasks/<task>/task.json                   one task: household, issues, documents, files and trials
  data/tasks/<task>/files/<path>                the task's own files (instruction, PDFs, answer key, ...)
  data/task-shared/<path>                       files every task has the same (calculator, verifier code)
  data/runs/<run>/trajectories/<task>.json.gz   one trial's agent turns (agent runs only)

An experiment groups runs that ran the same way on the same tasks (evals/experiments.json, else a default rule).
Every run scores the same holdout households, so a task (one household's case) has one result per run.

The public site holds only the holdout. Train and validation tasks have secret answers, and their documents alone
are enough to work those out, so they appear only on a local server started with --private-splits.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from viewer.data import RESULTS_DIR, ROOT, load_results, run_dirs, safe

EXPERIMENTS_FILE = ROOT / "evals" / "experiments.json"
DOCUMENTS_DIR = ROOT / "data" / "documents"
SAMPLES_DIR = ROOT / "tasks"
HOLDOUT = {"holdout-id": "id", "holdout-ood": "ood"}  # split -> document set
PRIVATE_SPLITS = ("train", "validation")
DEFAULT_EXPERIMENTS = {
    "agent-holdout": {"title": "Agent on the holdout tasks", "description": "An agent works through each task."},
    "one-reply-docs": {"title": "One reply, from the paperwork", "description": "One prompt with the documents."},
    "one-reply-text": {"title": "One reply, from a written summary", "description": "One prompt with a summary."},
}
# The task's own files; every other file is checked against the shared copy and stored once if it matches.
GROUPS = (("Prompt", ("instruction.md",)), ("Documents", ("environment/case/",)),
          ("Reference solution", ("solution/",)), ("Verification", ("tests/",)),
          ("Agent environment", ("environment/",)), ("Task metadata", ("task.toml", "README.md")))
PROGRAMS = ("snap", "eitc", "medicaid", "wic")


# --- experiments --------------------------------------------------------------------------------

def registry(path: Path = EXPERIMENTS_FILE) -> dict:
    data = json.loads(path.read_text()) if path.is_file() else {}
    return {"experiments": data.get("experiments", {}), "notes": data.get("notes", {})}


def default_experiment(summary: dict) -> str:
    if summary.get("harness"):
        return "agent-holdout"
    households = [str(s.get("households") or "") for s in summary.get("sets", {}).values()]
    return "one-reply-docs" if any("data/documents" in h for h in households) else "one-reply-text"


def run_experiments(results_dir: Path = RESULTS_DIR, reg: dict | None = None) -> dict[str, str]:
    """Run id -> experiment id, for every run in results_dir."""
    reg = reg or registry()
    listed = {run: exp for exp, e in reg["experiments"].items() for run in e.get("runs", [])}
    out = {}
    for run_dir in run_dirs(results_dir):
        summary = json.loads((run_dir / "summary.json").read_text())
        out[run_dir.name] = listed.get(run_dir.name) or default_experiment(summary)
    return out


def cell(record: dict) -> dict:
    """One task's result in one run: a status class and the rewards."""
    if record["status"] != "ok":
        skipped = "not run" in (record.get("api_error") or "")
        return {"status": "skipped" if skipped else "error"}
    reward = record["score"]["reward"]
    out = {"status": "pass" if reward >= 0.999 else "partial" if reward > 0 else "fail", "reward": round(reward, 4)}
    if record.get("task_score"):
        out["task_reward"] = round(record["task_score"]["reward"], 4)
    if record["score"].get("malformed"):
        out["malformed"] = True
    return out


def _run_info(run_dir: Path, notes: dict) -> dict:
    summary = json.loads((run_dir / "summary.json").read_text())
    info = summary.get("model_info") or {}
    sets = summary.get("sets", {})
    return {
        "run_id": run_dir.name, "model": summary.get("model"), "note": notes.get(run_dir.name),
        "base": info.get("base"), "repo": info.get("repo"), "harness": (summary.get("harness") or {}).get("agent"),
        "cost_usd": round(sum((s.get("cost_usd") or 0) for s in sets.values()), 6),
        "tokens": sum((s.get("prompt_tokens") or 0) + (s.get("completion_tokens") or 0) for s in sets.values()),
    }


def _stats(cells: list[dict]) -> dict:
    counts = Counter(c["status"] for c in cells)
    rewards = [c["reward"] for c in cells if "reward" in c]
    task_rewards = [c["task_reward"] for c in cells if "task_reward" in c]
    return {
        "trials": len(cells), "finished": len(cells) - counts["skipped"],
        "counts": {k: counts[k] for k in ("pass", "partial", "fail", "error", "skipped")},
        "reward": round(sum(rewards) / len(rewards), 4) if rewards else None,
        "task_reward": round(sum(task_rewards) / len(task_rewards), 4) if task_rewards else None,
        "malformed": sum(bool(c.get("malformed")) for c in cells),
    }


def _records(run_dir: Path) -> list[dict]:
    return [r for set_ in ("id", "ood") for r in load_results(run_dir, set_)]


def experiments_index(results_dir: Path = RESULTS_DIR, reg: dict | None = None) -> list[dict]:
    reg = reg or registry()
    members = defaultdict(list)
    for run, exp in run_experiments(results_dir, reg).items():
        members[exp].append(run)
    out = []
    for exp in sorted(members, key=lambda e: max(members[e]), reverse=True):
        meta = {**DEFAULT_EXPERIMENTS.get(exp, {}), **reg["experiments"].get(exp, {})}
        runs = sorted(members[exp], reverse=True)
        cells = [cell(r) for run in runs for r in _records(results_dir / run)]
        tasks = {r["id"] for run in runs for r in _records(results_dir / run)}
        out.append({"id": exp, "title": meta.get("title", exp), "description": meta.get("description"),
                    "runs": runs, "created": min(runs)[:8], "updated": max(runs)[:8], "tasks": len(tasks),
                    **_stats(cells)})
    return out


def experiment_detail(exp: str, results_dir: Path = RESULTS_DIR, reg: dict | None = None,
                      tasks: dict[str, dict] | None = None) -> dict | None:
    reg = reg or registry()
    runs = sorted((r for r, e in run_experiments(results_dir, reg).items() if e == exp), reverse=True)
    if not runs:
        return None
    meta = {**DEFAULT_EXPERIMENTS.get(exp, {}), **reg["experiments"].get(exp, {})}
    tasks = tasks if tasks is not None else {t["case"]: t for t in task_rows()}
    board, grid = [], {}
    all_cells = []
    for run in runs:
        records = _records(results_dir / run)
        cells = {r["id"]: cell(r) for r in records}
        all_cells += cells.values()
        by_set = {s: _stats([cells[r["id"]] for r in records if r["id"].startswith(f"{s}-")]) for s in ("id", "ood")}
        board.append({**_run_info(results_dir / run, reg["notes"]), **_stats(list(cells.values())),
                      "sets": {s: {"reward": v["reward"], "trials": v["trials"]} for s, v in by_set.items()}})
        for case, c in cells.items():
            grid.setdefault(case, {})[run] = c
    board.sort(key=lambda b: (b["reward"] is None, -(b["reward"] or 0)))
    rows = []
    for case in sorted(grid, key=lambda c: (c.split("-")[0] != "id", c)):
        t = tasks.get(case, {})
        rows.append({"case": case, "task": t.get("task"), "split": t.get("split"), "state": t.get("state"),
                     "shift": t.get("shift"), "twists": t.get("twists", []), "issues": t.get("issues", []),
                     "cells": grid[case]})
    return {"id": exp, "title": meta.get("title", exp), "description": meta.get("description"),
            "runs": runs, "created": min(runs)[:8], "tasks": len(rows), **_stats(all_cells),
            "leaderboard": board, "rows": rows}


# --- tasks --------------------------------------------------------------------------------------

def _yes_no(value) -> str:
    return "unknown" if value == "unknown" else "yes" if value else "no"


def task_meta(row: dict, split: str, samples: set[str] = frozenset()) -> dict:
    from harbortask import build

    h, truth = row["household"], row["truth"]
    members = h["members"]
    issues = row["packet"]["issues"]
    return {
        "task": build.task_id(row["id"]), "case": row["id"], "split": split, "sample": build.task_id(row["id"]) in samples,
        "state": h["state"], "members": len(members), "shift": h.get("shift") or "none", "twists": h.get("twists") or [],
        "edge": (h.get("edge") or {}).get("program") if isinstance(h.get("edge"), dict) else h.get("edge"),
        "issues": sorted({i["kind"] for i in issues}),
        "gaps": sorted({i["gap"]["fact"] for i in issues if isinstance(i.get("gap"), dict) and i["gap"].get("fact")}),
        "documents": len(row["packet"]["documents"]),
        "missing": truth.get("missing_information", []),
        "truth": {
            "snap": _yes_no(truth["snap"]["eligible"]), "eitc": _yes_no(truth["eitc"]["eligible"]),
            "medicaid": {"eligible": len(truth["medicaid"]["eligible_members"]),
                         "unknown": len(truth["medicaid"].get("unknown_members", [])), "of": len(members)},
            "wic": {"eligible": len(truth["wic"]["eligible_members"]),
                    "unknown": len(truth["wic"].get("unknown_members", [])), "of": len(members)},
        },
    }


def sample_tasks(samples_dir: Path = SAMPLES_DIR) -> set[str]:
    return {p.name for p in samples_dir.glob("benefits-*") if p.is_dir()}


def case_rows(split: str, private_dir: Path | None = None) -> list[dict]:
    """The document cases of a split: the holdout from data/documents, train/validation from a private splits dir."""
    if split in HOLDOUT:
        path = DOCUMENTS_DIR / HOLDOUT[split] / "cases.jsonl"
    elif split in PRIVATE_SPLITS and private_dir is not None:
        path = private_dir / split / "cases.jsonl"
    else:
        return []
    return [json.loads(line) for line in path.open()] if path.is_file() else []


def task_rows(private_dir: Path | None = None) -> list[dict]:
    samples = sample_tasks()
    splits = list(HOLDOUT) + (list(PRIVATE_SPLITS) if private_dir is not None else [])
    return [task_meta(row, split, samples) for split in splits for row in case_rows(split, private_dir)]


def run_results(results_dir: Path = RESULTS_DIR, reg: dict | None = None) -> dict[str, dict[str, dict]]:
    """Case id -> run id -> {experiment, cell}, over every run."""
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for run, exp in run_experiments(results_dir, reg).items():
        for r in _records(results_dir / run):
            out[r["id"]][run] = {"experiment": exp, **cell(r)}
    return out


def tasks_index(results_dir: Path = RESULTS_DIR, private_dir: Path | None = None, reg: dict | None = None) -> dict:
    results = run_results(results_dir, reg)
    rows = [{**t, "results": results.get(t["case"], {})} for t in task_rows(private_dir)]
    return {"tasks": rows, "experiments": [{"id": e["id"], "title": e["title"], "runs": e["runs"]}
                                           for e in experiments_index(results_dir, reg)]}


def group_of(path: str) -> str:
    for label, prefixes in GROUPS:
        if any(path == p or (p.endswith("/") and path.startswith(p)) for p in prefixes):
            return label
    return "Task metadata"


def build_task(row: dict, out_dir: Path) -> Path:
    """The task's Harbor directory, as harbortask builds it."""
    from harbortask import build

    return build.build(row, out_dir)


def task_files(task_dir: Path, shared: dict[str, bytes] | None = None) -> list[dict]:
    """Every file of a built task, in tree order. With `shared`, files identical across tasks are marked shared."""
    files = []
    for path in sorted(p for p in task_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(task_dir).as_posix()
        body = path.read_bytes()
        own = rel in ("instruction.md", "task.toml", "README.md", "tests/truth.json", "solution/solve.sh") \
            or rel.startswith("environment/case/")
        is_shared = shared is not None and not own and shared.setdefault(rel, body) == body
        files.append({"path": rel, "size": len(body), "group": group_of(rel), "shared": is_shared,
                      "kind": "pdf" if rel.endswith(".pdf") else "markdown" if rel.endswith(".md") else "text"})
    order = {label: i for i, (label, _) in enumerate(GROUPS)}
    return sorted(files, key=lambda f: (order[f["group"]], f["path"]))


def task_detail(row: dict, meta: dict, files: list[dict], results: dict[str, dict], results_dir: Path = RESULTS_DIR,
                reg: dict | None = None) -> dict:
    reg = reg or registry()
    trials = []
    for run, res in sorted(results.items(), reverse=True):
        run_dir = results_dir / run
        record = next((r for r in load_results(run_dir, row["id"].split("-")[0]) if r["id"] == row["id"]), None)
        agent = (record or {}).get("agent") or {}
        has_turns = (run_dir / "trajectories" / f"{meta['task']}.json.gz").is_file()
        trials.append({**_run_info(run_dir, reg["notes"]), **res, "trajectory": has_turns,
                       "turns": agent.get("turns"), "seconds": agent.get("seconds"),
                       "finish_reason": (record or {}).get("finish_reason"),
                       "usage": (record or {}).get("usage")})
    issues = [{"kind": i["kind"], "detail": i.get("detail"), "missing": i.get("flag")} for i in row["packet"]["issues"]]
    documents = [{"name": d["name"], "kind": d["kind"], "date": d.get("date")} for d in row["packet"]["documents"]]
    return {**meta, "issues_detail": issues, "documents_detail": documents, "files": files, "trials": trials}


def copy_trajectories(results_dir: Path, out: Path) -> int:
    n = 0
    for run_dir in run_dirs(results_dir):
        folder = run_dir / "trajectories"
        if folder.is_dir():
            shutil.copytree(folder, out / "data" / "runs" / run_dir.name / "trajectories", dirs_exist_ok=True)
            n += sum(1 for _ in folder.glob("*.json.gz"))
    return n


def safe_path(rel: str) -> bool:
    parts = rel.split("/")
    return bool(rel) and all(safe(p) for p in parts)
