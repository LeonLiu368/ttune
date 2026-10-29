"""Write the viewer as a static site: the frontend plus every run's data as JSON files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from viewer import data

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def build(out: Path, results_dir: Path = data.RESULTS_DIR, sets_dir: Path = data.SETS_DIR) -> dict:
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
    return {"runs": len(index), "cases": cases, "out": str(out)}
