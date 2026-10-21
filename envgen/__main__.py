"""python -m envgen generate --set {id,ood} --n 200 --seed 1"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from envgen.describe import describe
from envgen.household import SETS
from envgen.sample import sample

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("snap", "eitc", "wic", "medicaid")
MAX_ATTEMPTS = 10


class GenerateError(Exception):
    pass


def build(set_: str, n: int, seed: int) -> tuple[list, list[dict]]:
    """Households (threshold edges placed) and their PolicyEngine truth."""
    from envgen import edges, truth

    households = [sample(set_, seed, i) for i in range(n)]
    pending = [i for i, h in enumerate(households) if h.shift == "threshold_edge"]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not pending:
            break
        placed = edges.place([households[i] for i in pending])
        missing = []
        for i, moved in zip(pending, placed):
            if moved is None:
                missing.append(i)
                households[i] = sample(set_, seed, i, attempt)
            else:
                households[i] = moved
        pending = missing
    if pending:
        raise GenerateError(f"no cutoff found for {len(pending)} threshold-edge households after {MAX_ATTEMPTS} tries")

    truths = truth.compute(households)
    for h, t in zip(households, truths):
        if h.shift == "threshold_edge":
            program, target = h.edge["program"], h.edge.get("target")
            yes = target in t["medicaid"]["eligible_members"] if program == "medicaid" else t[program]["eligible"]
            if yes != (h.edge["side"] == "below"):
                raise GenerateError(f"{h.id}: {program} answer doesn't match its side of the cutoff: {h.edge}")
    return households, truths


def manifest(set_: str, n: int, seed: int, households: list, truths: list[dict]) -> dict:
    from envgen import truth

    def counts(values) -> dict:
        return dict(sorted(Counter(values).items()))

    return {
        "set": set_, "n": n, "seed": seed,
        "policyengine_us": truth.version(),
        "periods": {k: str(v) for k, v in truth.PERIODS.items()},
        "inputs_year": truth.YEAR,
        "poverty_guidelines": "data/processed/hhs-poverty-guidelines.csv (HHS 2026)",
        "counts": {
            "state": counts(h.state for h in households),
            "size": counts(str(h.size) for h in households),
            "shift": counts(h.shift for h in households),
            "twist": counts(t for h in households for t in h.twists),
            "eligible": {p: {"yes": sum(truth.eligible(t, p) for t in truths),
                             "no": sum(not truth.eligible(t, p) for t in truths)} for p in PROGRAMS},
        },
    }


def write(out_dir: Path, households: list, truths: list[dict], meta: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "households.jsonl").open("w") as fh:
        for h, t in zip(households, truths):
            line = {"id": h.id, "household": h.to_dict(), "case": describe(h), "truth": t}
            fh.write(json.dumps(line, sort_keys=True) + "\n")
    (out_dir / "manifest.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def balance_report(meta: dict) -> tuple[str, bool]:
    lines = [f"{meta['set']} set: {meta['n']} households, seed {meta['seed']}, policyengine-us {meta['policyengine_us']}",
             "", f"{'program':10} {'eligible':>9} {'not':>5}"]
    ok = True
    for program, c in meta["counts"]["eligible"].items():
        flag = ""
        if c["yes"] == 0 or c["no"] == 0:
            ok, flag = False, "  <- all one answer"
        lines.append(f"{program:10} {c['yes']:>9} {c['no']:>5}{flag}")
    lines += ["", "shift: " + ", ".join(f"{k} {v}" for k, v in meta["counts"]["shift"].items())]
    if meta["counts"]["twist"]:
        lines.append("twist: " + ", ".join(f"{k} {v}" for k, v in meta["counts"]["twist"].items()))
    lines.append(f"states: {len(meta['counts']['state'])}, sizes: " +
                 ", ".join(f"{k}: {v}" for k, v in sorted(meta["counts"]["size"].items(), key=lambda kv: int(kv[0]))))
    return "\n".join(lines), ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m envgen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="write a household set with PolicyEngine truth")
    gen.add_argument("--set", choices=SETS, required=True, dest="set_")
    gen.add_argument("--n", type=int, default=200)
    gen.add_argument("--seed", type=int, default=1)
    gen.add_argument("--out", type=Path, default=None, help="default: data/households/<set>")
    args = parser.parse_args(argv)

    households, truths = build(args.set_, args.n, args.seed)
    meta = manifest(args.set_, args.n, args.seed, households, truths)
    out = args.out or ROOT / "data" / "households" / args.set_
    write(out, households, truths, meta)
    report, ok = balance_report(meta)
    print(report)
    print(f"\nwrote {out / 'households.jsonl'} and manifest.json")
    if not ok:
        print("error: a program has only one answer across the set; the set can't measure it", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
