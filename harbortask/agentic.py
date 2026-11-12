"""The agentic baseline: a model drives Harbor's terminus-2 agent through the holdout tasks.

`pick` writes the task directories one shard runs; `collect` reads the trials Harbor wrote and stores them as an
evals run (evals/results/<run id>/{id,ood}.jsonl and summary.json), so `python -m evals compare` and the viewer
work on it unchanged. Each answer is scored twice from the same /app/answer.json:

- with the evals scorer (`reward`), so the numbers line up with the one-shot runs on the same households;
- with the task's own reward (`task_score`: eligibility, amount and the missing-information list, as the
  verifier scores it), checked against what Harbor's verifier reported.

Every trial's agent turns are kept too, one gzipped file per task in trajectories/ (the holdout is public, so they
can be published), for the viewer's trajectory display.

A trial the verifier scored counts, whatever the agent did: an agent that timed out or never wrote an answer
scores 0, like a malformed reply. A trial that never reached the verifier (the environment failed to build, the
model server was down) is an error, not a score, and so is a task a shard ran out of time to start.
"""

from __future__ import annotations

import gzip
import json
import statistics
from datetime import datetime
from pathlib import Path

from evals.run import RESULTS_DIR, ROOT, _base, evaluate, select, write_set
from harbortask import build, verify
from harbortask.split import HOLDOUT, holdout_rows

HARBOR = "0.25.0"
AGENT = "terminus-2"
SETS = {"id": "holdout-id", "ood": "holdout-ood"}  # evals set name -> split


class CollectError(Exception):
    pass


def chosen(set_: str, limit: int | None = None, shard: tuple[int, int] | None = None) -> list[tuple[int, dict]]:
    """(index, case) for the tasks to run, chosen the way `evals run` chooses households."""
    return select(holdout_rows(SETS[set_]), limit, shard)


def pick(out: Path, limit: int | None = None, shard: tuple[int, int] | None = None) -> list[Path]:
    """Build this shard's tasks, from both holdout sets, into out/<task id>/."""
    out.mkdir(parents=True, exist_ok=True)
    return [build.build(row, out) for set_ in SETS for _, row in chosen(set_, limit, shard)]


def pick_generated(out: Path, split: str, n_cases: int, secret: str, start: int = 0, limit: int | None = None,
                   shard: tuple[int, int] | None = None) -> list[Path]:
    """Build this shard's tasks from a secret-seeded split (train, validation): cases start .. start+limit-1."""
    from harbortask.split import GENERATED, generated_rows

    if split not in GENERATED:
        raise CollectError(f"{split!r} isn't a generated split ({', '.join(GENERATED)})")
    rows = generated_rows(split, n_cases, secret)[start:]
    out.mkdir(parents=True, exist_ok=True)
    return [build.build(row, out) for _, row in select(rows, limit, shard)]


def _seconds(timing: dict | None) -> float | None:
    if not timing or not timing.get("started_at") or not timing.get("finished_at"):
        return None
    start, end = (datetime.fromisoformat(timing[k]) for k in ("started_at", "finished_at"))
    return round((end - start).total_seconds(), 1)


def trials(jobs: list[Path]) -> dict[str, tuple[dict, Path]]:
    """Task id -> (Harbor's trial result, trial directory). If a task ran more than once, the last run wins."""
    found: dict[str, tuple[dict, Path]] = {}
    for root in jobs:
        for path in sorted(root.rglob("result.json")):
            result = json.loads(path.read_text())
            if "trial_name" not in result or "task_name" not in result:
                continue  # a job's summary, not a trial
            task = result["task_name"].rsplit("/", 1)[-1]
            if task in found and (found[task][0].get("finished_at") or "") > (result.get("finished_at") or ""):
                continue
            found[task] = (result, path.parent)
    return found


def record(index: int, row: dict, trial: tuple[dict, Path] | None) -> dict:
    """One household's result, in the evals format plus the agent's run."""
    out = _base(index, row)
    if trial is None:
        return {**out, "status": "api_error", "api_error": "not run: the shard ran out of time before this task"}
    result, trial_dir = trial
    exc = result.get("exception_info") or {}
    agent = result.get("agent_result") or {}
    verifier = result.get("verifier_result")
    run = {"task": build.task_id(row["id"]), "trial": result.get("trial_name"),
           "exception": exc.get("exception_type"),
           "turns": (agent.get("metadata") or {}).get("n_episodes"),
           "seconds": _seconds(result.get("agent_execution")),
           "harbor_rewards": (verifier or {}).get("rewards")}
    if verifier is None:
        message = (exc.get("exception_message") or "no verifier result").strip().splitlines()
        return {**out, "status": "api_error", "agent": run,
                "api_error": f"{exc.get('exception_type') or 'error'}: {(message or [''])[0][:300]}"}
    answer = trial_dir / "artifacts" / "app" / "answer.json"
    text = answer.read_text() if answer.is_file() else ""
    finish = "agent_timeout" if run["exception"] == "AgentTimeoutError" else ("stop" if text else "no_answer")
    scored = evaluate(row, text)
    if not text:
        scored["parse_error"] = "the agent wrote no /app/answer.json" + (" (timed out)" if finish == "agent_timeout" else "")
    return {**out, "status": "ok", "reply": text, "finish_reason": finish, "attempts": 1,
            "usage": {"prompt_tokens": agent.get("n_input_tokens") or 0,
                      "completion_tokens": agent.get("n_output_tokens") or 0,
                      "cached_tokens": agent.get("n_cache_tokens") or 0},
            "task_score": verify.evaluate(text, build.truth_file(row)), "agent": run, **scored}


PHASES = (("environment_setup", "Environment setup"), ("agent_setup", "Agent setup"),
          ("agent_execution", "Agent running"), ("verifier", "Verification"))


def _content(value) -> str:
    if isinstance(value, list):  # content parts
        return "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in value)
    return "" if value is None else str(value)


def trajectory(task: str, result: dict, trial_dir: Path) -> dict:
    """One trial for the viewer: its timeline, rewards, answer file and every step (message, commands, output)."""
    exc = result.get("exception_info") or {}
    path = trial_dir / "agent" / "trajectory.json"
    raw = json.loads(path.read_text()) if path.is_file() else {}
    steps = []
    for step in raw.get("steps") or []:
        metrics = step.get("metrics") or {}
        steps.append({
            "id": step.get("step_id"), "source": step.get("source"), "time": step.get("timestamp"),
            "message": _content(step.get("message")),
            "reasoning": step.get("reasoning_content") or None,
            "calls": [{"name": c.get("function_name"), "args": c.get("arguments")} for c in step.get("tool_calls") or []],
            "output": [_content(r.get("content")) for r in ((step.get("observation") or {}).get("results") or [])],
            "tokens": {k: metrics.get(k) for k in ("prompt_tokens", "completion_tokens") if metrics.get(k) is not None},
        })
    answer = trial_dir / "artifacts" / "app" / "answer.json"
    agent = result.get("agent_result") or {}
    return {
        "task": task, "trial": result.get("trial_name"),
        "started_at": result.get("started_at"), "finished_at": result.get("finished_at"),
        "phases": [{"key": key, "label": label, "started_at": (result.get(key) or {}).get("started_at"),
                    "finished_at": (result.get(key) or {}).get("finished_at"), "seconds": _seconds(result.get(key))}
                   for key, label in PHASES],
        "rewards": (result.get("verifier_result") or {}).get("rewards"),
        "exception": {"type": exc.get("exception_type"), "message": (exc.get("exception_message") or "")[:2000]}
        if exc else None,
        "tokens": {"input": agent.get("n_input_tokens"), "output": agent.get("n_output_tokens"),
                   "cached": agent.get("n_cache_tokens")},
        "answer": answer.read_text() if answer.is_file() else None,
        "steps": steps,
    }


def write_trajectories(out_dir: Path, found: dict[str, tuple[dict, Path]], cases: dict[str, tuple[str, str]]) -> int:
    """trajectories/<task>.json.gz for each trial of the run's tasks, and trajectories/index.json listing them.
    `cases` maps each task id to its (set, case id). gzip without a timestamp, so a rebuild changes nothing."""
    folder = out_dir / "trajectories"
    folder.mkdir(parents=True, exist_ok=True)
    index = {}
    for task, (result, trial_dir) in sorted(found.items()):
        if task not in cases:
            continue
        data = trajectory(task, result, trial_dir)
        blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        (folder / f"{task}.json.gz").write_bytes(gzip.compress(blob, compresslevel=9, mtime=0))
        set_, case = cases[task]
        index[task] = {"set": set_, "case": case, "steps": len(data["steps"]),
                       "reward": (data["rewards"] or {}).get("reward")}
    (folder / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    return len(index)


def run_cases(limit: int | None = None) -> dict[str, tuple[str, str]]:
    """Task id -> (set, case id) for the holdout tasks of a run."""
    return {build.task_id(row["id"]): (set_, row["id"]) for set_ in SETS for _, row in chosen(set_, limit)}


def backfill_trajectories(run_dir: Path, jobs: list[Path]) -> int:
    """Add trajectories to a run collected before they were kept. Only the run's own scored tasks are written."""
    if not (run_dir / "summary.json").is_file():
        raise CollectError(f"{run_dir} isn't a collected run")
    scored_tasks = {}
    for set_ in SETS:
        path = run_dir / f"{set_}.jsonl"
        for line in path.open() if path.is_file() else []:
            row = json.loads(line)
            if row.get("agent"):
                scored_tasks[row["agent"]["task"]] = (set_, row["id"])
    found = trials(jobs)
    stray = sorted(set(found) - set(scored_tasks))
    if stray:
        raise CollectError(f"{len(stray)} trials aren't tasks this run scored, e.g. {stray[:3]}")
    return write_trajectories(run_dir, found, scored_tasks)


def _median(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def agent_stats(results: list[dict]) -> dict:
    ok = [r for r in results if r["status"] == "ok"]
    mismatched = [r["id"] for r in ok if (r["agent"].get("harbor_rewards") or {}).get("reward") is not None
                  and abs(r["agent"]["harbor_rewards"]["reward"] - r["task_score"]["reward"]) > 1e-6]

    def mean(key: str) -> float | None:
        return round(statistics.mean(r["task_score"][key] for r in ok), 4) if ok else None

    return {
        "task_reward": mean("reward"), "task_missing_info": mean("missing_info"),
        "agent_timeouts": sum(r["finish_reason"] == "agent_timeout" for r in ok),
        "no_answer": sum(not r["reply"] for r in ok),
        "errors": sum(r["status"] == "api_error" and "agent" in r for r in results),
        "not_run": sum(r["status"] == "api_error" and "agent" not in r for r in results),
        "median_turns": _median([r["agent"].get("turns") for r in ok]),
        "median_minutes": None if _median([r["agent"].get("seconds") for r in ok]) is None
        else round(_median([r["agent"].get("seconds") for r in ok]) / 60, 1),
        "harbor_reward_mismatches": mismatched,
    }


def collect(run_id: str, jobs: list[Path], *, model: str, limit: int | None = None, harness: dict | None = None,
            model_info: dict | None = None, compare_to: str | None = None, base_url: str | None = None,
            results_dir: Path = RESULTS_DIR) -> Path:
    found = trials(jobs)
    if not found:
        raise CollectError(f"no Harbor trials under {', '.join(map(str, jobs))}: every shard failed before running a task")
    out_dir = results_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = {"run_id": run_id, "model": model, "base_url": base_url, "max_tokens": None, "reasoning_effort": None}
    if model_info:
        settings["model_info"] = model_info
    wanted = set()
    stats = {}
    for set_, split in SETS.items():
        picked = chosen(set_, limit)
        wanted |= {build.task_id(row["id"]) for _, row in picked}
        results = [record(i, row, found.get(build.task_id(row["id"]))) for i, row in picked]
        path = ROOT / "data" / "documents" / HOLDOUT[split] / "cases.jsonl"
        write_set(out_dir, set_, path, [row for _, row in picked], results, limit, settings)
        stats[set_] = agent_stats(results)
    stray = sorted(set(found) - wanted)
    if stray:
        raise CollectError(f"{len(stray)} trials aren't holdout tasks of this run, e.g. {stray[:3]}")
    write_trajectories(out_dir, found, run_cases(limit))
    summary_path = out_dir / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary.update({"harness": {"agent": AGENT, "harbor": HARBOR, "tasks": "holdout-id + holdout-ood", **(harness or {})},
                    "prompt_version": None, "prompt_hash": None, "compare_to": compare_to})
    for set_, s in stats.items():
        summary["sets"][set_]["agent"] = s
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return out_dir


def _text(value, limit: int) -> str:
    if isinstance(value, list):  # content parts
        value = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in value)
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit] + " …"


def show(job_dir: Path, message_chars: int = 600, observation_chars: int = 300) -> str:
    """A trial in a few lines, for the workflow log: its result, the answer file and every agent turn."""
    found = trials([job_dir])
    lines = []
    for task, (result, trial_dir) in sorted(found.items()):
        exc = result.get("exception_info") or {}
        rewards = (result.get("verifier_result") or {}).get("rewards")
        lines.append(f"== {task}: rewards={rewards} exception={exc.get('exception_type')}"
                     f"{' (' + _text(exc.get('exception_message'), 200) + ')' if exc else ''}")
        answer = trial_dir / "artifacts" / "app" / "answer.json"
        lines.append(f"answer.json: {_text(answer.read_text(), 800) if answer.is_file() else 'none'}")
        path = trial_dir / "agent" / "trajectory.json"
        steps = json.loads(path.read_text()).get("steps", []) if path.is_file() else []
        for step in steps:
            if step.get("source") != "agent":
                continue
            lines.append(f"-- turn {step.get('step_id')}: {_text(step.get('message'), message_chars)}")
            for res in ((step.get("observation") or {}).get("results") or []):
                lines.append(f"   => {_text(res.get('content'), observation_chars)}")
    return "\n".join(lines) or f"no trials under {job_dir}"
