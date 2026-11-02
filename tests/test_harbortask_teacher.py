"""Teacher trajectories: the price ceiling, the spend check, the SFT export and an aggregate-only summary."""

import json
from pathlib import Path

import pytest

from harbortask import teacher

PRICES = {"input": 0.1e-6, "output": 0.5e-6, "request": 0.0}


def trial(jobs: Path, task: str, *, reward: float | None, tokens=(100_000, 5_000), messages=None,
          exception: str | None = None, summarized: int = 0) -> None:
    d = jobs / task / "job" / f"{task}__x"
    d.mkdir(parents=True)
    if messages is None:
        messages = [{"role": "user", "content": "instruction"},
                    {"role": "assistant", "content": '{"commands": [{"keystrokes": "benefits-calc household.json\\n"}]}'},
                    {"role": "user", "content": "output"},
                    {"role": "assistant", "content": '{"task_complete": true}'}]
    (d / "result.json").write_text(json.dumps({
        "task_name": f"ttune/{task}", "trial_name": f"{task}__x", "finished_at": "2026-11-02T00:00:00+00:00",
        "agent_result": {"n_input_tokens": tokens[0], "n_output_tokens": tokens[1],
                         "metadata": {"n_episodes": 4, "summarization_count": summarized, "all_messages": messages}},
        "verifier_result": None if reward is None else {"rewards": {"reward": reward, "eligibility": reward,
                                                                    "amount": reward, "missing_info": 1.0}},
        "exception_info": {"exception_type": exception} if exception else None,
    }))


def test_price_refuses_unknown_and_expensive_models():
    models = [{"id": "qwen/cheap", "pricing": {"prompt": "0.0000001", "completion": "0.0000005"}},
              {"id": "big/pricey", "pricing": {"prompt": "0.000003", "completion": "0.000015"}}]
    assert teacher.price(models, "qwen/cheap") == {"input": 1e-7, "output": 5e-7, "request": 0.0}
    with pytest.raises(teacher.TeacherError, match="ceiling"):
        teacher.price(models, "big/pricey")
    with pytest.raises(teacher.TeacherError, match="doesn't list"):
        teacher.price(models, "qwen/typo")


def test_spend_check_keeps_room_for_one_more_task(tmp_path):
    trial(tmp_path, "benefits-a", reward=1.0)  # 100k in, 5k out: $0.0125
    assert teacher.spent([tmp_path], PRICES) == pytest.approx(0.0125)
    reserve = teacher.RESERVE_INPUT_TOKENS * PRICES["input"] + teacher.RESERVE_OUTPUT_TOKENS * PRICES["output"]
    assert teacher.can_start([tmp_path], PRICES, 0.0125 + reserve)[0]
    assert not teacher.can_start([tmp_path], PRICES, 0.0125 + reserve - 0.001)[0]


def test_sft_keeps_only_finished_high_reward_linear_chats(tmp_path):
    trial(tmp_path, "benefits-good", reward=1.0)
    trial(tmp_path, "benefits-low", reward=0.5)
    trial(tmp_path, "benefits-timeout", reward=1.0, exception="AgentTimeoutError")
    trial(tmp_path, "benefits-summarized", reward=1.0, summarized=1)
    trial(tmp_path, "benefits-unverified", reward=None)
    out = tmp_path / "sft.jsonl"
    assert teacher.sft([tmp_path], out) == {"kept": 1, "skipped": 4, "min_reward": teacher.SFT_MIN_REWARD}
    row = json.loads(out.read_text())
    assert row["task"] == "benefits-good" and row["messages"][-1]["role"] == "assistant"


def test_summary_is_aggregate_only(tmp_path):
    secret_answer = '{"snap": {"eligible": true, "monthly_benefit": 291}}'
    trial(tmp_path, "benefits-0123456789", reward=1.0,
          messages=[{"role": "user", "content": "Ana Lopez, 3 Elm St"},
                    {"role": "assistant", "content": f"benefits-calc household.json; echo '{secret_answer}'"}])
    trial(tmp_path, "benefits-9876543210", reward=0.0)
    text = teacher.summary([tmp_path], PRICES, "qwen/teacher")
    assert "2 training tasks" in text and "Mean task reward (of those) | 0.500" in text and "Reached the verifier | 2 of 2" in text and "Reward 1.0 | 1 (50%)" in text
    assert "Ran `benefits-calc` on a household file | 2 (100%)" in text
    for leak in ("benefits-0123456789", "benefits-9876543210", "Ana", "Elm", "291", "monthly_benefit"):
        assert leak not in text
