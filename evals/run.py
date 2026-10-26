"""Run a model over a household set and write scored results."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from evals import prompt
from evals.answer import parse_answer
from evals.client import ApiError, ChatClient, FatalApiError
from evals.metrics import floors, summarize
from evals.score import score

ROOT = Path(__file__).resolve().parents[1]
SETS_DIR = ROOT / "data" / "households"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def default_run_id(model: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now:%Y%m%d-%H%M}-" + re.sub(r"[^A-Za-z0-9.-]+", "-", model).strip("-").lower()


def load_set(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh]


def _names(row: dict) -> dict[str, str]:
    return {m["name"]: m["id"] for m in row["household"]["members"]}


def evaluate(row: dict, text: str, finish_reason: str | None = None) -> dict:
    """Parse and score one reply."""
    answer, error = parse_answer(text, _names(row))
    if answer is None and finish_reason == "length":
        error = f"cut off at the token limit before the answer ({error})"
    member_ids = [m["id"] for m in row["household"]["members"]]
    return {"answer": answer, "parse_error": error, "score": score(answer, row["truth"], member_ids)}


def _base(index: int, row: dict) -> dict:
    h = row["household"]
    return {"id": row["id"], "index": index, "shift": h["shift"], "twists": h["twists"],
            "edge_program": (h.get("edge") or {}).get("program")}


async def _one(client: ChatClient, index: int, row: dict) -> dict:
    out = _base(index, row)
    try:
        completion = await client.complete(prompt.messages(row["case"]))
    except FatalApiError:
        raise
    except ApiError as exc:
        return {**out, "status": "api_error", "api_error": str(exc)}
    return {**out, "status": "ok", "reply": completion.text, "usage": completion.usage,
            "attempts": completion.attempts, "finish_reason": completion.finish_reason,
            **evaluate(row, completion.text, completion.finish_reason)}


GIVE_UP_AFTER = 3  # failed cases in a row, before any case succeeds: the endpoint is down or rate-limited


async def _run_all(client: ChatClient, todo: list[tuple[int, dict]], partial: Path) -> list[dict]:
    results, answered = [], False
    with partial.open("a") as fh:
        for task in asyncio.as_completed([_one(client, i, row) for i, row in todo]):
            result = await task
            fh.write(json.dumps(result, sort_keys=True) + "\n")
            fh.flush()
            results.append(result)
            answered = answered or result["status"] == "ok"
            if not answered and len(results) >= GIVE_UP_AFTER:
                raise FatalApiError(f"the first {len(results)} cases all failed, so the endpoint looks down or "
                                    f"rate-limited; last error: {result['api_error'][:300]}")
    return results


def select(rows: list[dict], limit: int | None = None, shard: tuple[int, int] | None = None) -> list[tuple[int, dict]]:
    """(index in the full set, row) for the households to run: the first `limit`, then every n-th from k for shard k/n."""
    chosen = list(enumerate(rows[:limit] if limit else rows))
    if shard:
        k, n = shard
        chosen = [(i, row) for i, row in chosen if i % n == k]
    return chosen


def run(set_: str, model: str, *, run_id: str | None = None, limit: int | None = None, base_url: str | None = None,
        households: Path | None = None, resume: bool = False, concurrency: int = 8, retries: int = 5,
        max_tokens: int = 8000, reasoning_effort: str | None = None, timeout: float = 180.0,
        shard: tuple[int, int] | None = None, model_info: dict | None = None,
        results_dir: Path = RESULTS_DIR, api_key: str | None = None) -> tuple[Path, dict]:
    """Run one set (or one shard of it). Returns (run directory, that set's summary)."""
    path = households or SETS_DIR / set_ / "households.jsonl"
    chosen = select(load_set(path), limit, shard)
    run_id = run_id or default_run_id(model)
    out_dir = results_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    final, partial = out_dir / f"{set_}.jsonl", out_dir / f"{set_}.partial.jsonl"

    done: dict[str, dict] = {}
    if resume:
        for file in (final, partial):
            if file.is_file():
                for line in file.open():
                    result = json.loads(line)
                    if result["status"] == "ok":
                        done[result["id"]] = result
    elif partial.exists():
        partial.unlink()
    todo = [(i, row) for i, row in chosen if row["id"] not in done]

    async def go() -> list[dict]:
        kwargs = {"concurrency": concurrency, "retries": retries, "max_tokens": max_tokens,
                  "reasoning_effort": reasoning_effort, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        client = ChatClient(model, api_key=api_key, **kwargs)
        try:
            return await _run_all(client, todo, partial)
        finally:
            await client.aclose()

    new = asyncio.run(go()) if todo else []
    wanted = {row["id"] for _, row in chosen}
    results = sorted([r for r in done.values() if r["id"] in wanted] + new, key=lambda r: r["index"])
    settings = {"run_id": run_id, "model": model, "base_url": base_url or "https://openrouter.ai/api/v1",
                "max_tokens": max_tokens, "reasoning_effort": reasoning_effort}
    if model_info:
        settings["model_info"] = model_info
    set_summary = write_set(out_dir, set_, path, [row for _, row in chosen], results, limit, settings,
                            shard=f"{shard[0]}/{shard[1]}" if shard else None)
    partial.unlink(missing_ok=True)
    return out_dir, set_summary


def write_set(out_dir: Path, set_: str, path: Path, rows: list[dict], results: list[dict], limit: int | None,
              settings: dict, shard: str | None = None) -> dict:
    """Write <set>.jsonl and this set's entry in summary.json."""
    with (out_dir / f"{set_}.jsonl").open("w") as fh:
        for result in results:
            fh.write(json.dumps(result, sort_keys=True) + "\n")
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    usage = [r.get("usage") or {} for r in results]
    stats = summarize(results)
    set_summary = {
        "households": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "households_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "policyengine_us": manifest.get("policyengine_us"),
        "limit": limit,
        "shard": shard,
        "cases": len(results),
        "api_errors": stats["api_errors"],
        "malformed": round(stats.get("malformed", 0.0) * stats["n"]),
        "cut_off": sum(r.get("finish_reason") == "length" for r in results),
        "reasoning_tokens": sum((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0 for u in usage),
        "mean_reward": None if not stats["n"] else round(stats["reward"], 4),
        "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
        "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
        "cost_usd": round(sum(float(u.get("cost") or 0) for u in usage), 6),
        "floors": floors(rows),
    }
    summary_path = out_dir / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    summary.update({**settings, "prompt_version": prompt.PROMPT_VERSION, "prompt_hash": prompt.prompt_hash()})
    summary.setdefault("sets", {})[set_] = set_summary
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return set_summary


class MergeError(Exception):
    pass


def merge(run_id: str, parts: list[Path], *, limit: int | None = None, results_dir: Path = RESULTS_DIR,
          sets_dir: Path = SETS_DIR) -> Path:
    """Combine shard results (each part is a run directory) into one run, checking every household is there once."""
    summaries = [json.loads((p / "summary.json").read_text()) for p in parts if (p / "summary.json").is_file()]
    if not summaries:
        raise MergeError("no summary.json in any part")
    for key in ("model", "prompt_hash", "max_tokens", "reasoning_effort"):
        values = {json.dumps(s.get(key)) for s in summaries}
        if len(values) > 1:
            raise MergeError(f"parts disagree on {key}: {sorted(values)}")
    first = summaries[0]
    settings = {k: first.get(k) for k in ("model", "base_url", "max_tokens", "reasoning_effort", "model_info")
                if first.get(k) is not None}
    settings["run_id"] = run_id
    out_dir = results_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for set_ in ("id", "ood"):
        files = [p / f"{set_}.jsonl" for p in parts if (p / f"{set_}.jsonl").is_file()]
        if not files:
            continue
        results = [json.loads(line) for f in files for line in f.open()]
        path = sets_dir / set_ / "households.jsonl"
        rows = [row for _, row in select(load_set(path), limit)]
        ids = [r["id"] for r in results]
        if len(ids) != len(set(ids)):
            raise MergeError(f"{set_}: some households appear in more than one part")
        missing = sorted({row["id"] for row in rows} - set(ids))
        if missing:
            raise MergeError(f"{set_}: {len(missing)} households missing, e.g. {missing[:5]}")
        write_set(out_dir, set_, path, rows, sorted(results, key=lambda r: r["index"]), limit, settings)
    return out_dir
