"""Teacher trajectories for the SFT warm-start: a stronger open model drives terminus-2 through the training tasks.

The teacher runs only on the secret training split, never the holdout. Its trajectories reveal the training answers,
so they stay in the workflow's encrypted artifact; the repository gets only `summary` (aggregate numbers).

- `price`: the teacher's per-token price from OpenRouter, refusing a model that costs more than a ceiling.
- `spent`: what a run has cost so far, from each trial's token counts and those prices (cache reads priced as input,
  so the figure errs high). The workflow checks it before every task and stops at the budget.
- `sft`: the trials worth learning from, as chat transcripts ready for supervised fine-tuning.
- `summary`: what the teacher did, in aggregate.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from harbortask.agentic import trials

# Refuse a teacher above these prices (USD per million tokens): a typo in the model id shouldn't cost real money.
MAX_INPUT_PER_M = 1.0
MAX_OUTPUT_PER_M = 4.0
# Before starting a task, keep this many tokens' worth of budget in hand: about the most one task can use
# (40 turns of a growing conversation).
RESERVE_INPUT_TOKENS = 1_500_000
RESERVE_OUTPUT_TOKENS = 60_000
SFT_MIN_REWARD = 0.9


class TeacherError(Exception):
    pass


def price(models: list[dict], model_id: str) -> dict:
    """{"input": USD per token, "output": USD per token} for a paid model, within the ceiling."""
    by_id = {m["id"]: m for m in models}
    if model_id not in by_id:
        near = sorted(m for m in by_id if model_id.split("/")[-1].split("-")[0] in m)[:12]
        raise TeacherError(f"OpenRouter doesn't list {model_id!r}; similar ids: {', '.join(near) or 'none'}")
    p = by_id[model_id].get("pricing") or {}
    out = {"input": float(p.get("prompt") or 0), "output": float(p.get("completion") or 0),
           "request": float(p.get("request") or 0)}
    if out["input"] * 1e6 > MAX_INPUT_PER_M or out["output"] * 1e6 > MAX_OUTPUT_PER_M or out["request"]:
        raise TeacherError(f"{model_id} costs {out['input'] * 1e6:.3f}/{out['output'] * 1e6:.3f} USD per million "
                           f"input/output tokens (request fee {out['request']}); the ceiling is "
                           f"{MAX_INPUT_PER_M}/{MAX_OUTPUT_PER_M}")
    return out


def cost(result: dict, prices: dict) -> float:
    agent = result.get("agent_result") or {}
    return (agent.get("n_input_tokens") or 0) * prices["input"] + (agent.get("n_output_tokens") or 0) * prices["output"]


def spent(jobs: list[Path], prices: dict) -> float:
    return sum(cost(result, prices) for result, _ in trials(jobs).values())


def can_start(jobs: list[Path], prices: dict, budget: float) -> tuple[bool, float]:
    """Whether one more task fits in the budget, with room for the most a task can cost; and the spend so far."""
    so_far = spent(jobs, prices)
    reserve = RESERVE_INPUT_TOKENS * prices["input"] + RESERVE_OUTPUT_TOKENS * prices["output"]
    return so_far + reserve <= budget, so_far


def _reward(result: dict) -> float | None:
    return ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")


def _messages(result: dict) -> list[dict]:
    return ((result.get("agent_result") or {}).get("metadata") or {}).get("all_messages") or []


def _used_calculator(messages: list[dict]) -> bool:
    return any(m.get("role") == "assistant" and "benefits-calc" in str(m.get("content")) and
               "household" in str(m.get("content")) for m in messages)


def sft(jobs: list[Path], out: Path, min_reward: float = SFT_MIN_REWARD) -> dict:
    """Write the good trials as {"messages": [...], "task", "reward"} lines. Returns counts."""
    kept = skipped = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for task, (result, _) in sorted(trials(jobs).items()):
            reward, messages = _reward(result), _messages(result)
            exc = (result.get("exception_info") or {}).get("exception_type")
            summarized = ((result.get("agent_result") or {}).get("metadata") or {}).get("summarization_count")
            # A summarized conversation isn't one linear chat, and a timed-out one never finished.
            if reward is None or reward < min_reward or not messages or exc or summarized:
                skipped += 1
                continue
            if messages[-1].get("role") != "assistant":
                skipped += 1
                continue
            fh.write(json.dumps({"task": task, "reward": reward, "messages": messages}) + "\n")
            kept += 1
    return {"kept": kept, "skipped": skipped, "min_reward": min_reward}


def summary(jobs: list[Path], prices: dict, model: str, min_reward: float = SFT_MIN_REWARD) -> str:
    """What the teacher did, in aggregate only: no task ids, answers or household facts."""
    found = list(trials(jobs).values())
    rewards = [r for r in (_reward(res) for res, _ in found) if r is not None]
    agent = [res.get("agent_result") or {} for res, _ in found]
    turns = [(a.get("metadata") or {}).get("n_episodes") for a in agent]
    exceptions = Counter((res.get("exception_info") or {}).get("exception_type") or "none" for res, _ in found)
    calc = sum(_used_calculator(_messages(res)) for res, _ in found)
    total = sum(cost(res, prices) for res, _ in found)
    dims = Counter()
    for res, _ in found:
        for k, v in ((res.get("verifier_result") or {}).get("rewards") or {}).items():
            dims[k] += v
    n = len(found)

    def pct(k: int) -> str:
        return f"{100 * k / n:.0f}%" if n else "–"

    lines = [
        f"# Teacher trajectories: `{model}`", "",
        f"{n} training tasks · cost ${total:.2f} (from token counts at "
        f"${prices['input'] * 1e6:.3f} / ${prices['output'] * 1e6:.3f} per million input / output tokens)", "",
        "| | |", "|---|---|",
        f"| Reached the verifier | {len(rewards)} of {n} |",
        f"| Mean task reward (of those) | {statistics.mean(rewards):.3f} |" if rewards else "| Mean task reward | – |",
        f"| Reward ≥ {min_reward} (kept for SFT) | {sum(r >= min_reward for r in rewards)} ({pct(sum(r >= min_reward for r in rewards))}) |",
        f"| Reward 1.0 | {sum(r == 1.0 for r in rewards)} ({pct(sum(r == 1.0 for r in rewards))}) |",
        f"| Reward 0 | {sum(r == 0 for r in rewards)} ({pct(sum(r == 0 for r in rewards))}) |",
        f"| Ran `benefits-calc` on a household file | {calc} ({pct(calc)}) |",
        f"| Median turns | {statistics.median([t for t in turns if t is not None]) if any(t is not None for t in turns) else '–'} |",
        f"| Exceptions | {', '.join(f'{k} {v}' for k, v in exceptions.most_common())} |",
    ]
    if n:
        lines += ["", "Mean of each reward dimension: " +
                  ", ".join(f"{k} {v / n:.3f}" for k, v in sorted(dims.items()) if k != "reward")]
    return "\n".join(lines) + "\n"
