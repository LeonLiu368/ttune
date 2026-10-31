"""Harbor tasks: the generator, the verifier's scoring, the calculator's input checks and the reward-hack audit."""

import filecmp
import json
from pathlib import Path

import pytest

from harbortask import audit, build, calc, verify

ROOT = Path(__file__).resolve().parents[1]
ROWS = [json.loads(line) for s in ("id", "ood") for line in (ROOT / "data" / "documents" / s / "cases.jsonl").open()]
BY_ID = {r["id"]: r for r in ROWS}


def truth_with_gap():
    row = next(r for r in ROWS if any(i["kind"] == "missing_income_doc" for i in r["packet"]["issues"]))
    return build.truth_file(row)


# --- scoring ----------------------------------------------------------------------------------------

def test_the_reference_answer_scores_one_on_every_case():
    for row in ROWS:
        truth = build.truth_file(row)
        assert verify.evaluate(json.dumps(verify.oracle(truth)), truth)["reward"] == 1.0, row["id"]


def test_missing_information_needs_the_right_document_and_member():
    truth = truth_with_gap()
    item = truth["missing_information"][0]
    names = truth["names"]
    full_name = item["member"] + " Somebody"
    assert verify.missing_info_score([item], truth["missing_information"], names) == 1.0
    assert verify.missing_info_score([{**item, "member": full_name}], truth["missing_information"], names) == 1.0
    assert verify.missing_info_score([], truth["missing_information"], names) == 0.0
    other = next(n for n in names.values() if n != item["member"]) if len(names) > 1 else "Nobody"
    assert verify.missing_info_score([{**item, "member": other}], truth["missing_information"], names) == 0.0
    # Each wrong flag costs 0.25, and repeating the right one doesn't pay twice.
    extra = [item, item, {"document": "lease_rent_page", "member": None}]
    assert verify.missing_info_score(extra, truth["missing_information"], names) == 0.75
    assert verify.missing_info_score([{"document": "tax_return"}], [], names) == 0.75


def test_unreadable_answers_score_zero_everywhere():
    truth = truth_with_gap()
    for text in (None, "", "{not json", json.dumps({"snap": {}}),
                 json.dumps({**verify.oracle(truth), "missing_information": "pay stubs"})):
        assert verify.evaluate(text, truth)["reward"] == 0.0


def test_categories_cover_every_gap_docgen_can_make():
    for row in ROWS:
        for item in build.truth_file(row)["missing_information"]:
            assert item["document"] in verify.CATEGORIES
            assert (item["member"] is None) == (item["document"] not in verify.PER_MEMBER)


def test_degenerate_answers_stay_well_below_the_reference():
    result = audit.report(audit.run(ROWS), len(ROWS))
    p = result["policies"]
    assert p["oracle"]["mean"] == 1.0
    assert p["empty"]["max"] == p["malformed"]["max"] == 0.0
    for name, stats in p.items():
        if name != "oracle":
            assert stats["mean"] < 0.4, (name, stats)
    assert p["all unknown, flag everything"]["mean"] < 0.15
    assert all(c["result"] == "pass" for c in result["checks"])


# --- the generator ------------------------------------------------------------------------------------

def tree(path: Path) -> list[str]:
    return sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())


def test_committed_tasks_are_what_the_generator_writes(tmp_path):
    pytest.importorskip("reportlab")
    audit_result = json.loads((ROOT / "tasks" / "audit.json").read_text())
    for row in build.pick_samples(ROWS):
        fresh = build.build(row, tmp_path, audit_result)
        committed = ROOT / "tasks" / fresh.name
        assert tree(fresh) == tree(committed), fresh.name
        for name in tree(fresh):
            assert filecmp.cmp(fresh / name, committed / name, shallow=False), f"{fresh.name}/{name}"


def test_the_agents_image_has_no_answers_and_no_case_id():
    for task in sorted((ROOT / "tasks").glob("benefits-*")):
        config = (task / "task.toml").read_text()
        case_id = next(line.split('"')[1] for line in config.splitlines() if line.startswith("source_case"))
        files = tree(task / "environment")
        assert not [f for f in files if f.endswith(".json") and not f.endswith("calc/data.json")], files
        assert not any(f.startswith(("tests", "solution")) for f in files)
        for name in files:
            if not name.endswith(".pdf"):
                assert case_id not in (task / "environment" / name).read_text(), name
        assert case_id not in (task / "instruction.md").read_text()
        assert "verify" not in " ".join(files) and "truth.json" not in " ".join(files)


def test_task_config_uses_a_separate_offline_verifier_and_a_non_root_agent():
    import tomllib

    for task in sorted((ROOT / "tasks").glob("benefits-*")):
        config = tomllib.loads((task / "task.toml").read_text())
        assert config["artifacts"] == ["/app/answer.json"]
        assert config["verifier"]["environment_mode"] == "separate"
        assert config["environment"]["network_mode"] == config["verifier"]["environment"]["network_mode"] == "no-network"
        assert config["agent"]["user"] == "caseworker"
        assert (task / "tests" / "Dockerfile").is_file() and (task / "tests" / "truth.json").is_file()
        assert (task / "solution" / "solve.sh").stat().st_mode & 0o111


def test_instruction_states_the_rules_the_tools_and_every_category():
    text = (sorted((ROOT / "tasks").glob("benefits-*"))[0] / "instruction.md").read_text()
    assert "two most recent pay stubs" in text and "benefits-calc" in text and "pdftotext" in text
    for category in verify.CATEGORIES:
        assert f"`{category}`" in text


def test_task_ids_are_stable_and_opaque():
    assert build.task_id("id-1-0001") == build.task_id("id-1-0001") != build.task_id("id-1-0002")
    assert "0001" not in build.task_id("id-1-0001")


# --- the calculator's input checks (PolicyEngine itself: test_harbortask_calc.py) ---------------------------

DATA = build._calc_data()


def test_calculator_reads_the_documents_vocabulary():
    h = calc.to_household({**calc.EXAMPLE, "state": "Ohio",
                           "expenses": {"rent": 900, "heating_cooling": True, "medical": {"Ana": 40}}}, DATA)
    assert h.state == "OH" and h.member("p1").income == {"wages": 1800} and h.expenses.medical == {"p1": 40}
    ny = calc.to_household({**calc.EXAMPLE, "state": "NY", "area": "Brooklyn"}, DATA)
    assert ny.county == "KINGS_COUNTY_NY"


@pytest.mark.parametrize("facts, message", [
    ({**calc.EXAMPLE, "state": "Atlantis"}, "unknown state"),
    ({**calc.EXAMPLE, "state": "NY", "area": "New York City"}, "needs \"area\""),
    ({**calc.EXAMPLE, "members": []}, "non-empty list"),
    ({**calc.EXAMPLE, "members": [{"name": "Leo", "age": 3, "relationship": "child"}]}, "head of household"),
    ({**calc.EXAMPLE, "members": [{"name": "Ana", "age": 30, "income": {"lottery": 5}}]}, "unknown income types"),
    ({**calc.EXAMPLE, "expenses": {"medical": {"Zed": 10}}}, "isn't a member"),
])
def test_calculator_input_errors_are_plain_messages(facts, message):
    with pytest.raises(calc.InputError, match=message):
        calc.to_household(facts, DATA)
