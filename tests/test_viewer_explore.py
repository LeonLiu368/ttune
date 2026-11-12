"""The viewer's Experiments and Tasks sections: grouping, task data, files, trajectories, and keeping the private
splits out of anything published."""

import gzip
import json
import shutil
import threading

import pytest

from harbortask import build as task_build
from viewer import explore
from viewer.build import build
from tests.test_viewer import REAL_RUN, call

AGENT_RUN = "20991231-2359-harbor-test-agent"


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """A one-reply run and an agent run, 6 households per set each; the agent run has one trajectory."""
    root = tmp_path_factory.mktemp("results")
    for name, harness in (("20991231-2358-local-test-model", None), (AGENT_RUN, {"agent": "terminus-2"})):
        run = root / name
        run.mkdir()
        summary = json.loads((REAL_RUN / "summary.json").read_text())
        summary.pop("harness", None)
        if harness:
            summary["harness"] = harness
        (run / "summary.json").write_text(json.dumps(summary))
        for set_ in ("id", "ood"):
            lines = (REAL_RUN / f"{set_}.jsonl").read_text().splitlines()[:6]
            (run / f"{set_}.jsonl").write_text("\n".join(lines) + "\n")
    task = task_build.task_id("id-1-0000")
    folder = root / AGENT_RUN / "trajectories"
    folder.mkdir()
    (folder / f"{task}.json.gz").write_bytes(gzip.compress(json.dumps({"task": task, "steps": []}).encode(), mtime=0))
    return root


def test_runs_join_experiments_by_registry_then_by_kind(results, tmp_path):
    reg = {"experiments": {"mine": {"title": "Mine", "runs": ["20991231-2358-local-test-model"]}}, "notes": {}}
    assert explore.run_experiments(results, reg) == {AGENT_RUN: "agent-holdout", "20991231-2358-local-test-model": "mine"}
    assert explore.default_experiment({"sets": {"id": {"households": "data/documents/id/cases.jsonl"}}}) == "one-reply-docs"
    assert explore.default_experiment({"sets": {"id": {"households": "data/households/id/households.jsonl"}}}) == "one-reply-text"
    index = explore.experiments_index(results, reg)
    assert {e["id"] for e in index} == {"agent-holdout", "mine"}
    mine = next(e for e in index if e["id"] == "mine")
    assert mine["title"] == "Mine" and mine["tasks"] == 12 and mine["trials"] == 12
    assert sum(mine["counts"].values()) == 12


def test_cells_classify_each_result():
    ok = lambda r, **kw: {"status": "ok", "score": {"reward": r, "malformed": False}, **kw}  # noqa: E731
    assert explore.cell(ok(1.0))["status"] == "pass"
    assert explore.cell(ok(0.4))["status"] == "partial"
    assert explore.cell(ok(0.0))["status"] == "fail"
    assert explore.cell(ok(0.5, task_score={"reward": 0.42}))["task_reward"] == 0.42
    assert explore.cell({"status": "api_error", "api_error": "not run: the shard ran out of time"}) == {"status": "skipped"}
    assert explore.cell({"status": "api_error", "api_error": "RuntimeError: boom"}) == {"status": "error"}


def test_experiment_detail_has_a_leaderboard_and_a_grid(results):
    x = explore.experiment_detail("agent-holdout", results)
    assert x["runs"] == [AGENT_RUN] and len(x["leaderboard"]) == 1 and len(x["rows"]) == 12
    row = x["rows"][0]
    assert row["case"] == "id-1-0000" and row["task"] == task_build.task_id("id-1-0000") and AGENT_RUN in row["cells"]
    assert x["leaderboard"][0]["sets"]["id"]["trials"] == 6
    assert explore.experiment_detail("nope", results) is None


def test_task_rows_cover_the_holdout_only_unless_private_splits_are_given(tmp_path):
    rows = explore.task_rows()
    assert len(rows) == 400 and {r["split"] for r in rows} == {"holdout-id", "holdout-ood"}
    assert sum(r["sample"] for r in rows) == len(explore.sample_tasks()) == 6
    t = next(r for r in rows if r["case"] == "id-1-0000")
    assert t["truth"]["snap"] in ("yes", "no", "unknown") and t["truth"]["medicaid"]["of"] == t["members"]
    # A private splits directory (as the Task splits artifact unpacks) adds train and validation, on request only.
    (tmp_path / "train").mkdir()
    (tmp_path / "train" / "cases.jsonl").write_text((explore.DOCUMENTS_DIR / "id" / "cases.jsonl").read_text().splitlines()[0] + "\n")
    assert sum(r["split"] == "train" for r in explore.task_rows(tmp_path)) == 1


def test_static_build_publishes_holdout_tasks_files_and_trajectories(results, tmp_path):
    out = tmp_path / "site"
    build(out, results, task_limit=1)
    data = out / "data"
    tasks = json.loads((data / "tasks.json").read_text())["tasks"]
    assert len(tasks) == 400 and {t["split"] for t in tasks} == {"holdout-id", "holdout-ood"}
    task = task_build.task_id("id-1-0000")
    detail = json.loads((data / "tasks" / task / "task.json").read_text())
    files = {f["path"]: f for f in detail["files"]}
    assert files["instruction.md"]["group"] == "Prompt" and not files["instruction.md"]["shared"]
    pdfs = [p for p in files if p.startswith("environment/case/")]
    assert pdfs and all((data / "tasks" / task / "files" / p).read_bytes().startswith(b"%PDF") for p in pdfs)
    assert files["tests/truth.json"]["group"] == "Verification"
    shared = [p for p, f in files.items() if f["shared"]]
    assert "environment/calc/calc.py" in shared and all((data / "task-shared" / p).is_file() for p in shared)
    trial = next(t for t in detail["trials"] if t["run_id"] == AGENT_RUN)
    assert trial["trajectory"] and trial["experiment"] == "agent-holdout"
    assert (data / "runs" / AGENT_RUN / "trajectories" / f"{task}.json.gz").is_file()
    assert {e["id"] for e in json.loads((data / "experiments.json").read_text())} == {"agent-holdout", "one-reply-text"}
    assert (data / "experiments" / "agent-holdout.json").is_file()
    assert (out / "explore.js").is_file() and (out / "vendor" / "pdfjs" / "pdf.min.js").is_file()


@pytest.fixture()
def server(results):
    from viewer.server import ViewerServer

    srv = ViewerServer(("127.0.0.1", 0), results_dir=results)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    shutil.rmtree(srv.tasks.cache, ignore_errors=True)


def test_server_serves_experiments_tasks_files_and_trajectories(server):
    task = task_build.task_id("id-1-0000")
    assert call(server, "GET", "/data/experiments.json")[0] == 200
    assert call(server, "GET", "/data/experiments/agent-holdout.json")[1]["runs"] == [AGENT_RUN]
    assert len(call(server, "GET", "/data/tasks.json")[1]["tasks"]) == 400
    status, detail = call(server, "GET", f"/data/tasks/{task}/task.json")
    assert status == 200 and detail["case"] == "id-1-0000" and detail["trials"]
    status, body = call(server, "GET", f"/data/tasks/{task}/files/instruction.md")
    assert status == 200 and b"/app/answer.json" in body
    pdf = next(f["path"] for f in detail["files"] if f["kind"] == "pdf")
    assert call(server, "GET", f"/data/tasks/{task}/files/{pdf}")[1].startswith(b"%PDF")
    assert call(server, "GET", f"/data/runs/{AGENT_RUN}/trajectories/{task}.json.gz")[0] == 200
    for path in (f"/data/tasks/{task}/files/../../README.md", f"/data/tasks/{task}/files/%2e%2e/task.toml",
                 "/data/tasks/benefits-0000000000/task.json", f"/data/runs/{AGENT_RUN}/trajectories/..%2fsummary.json.gz",
                 "/data/experiments/..%2fx.json"):
        assert call(server, "GET", path)[0] == 404, path


def test_private_splits_are_refused_beyond_this_machine(tmp_path):
    from viewer.__main__ import main

    assert main(["serve", "--host", "0.0.0.0", "--port", "0", "--private-splits", str(tmp_path)]) == 2
