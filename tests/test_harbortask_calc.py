"""benefits-calc through PolicyEngine: the household's own facts give back its stored answers. Skipped without
policyengine-us."""

import json
from pathlib import Path

import pytest

pytest.importorskip("policyengine_us")

from harbortask import build, calc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def facts(h: dict) -> dict:
    name = {m["id"]: m["name"] for m in h["members"]}
    return {"state": h["state"], "area": h["area"],
            "members": [{k: m[k] for k in ("name", "age", "relationship", "pregnant", "disabled", "student",
                                           "citizenship", "income")} for m in h["members"]],
            "expenses": {**h["expenses"], "medical": {name[k]: v for k, v in h["expenses"]["medical"].items()}}}


def test_correct_facts_give_the_stored_answers():
    rows = [json.loads(line) for line in (ROOT / "data" / "households" / "ood" / "households.jsonl").open()]
    # Rare shapes and held-out states, including Alaska and New York areas.
    rows = [r for r in rows if r["household"]["shift"] != "threshold_edge"][:12] + \
           [r for r in rows if r["household"]["state"] in ("AK", "NY")][:4]
    data = build._calc_data()
    for row in rows:
        out = calc.calculate(facts(row["household"]), data)
        t, names = row["truth"], {m["id"]: m["name"] for m in row["household"]["members"]}
        assert out["snap"] == t["snap"] and out["eitc"] == t["eitc"], row["id"]
        for program in ("medicaid", "wic"):
            assert out[program]["eligible_members"] == [names[i] for i in t[program]["eligible_members"]], row["id"]


def test_cli_prints_json_or_a_plain_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(calc, "_data", build._calc_data)
    path = tmp_path / "h.json"
    path.write_text(json.dumps(calc.EXAMPLE))
    assert calc.main([str(path)]) == 0
    assert set(json.loads(capsys.readouterr().out)) >= {"snap", "eitc", "medicaid", "wic"}
    path.write_text("{oops")
    assert calc.main([str(path)]) == 2
    assert "not valid JSON" in capsys.readouterr().err
