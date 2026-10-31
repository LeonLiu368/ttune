"""Task splits: secret-derived seeds, no overlap with the holdout, manifests without answers."""

import json
from pathlib import Path

import pytest

from harbortask import split

ROOT = Path(__file__).resolve().parents[1]


def test_one_secret_gives_stable_independent_seeds():
    assert split.seed_for("s3cret", "train") == split.seed_for("s3cret", "train")
    assert split.seed_for("s3cret", "train") != split.seed_for("s3cret", "validation")
    assert split.seed_for("s3cret", "train") != split.seed_for("other", "train")
    with pytest.raises(split.SplitError, match="TTUNE_TRAIN_SEED"):
        split.seed_for("", "train")


def test_overlap_is_caught_within_and_across_splits():
    rows = split.holdout_rows("holdout-id")[:5]
    split.check_overlap({"a": rows[:3], "b": rows[3:]})
    copy = json.loads(json.dumps(rows[1]))
    copy["id"], copy["household"]["id"] = "train-0000", "train-0000"
    copy["household"]["members"][0]["name"] = "Someone Else"  # names don't make a household different
    with pytest.raises(split.SplitError, match="same facts as holdout/id-1-0001"):
        split.check_overlap({"holdout": rows, "train": [copy]})


def test_the_published_holdout_has_no_duplicates():
    split.check_overlap({s: split.holdout_rows(s) for s in split.HOLDOUT})


def test_manifest_has_counts_and_digests_but_no_case_data_or_answers(tmp_path):
    pytest.importorskip("reportlab")
    from harbortask import audit
    from harbortask.build import build

    rows = split.holdout_rows("holdout-ood")[:4]
    dirs = [build(r, tmp_path) for r in rows]
    meta = split.manifest("holdout-ood", rows, dirs, audit.report(audit.run(rows), len(rows)))
    text = json.dumps(meta)
    assert meta["n"] == 4 and len(meta["tasks"]) == 4
    assert all(v.startswith("sha256:") for v in meta["tasks"].values())
    for row in rows:
        assert row["id"] not in text and row["household"]["members"][0]["name"] not in text
    for key in ("monthly_benefit", "annual_amount", "eligible_members", "missing_information", "household"):
        assert key not in text


def test_generated_split_end_to_end(tmp_path):
    pytest.importorskip("policyengine_us")
    pytest.importorskip("reportlab")
    meta = split.build_split("validation", tmp_path, secret="test-secret", n=12)
    seed = str(split.seed_for("test-secret", "validation"))
    files = [p for p in (tmp_path / "validation").rglob("*") if p.is_file() and p.suffix != ".pdf"]
    assert not any(seed in p.read_text() for p in files)
    rows = [json.loads(line) for line in (tmp_path / "validation" / "cases.jsonl").open()]
    assert [r["id"] for r in rows] == [f"validation-{i:04d}" for i in range(12)]
    assert all(r["household"]["seed"] == 0 for r in rows)
    assert meta["audit"]["oracle"] == 1.0 and len(meta["tasks"]) == 12
