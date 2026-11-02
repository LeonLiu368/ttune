"""The agentic baseline's collector: Harbor trial directories in, an evals run out."""

import json
import shutil
from pathlib import Path

from evals.compare import comparison_markdown
from harbortask import agentic, build, verify
from harbortask.split import holdout_rows


def fake_trial(jobs: Path, row: dict, *, answer: str | None, exception: str | None = None, verified: bool = True,
               reported: float | None = None) -> None:
    task = build.task_id(row["id"])
    trial = jobs / task / "2026-11-01__00-00-00" / f"{task}__abc"
    (trial / "artifacts" / "app").mkdir(parents=True)
    if answer is not None:
        (trial / "artifacts" / "app" / "answer.json").write_text(answer)
    rewards = verify.evaluate(answer, build.truth_file(row))
    if reported is not None:
        rewards = {**rewards, "reward": reported}
    result = {
        "task_name": f"ttune/{task}", "trial_name": f"{task}__abc", "finished_at": "2026-11-01T00:10:00+00:00",
        "agent_result": {"n_input_tokens": 5000, "n_output_tokens": 800, "metadata": {"n_episodes": 7}},
        "agent_execution": {"started_at": "2026-11-01T00:00:00+00:00", "finished_at": "2026-11-01T00:06:00+00:00"},
        "verifier_result": {"rewards": rewards} if verified else None,
        "exception_info": {"exception_type": exception, "exception_message": f"{exception} happened"} if exception else None,
    }
    (trial / "result.json").write_text(json.dumps(result))
    (trial.parent / "result.json").write_text(json.dumps({"stats": {}}))  # the job's own summary is skipped


def test_collect_scores_answers_and_separates_errors(tmp_path):
    ids, oods = holdout_rows("holdout-id")[:2], holdout_rows("holdout-ood")[:2]
    jobs = tmp_path / "jobs"
    fake_trial(jobs, ids[0], answer=json.dumps(verify.oracle(build.truth_file(ids[0]))))
    fake_trial(jobs, ids[1], answer=None, exception="AgentTimeoutError")
    fake_trial(jobs, oods[0], answer=None, exception="RuntimeError", verified=False)
    # oods[1] never ran.

    out = agentic.collect("run", [jobs], model="local/test", limit=2, results_dir=tmp_path / "results",
                          harness={"max_turns": 40, "agent_timeout_sec": 1800.0, "temperature": 0.0})
    rows = {s: [json.loads(line) for line in (out / f"{s}.jsonl").open()] for s in ("id", "ood")}
    good, timed_out = rows["id"]
    assert good["status"] == "ok" and good["score"]["reward"] == 1.0 and good["task_score"]["reward"] == 1.0
    assert good["agent"]["turns"] == 7 and good["agent"]["seconds"] == 360.0
    assert timed_out["status"] == "ok" and timed_out["finish_reason"] == "agent_timeout"
    assert timed_out["score"]["malformed"] and timed_out["score"]["reward"] == 0.0
    errored, not_run = rows["ood"]
    assert errored["status"] == "api_error" and errored["api_error"].startswith("RuntimeError")
    assert not_run["status"] == "api_error" and "not run" in not_run["api_error"]

    summary = json.loads((out / "summary.json").read_text())
    assert summary["harness"]["agent"] == "terminus-2" and summary["prompt_hash"] is None
    assert summary["sets"]["id"]["households"] == "data/documents/id/cases.jsonl"
    agent = summary["sets"]["id"]["agent"]
    assert agent["task_reward"] == 0.5 and agent["agent_timeouts"] == 1 and agent["no_answer"] == 1
    assert agent["harbor_reward_mismatches"] == []
    assert summary["sets"]["ood"]["agent"]["errors"] == 1 and summary["sets"]["ood"]["agent"]["not_run"] == 1

    text = comparison_markdown(out)
    assert "terminus-2" in text and "Task reward, with missing information" in text and "prompt v" not in text


def test_a_verifier_that_disagrees_is_reported(tmp_path):
    row = holdout_rows("holdout-id")[0]
    fake_trial(tmp_path / "jobs", row, answer=json.dumps(verify.oracle(build.truth_file(row))), reported=0.2)
    out = agentic.collect("run", [tmp_path / "jobs"], model="m", limit=1, results_dir=tmp_path / "results")
    assert json.loads((out / "summary.json").read_text())["sets"]["id"]["agent"]["harbor_reward_mismatches"] == \
        [row["id"]]
    assert "disagrees" in comparison_markdown(out)


def test_comparison_against_a_one_shot_run_pairs_households(tmp_path):
    rows = holdout_rows("holdout-id")[:3] + holdout_rows("holdout-ood")[:3]
    jobs = tmp_path / "jobs"
    for row in rows:
        fake_trial(jobs, row, answer=json.dumps(verify.oracle(build.truth_file(row))))
    results = tmp_path / "results"
    agentic.collect("one-shot", [jobs], model="m", limit=3, results_dir=results)
    # The one-shot run got everything wrong on the first ID household.
    path = results / "one-shot" / "id.jsonl"
    lines = [json.loads(line) for line in path.open()]
    lines[0]["score"] = {**lines[0]["score"], "reward": 0.0}
    path.write_text("".join(json.dumps(r) + "\n" for r in lines))
    out = agentic.collect("agent", [jobs], model="m", limit=3, results_dir=results, compare_to="one-shot")
    text = comparison_markdown(out)
    assert "Against the one-shot run `one-shot`" in text
    assert "| Households in both | 3 | 3 |" in text and "0.67 → 1.00: +0.33" in text


def test_trials_outside_the_run_are_refused(tmp_path):
    row = holdout_rows("holdout-ood")[5]
    fake_trial(tmp_path / "jobs", row, answer="{}")
    try:
        agentic.collect("run", [tmp_path / "jobs"], model="m", limit=2, results_dir=tmp_path / "results")
    except agentic.CollectError as exc:
        assert "aren't holdout tasks of this run" in str(exc)
    else:
        raise AssertionError("expected CollectError")


def test_no_trials_at_all_is_an_error_not_an_empty_run(tmp_path):
    (tmp_path / "jobs").mkdir()
    try:
        agentic.collect("run", [tmp_path / "jobs"], model="m", limit=1, results_dir=tmp_path / "results")
    except agentic.CollectError as exc:
        assert "no Harbor trials" in str(exc)
    else:
        raise AssertionError("expected CollectError")
    assert not (tmp_path / "results" / "run").exists()


def test_pick_builds_each_shards_tasks_once(tmp_path):
    import pytest

    pytest.importorskip("reportlab")
    names = [sorted(p.name for p in agentic.pick(tmp_path / str(k), limit=3, shard=(k, 2))) for k in range(2)]
    every = {build.task_id(r["id"]) for s in ("holdout-id", "holdout-ood") for r in holdout_rows(s)[:3]}
    assert not set(names[0]) & set(names[1]) and set(names[0]) | set(names[1]) == every
    assert (tmp_path / "0" / names[0][0] / "tests" / "truth.json").is_file()
    shutil.rmtree(tmp_path / "0")


def test_show_prints_the_answer_and_each_agent_turn(tmp_path):
    row = holdout_rows("holdout-id")[0]
    fake_trial(tmp_path / "jobs", row, answer='{"snap": {"eligible": true}}')
    trial = next(p.parent for p in (tmp_path / "jobs").rglob("result.json") if p.parent.name.endswith("__abc"))
    (trial / "agent").mkdir()
    (trial / "agent" / "trajectory.json").write_text(json.dumps({"steps": [
        {"step_id": 1, "source": "user", "message": "the instruction"},
        {"step_id": 2, "source": "agent", "message": '{"commands": [{"keystrokes": "pdftotext case/01.pdf -\\n"}]}',
         "observation": {"results": [{"content": "APPLICATION FOR BENEFITS"}]}},
    ]}))
    text = agentic.show(tmp_path / "jobs" / build.task_id(row["id"]))
    assert '"snap"' in text and "-- turn 2:" in text and "pdftotext" in text and "APPLICATION FOR BENEFITS" in text
    assert "the instruction" not in text
