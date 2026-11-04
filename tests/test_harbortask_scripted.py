"""Scripted demonstrations: terminus-2's shape, real outputs, no hidden facts, answers that score 1.0."""

import json
import shutil

import pytest

pytest.importorskip("policyengine_us")
pytest.importorskip("reportlab")
if not shutil.which("pdftotext"):
    pytest.skip("needs pdftotext (poppler-utils)", allow_module_level=True)

from docgen.model import Packet  # noqa: E402
from envgen.household import Household  # noqa: E402
from harbortask import build, scripted, verify  # noqa: E402
from harbortask.split import holdout_rows  # noqa: E402


def cases(n=12):
    rows = holdout_rows("holdout-id") + holdout_rows("holdout-ood")
    gaps = [r for r in rows if any(i.get("gap") for i in r["packet"]["issues"])][:4]
    plain = [r for r in rows if r not in gaps][:n - len(gaps)]
    return gaps + plain


@pytest.fixture(scope="module")
def demos(tmp_path_factory):
    out = tmp_path_factory.mktemp("sft") / "demos.jsonl"
    rows = cases()
    counts = scripted.build_all(rows, out)
    return rows, counts, [json.loads(line) for line in out.open()]


def test_every_case_passes_its_checks(demos):
    rows, counts, kept = demos
    assert counts["kept"] == len(rows) == len(kept) and counts["with a gap"] == 4


def test_conversations_have_terminus_2s_shape(demos):
    _, _, kept = demos
    for demo in kept:
        roles = [m["role"] for m in demo["messages"]]
        assert roles[0] == "user" and roles[-1] == "assistant"
        assert all(a != b for a, b in zip(roles, roles[1:])), "turns alternate"
        assert "Task Description:" in demo["messages"][0]["content"]
        assistant = [json.loads(m["content"]) for m in demo["messages"] if m["role"] == "assistant"]
        for turn in assistant:
            assert {"analysis", "plan", "commands"} <= set(turn)
            assert all(c["keystrokes"].endswith("\n") for c in turn["commands"])
        assert assistant[-1]["task_complete"] and assistant[-2]["task_complete"]
        text = json.dumps(demo)
        assert "benefits-calc /app/household.json" in text and "pdftotext -layout" in text
        # Every document is read in full.
        assert text.count("pdftotext -layout /app/case/") >= 2


def test_the_written_answer_scores_one(demos):
    rows, _, kept = demos
    by_task = {build.task_id(r["id"]): r for r in rows}
    for demo in kept:
        last = json.loads([m for m in demo["messages"] if m["role"] == "assistant"][-2]["content"])
        keys = last["commands"][0]["keystrokes"]
        body = keys.split("<< 'EOF'\n", 1)[1].rsplit("\nEOF\n", 1)[0]
        assert verify.evaluate(body, build.truth_file(by_task[demo["task"]]))["reward"] == 1.0


def test_a_missing_figure_never_reaches_the_calculator():
    for row in cases()[:4]:
        packet = Packet.from_dict(row["packet"])
        household = Household.from_dict(row["household"])
        f = scripted.facts(household, packet)
        for issue in packet.gaps:
            gap = issue.gap
            if gap["fact"] == "income":
                member = next(m for m in household.members if m.id == gap["member"])
                entry = next(m for m in f["members"] if m["name"] == member.name.split()[0])
                assert gap["source"] not in entry.get("income", {})
            else:
                assert f["expenses"][gap["fact"]] == 0


def test_the_summary_is_aggregate_only(demos):
    rows, counts, _ = demos
    text = scripted.summary({"train": counts})
    assert f"| train | {len(rows)} | {len(rows)} | 4 | 0 |" in text
    for row in rows:
        assert row["id"] not in text and row["household"]["members"][0]["name"] not in text
