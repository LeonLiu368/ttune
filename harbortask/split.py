"""Task splits: generated train and validation sets, and the published holdout sets.

Train and validation are fresh typical (ID-style) households from envgen, seeded from a secret so only the owner can
regenerate their answers. Holdout is the 200 + 200 published document cases (data/documents), never trained on.
Generated cases are renamed train-0001, validation-0001, ... and their seed blanked, so nothing written reveals the
seed. Only the manifest (counts, audit, task digests: no case data, no answers) is meant to be committed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ("train", "validation")
HOLDOUT = {"holdout-id": "id", "holdout-ood": "ood"}
SPLITS = (*GENERATED, *HOLDOUT)
PROGRAMS = ("snap", "eitc", "wic", "medicaid")


class SplitError(Exception):
    pass


def seed_for(secret: str, split: str) -> int:
    """One secret gives an independent seed per split."""
    if not secret:
        raise SplitError("no secret: set TTUNE_TRAIN_SEED to any long random string")
    return int(hashlib.sha256(f"{secret}:{split}".encode()).hexdigest(), 16) % 2**31


def fingerprint(household: dict) -> str:
    """The facts that make a household what it is, ignoring ids and names. Used to rule out overlaps."""
    members = [(m["age"], m["relationship"], m["pregnant"], m["disabled"], m["student"], m["citizenship"],
                sorted(m["income"].items())) for m in household["members"]]
    e = household["expenses"]
    facts = [household["state"], household.get("county"), members, e["rent"], e["heating_cooling"], e["childcare"],
             sorted(e["medical"].values())]
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()


def generated_rows(split: str, n: int, secret: str) -> list[dict]:
    """Households, PolicyEngine truth and document packets for a generated split, renamed and seed-free."""
    from docgen.__main__ import build as build_documents
    from envgen.__main__ import build as build_households

    households, truths = build_households("id", n, seed_for(secret, split))
    rows = []
    for i, (h, t) in enumerate(zip(households, truths)):
        h.id, h.seed = f"{split}-{i:04d}", 0
        rows.append({"id": h.id, "household": h.to_dict(), "truth": t})
    return build_documents(rows)


def holdout_rows(split: str) -> list[dict]:
    path = ROOT / "data" / "documents" / HOLDOUT[split] / "cases.jsonl"
    return [json.loads(line) for line in path.open()]


def check_overlap(rows_by_split: dict[str, list[dict]]) -> None:
    """No household may appear twice, within or across splits: a train case must never be a holdout case."""
    seen: dict[str, str] = {}
    for split, rows in rows_by_split.items():
        for row in rows:
            key = fingerprint(row["household"])
            if key in seen:
                raise SplitError(f"{split}/{row['id']} has the same facts as {seen[key]}")
            seen[key] = f"{split}/{row['id']}"


def _dir_digest(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(path)).encode() + b"\0" + f.read_bytes() + b"\0")
    return "sha256:" + h.hexdigest()


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def manifest(split: str, rows: list[dict], task_dirs: list[Path], audit_result: dict) -> dict:
    from docgen import truth as doc_truth
    from harbortask.build import POLICYENGINE_US

    def counts(values) -> dict:
        return dict(sorted(Counter(values).items()))

    return {
        "split": split, "n": len(rows),
        "source": "generated (secret seed)" if split in GENERATED else f"data/documents/{HOLDOUT[split]}/cases.jsonl",
        "policyengine_us": POLICYENGINE_US, "generator_commit": _commit(),
        "counts": {
            "state": counts(r["household"]["state"] for r in rows),
            "size": counts(str(len(r["household"]["members"])) for r in rows),
            "shift": counts(r["household"]["shift"] for r in rows),
            "issue": counts(i["kind"] for r in rows for i in r["packet"]["issues"]),
            "packets_with_gap": sum(any(i["gap"] for i in r["packet"]["issues"]) for r in rows),
            "answer": {p: counts(doc_truth.eligible(r["truth"], p) for r in rows) for p in PROGRAMS},
        },
        "audit": {k: v["mean"] for k, v in audit_result["policies"].items()},
        "tasks": {d.name: _dir_digest(d) for d in sorted(task_dirs)},
    }


def build_split(split: str, out: Path, secret: str | None = None, n: int | None = None,
                avoid: list[dict] | None = None) -> dict:
    """Write out/<split>/<task-id>/ for every case, plus the private cases.jsonl; return the manifest."""
    from harbortask import audit
    from harbortask.build import build

    if split not in SPLITS:
        raise SplitError(f"unknown split {split!r}; choose from {', '.join(SPLITS)}")
    from docgen import truth as doc_truth

    if split in GENERATED:
        rows = generated_rows(split, n, secret)
        holdout = avoid if avoid is not None else holdout_rows("holdout-id") + holdout_rows("holdout-ood")
        check_overlap({split: rows, "holdout": holdout})
    else:
        rows = holdout_rows(split)
        check_overlap({split: rows})
    for program in PROGRAMS:  # as envgen's balance check: a split with one answer can't train or measure it
        if len({doc_truth.eligible(r["truth"], program) for r in rows}) < 2:
            raise SplitError(f"{split}: every case has the same {program} answer")
    audit_result = audit.report(audit.run(rows), len(rows))
    if any(c["result"] != "pass" for c in audit_result["checks"]):
        raise SplitError(f"{split}: reward-hack audit failed: {audit_result['checks']}")
    target = out / split
    target.mkdir(parents=True, exist_ok=True)
    with (target / "cases.jsonl").open("w") as fh:  # private: answers included
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    dirs = [build(row, target, audit_result) for row in rows]
    meta = manifest(split, rows, dirs, audit_result)
    (target / "manifest.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    return meta
