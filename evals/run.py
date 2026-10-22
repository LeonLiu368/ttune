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


def evaluate(row: dict, text: str) -> dict:
    """Parse and score one reply."""
    answer, error = parse_answer(text, _names(row))
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
            "attempts": completion.attempts, **evaluate(row, completion.text)}


async def _run_all(client: ChatClient, todo: list[tuple[int, dict]], partial: Path) -> list[dict]:
    results = []
    with partial.open("a") as fh:
        for task in asyncio.as_completed([_one(client, i, row) for i, row in todo]):
            result = await task
            fh.write(json.dumps(result, sort_keys=True) + "\n")
            fh.flush()
            results.append(result)
    return results


def run(set_: str, model: str, *, run_id: str | None = None, limit: int | None = None, base_url: str | None = None,
        households: Path | None = None, resume: bool = False, concurrency: int = 8, retries: int = 5,
        results_dir: Path = RESULTS_DIR, api_key: str | None = None) -> tuple[Path, dict]:
    """Run one set. Returns (run directory, that set's summary)."""
    path = households or SETS_DIR / set_ / "households.jsonl"
    rows = load_set(path)[:limit] if limit else load_set(path)
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
    todo = [(i, row) for i, row in enumerate(rows) if row["id"] not in done]

    async def go() -> list[dict]:
        kwargs = {"concurrency": concurrency, "retries": retries}
        if base_url:
            kwargs["base_url"] = base_url
        client = ChatClient(model, api_key=api_key, **kwargs)
        try:
            return await _run_all(client, todo, partial)
        finally:
            await client.aclose()

    new = asyncio.run(go()) if todo else []
    wanted = {row["id"] for row in rows}
    results = sorted([r for r in done.values() if r["id"] in wanted] + new, key=lambda r: r["index"])
    with final.open("w") as fh:
        for result in results:
            fh.write(json.dumps(result, sort_keys=True) + "\n")
    partial.unlink(missing_ok=True)

    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    usage = [r.get("usage") or {} for r in results]
    stats = summarize(results)
    set_summary = {
        "households": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "households_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "policyengine_us": manifest.get("policyengine_us"),
        "limit": limit,
        "cases": len(results),
        "api_errors": stats["api_errors"],
        "malformed": round(stats.get("malformed", 0.0) * stats["n"]),
        "mean_reward": None if not stats["n"] else round(stats["reward"], 4),
        "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
        "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
        "cost_usd": round(sum(float(u.get("cost") or 0) for u in usage), 6),
        "floors": floors(rows),
    }
    summary_path = out_dir / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    summary.update({"run_id": run_id, "model": model, "base_url": base_url or "https://openrouter.ai/api/v1",
                    "prompt_version": prompt.PROMPT_VERSION, "prompt_hash": prompt.prompt_hash()})
    summary.setdefault("sets", {})[set_] = set_summary
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return out_dir, set_summary
