"""Write the viewer as a static site: the frontend plus every run's data as JSON files."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from viewer import data, explore

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def build(out: Path, results_dir: Path = data.RESULTS_DIR, sets_dir: Path = data.SETS_DIR, task_limit: int | None = None) -> dict:
    """task_limit: write only the first N tasks' files and pages per split (for tests); tasks.json still lists all."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC_DIR, out, ignore=shutil.ignore_patterns(".hallmark"))
    (out / ".nojekyll").write_text("")  # serve files as they are on GitHub Pages
    index = data.runs_index(results_dir)
    _write(out / "data" / "runs.json", index)
    _write(out / "data" / "site.json", {"static": True})  # tells the frontend there's no server to ask
    cases = 0
    for run_dir in data.run_dirs(results_dir):
        base = out / "data" / "runs" / run_dir.name
        _write(base / "overview.json", data.run_overview(run_dir))
        for set_ in data.SETS:
            rows = data.case_rows(run_dir, set_)
            if not rows:
                continue
            _write(base / f"{set_}.json", rows)
            for row in rows:
                _write(base / "cases" / f"{row['id']}.json", data.case_detail(run_dir, row["id"], sets_dir))
                cases += 1
    tasks = build_explore(out, results_dir, task_limit)
    return {"runs": len(index), "cases": cases, "tasks": tasks, "out": str(out)}


def build_explore(out: Path, results_dir: Path = data.RESULTS_DIR, task_limit: int | None = None) -> int:
    """The Experiments and Tasks sections: the holdout tasks only. Train and validation never go into a build."""
    reg = explore.registry()
    experiments = explore.experiments_index(results_dir, reg)
    _write(out / "data" / "experiments.json", experiments)
    metas = {t["case"]: t for t in explore.task_rows()}
    for e in experiments:
        _write(out / "data" / "experiments" / f"{e['id']}.json", explore.experiment_detail(e["id"], results_dir, reg, metas))
    _write(out / "data" / "tasks.json", explore.tasks_index(results_dir, reg=reg))
    results = explore.run_results(results_dir, reg)
    shared: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for split in explore.HOLDOUT:
            for row in explore.case_rows(split)[:task_limit]:
                meta = metas[row["id"]]
                task_dir = explore.build_task(row, Path(tmp))
                files = explore.task_files(task_dir, shared)
                for f in files:
                    target = out / "data" / ("task-shared" if f["shared"] else f"tasks/{meta['task']}/files") / f["path"]
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(task_dir / f["path"], target)
                _write(out / "data" / "tasks" / meta["task"] / "task.json",
                       explore.task_detail(row, meta, files, results.get(row["id"], {}), results_dir, reg))
                shutil.rmtree(task_dir)
    explore.copy_trajectories(results_dir, out)
    return len(metas)
