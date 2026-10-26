"""The JSON the viewer reads. The static build writes these files; the server returns the same thing per request.

  data/runs.json                       every run, newest first, with headline numbers
  data/runs/<run>/overview.json        settings, per-set and per-program metrics, OOD families and twists
  data/runs/<run>/<set>.json           one light row per household, for the case table
  data/runs/<run>/cases/<case>.json    one household in full: case text, reply, answer, truth, scoring
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from evals.answer import PROGRAMS
from evals.compare import FAMILY_NAMES, PROGRAM_NAMES
from evals.metrics import bootstrap_change, mean_reward, program_balanced_accuracy, scored, summarize

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evals" / "results"
SETS_DIR = ROOT / "data" / "households"
SETS = ("id", "ood")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe(name: str) -> bool:
    """Run and case ids come from URLs; only plain names are ever turned into paths."""
    return bool(SAFE_ID.match(name)) and ".." not in name


def load_results(run_dir: Path, set_: str) -> list[dict]:
    path = run_dir / f"{set_}.jsonl"
    return [json.loads(line) for line in path.open()] if path.is_file() else []


def load_households(sets_dir: Path, set_: str) -> dict[str, dict]:
    path = sets_dir / set_ / "households.jsonl"
    return {row["id"]: row for row in map(json.loads, path.open())} if path.is_file() else {}


def run_dirs(results_dir: Path) -> list[Path]:
    dirs = [p for p in results_dir.iterdir() if p.is_dir() and (p / "summary.json").is_file() and safe(p.name)] \
        if results_dir.is_dir() else []
    return sorted(dirs, key=lambda p: p.name, reverse=True)  # run ids start with the UTC date and time


def _false_denial_rate(rows: list[dict]) -> float | None:
    details = [d for r in scored(rows) for d in r["score"]["programs"].values()]
    eligible = sum(d["truly_eligible"] for d in details)
    return sum(d["false_denials"] for d in details) / eligible if eligible else None


def _headline(rows: list[dict]) -> dict:
    s = summarize(rows)
    if not s["n"]:
        return {"n": 0, "api_errors": s["api_errors"]}
    return {"n": s["n"], "api_errors": s["api_errors"], "reward": s["reward"], "malformed": s["malformed"],
            "false_denial_rate": _false_denial_rate(rows)}


def runs_index(results_dir: Path = RESULTS_DIR) -> list[dict]:
    runs = []
    for run_dir in run_dirs(results_dir):
        summary = json.loads((run_dir / "summary.json").read_text())
        info = summary.get("model_info") or {}
        runs.append({
            "run_id": run_dir.name,
            "model": summary.get("model"),
            "hosted": "self-hosted" if info else "API",
            "parameters": info.get("parameters"),
            "license": info.get("license"),
            "prompt_version": summary.get("prompt_version"),
            "max_tokens": summary.get("max_tokens"),
            "cost_usd": round(sum((s.get("cost_usd") or 0) for s in summary.get("sets", {}).values()), 6),
            "limit": next((s.get("limit") for s in summary.get("sets", {}).values()), None),
            "sets": {set_: _headline(load_results(run_dir, set_)) for set_ in SETS if (run_dir / f"{set_}.jsonl").is_file()},
        })
    return runs


def _group(label: str, key: str, rows: list[dict]) -> dict:
    s = summarize(rows)
    group = {"key": key, "label": label, "n": s["n"]}
    if s["n"]:
        group.update({"reward": s["reward"], "malformed": s["malformed"], "false_denial_rate": _false_denial_rate(rows),
                      "balanced_accuracy": {p: s["programs"][p]["balanced_accuracy"] for p in PROGRAMS}})
    return group


def _change(result) -> dict | None:
    if result is None:
        return None
    d, low, high = result
    return {"change": d, "low": low, "high": high}


def run_overview(run_dir: Path) -> dict:
    summary = json.loads((run_dir / "summary.json").read_text())
    rows = {set_: load_results(run_dir, set_) for set_ in SETS}
    families: dict[str, list] = defaultdict(list)
    twists: dict[str, list] = defaultdict(list)
    for r in rows["ood"]:
        families[r["shift"]].append(r)
        for t in r["twists"]:
            twists[t].append(r)
    both = rows["id"] and rows["ood"]
    return {
        "run_id": run_dir.name,
        "settings": {k: v for k, v in summary.items() if k != "sets"},
        "set_info": summary.get("sets", {}),
        "sets": {set_: summarize(rows[set_]) for set_ in SETS if rows[set_]},
        "headline": {set_: _headline(rows[set_]) for set_ in SETS if rows[set_]},
        "programs": [{"key": p, "label": PROGRAM_NAMES[p]} for p in PROGRAMS],
        "changes": {
            "reward": _change(bootstrap_change(rows["id"], rows["ood"], mean_reward)) if both else None,
            "balanced_accuracy": {p: _change(bootstrap_change(rows["id"], rows["ood"], program_balanced_accuracy(p)))
                                  for p in PROGRAMS} if both else None,
        },
        "families": [_group("ID (reference)", "id", rows["id"])] +
                    [_group(FAMILY_NAMES[f], f, families[f]) for f in FAMILY_NAMES if f in families],
        "twists": [_group(t, t, twists[t]) for t in sorted(twists)],
    }


def _false_denials(result: dict) -> int:
    return sum(d["false_denials"] for d in result["score"]["programs"].values()) if result["status"] == "ok" else 0


def case_rows(run_dir: Path, set_: str) -> list[dict]:
    """One light row per household for the case table."""
    rows = []
    for r in load_results(run_dir, set_):
        ok = r["status"] == "ok"
        rows.append({
            "id": r["id"], "index": r["index"], "set": set_, "shift": r["shift"], "twists": r["twists"],
            "status": r["status"], "reward": r["score"]["reward"] if ok else None,
            "malformed": ok and r["score"]["malformed"], "cut_off": r.get("finish_reason") == "length",
            "false_denials": _false_denials(r),
        })
    return rows


def case_detail(run_dir: Path, case_id: str, sets_dir: Path = SETS_DIR) -> dict | None:
    """One household in full, joined with its case text and PolicyEngine's answer."""
    set_ = case_id.split("-", 1)[0]
    if set_ not in SETS:
        return None
    result = next((r for r in load_results(run_dir, set_) if r["id"] == case_id), None)
    if result is None:
        return None
    household = load_households(sets_dir, set_).get(case_id, {})
    members = [{k: m[k] for k in ("id", "name", "age", "relationship")} for m in household.get("household", {}).get("members", [])]
    return {**result, "set": set_, "case": household.get("case"), "truth": household.get("truth"), "members": members,
            "state": household.get("household", {}).get("state"), "edge": household.get("household", {}).get("edge")}
