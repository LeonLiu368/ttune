"""python -m harbortask audit | build [--samples | --set {id,ood} --ids ...] | split --split ... [--n N]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harbortask import audit, build

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "documents"
TASKS = ROOT / "tasks"


def load(set_: str) -> list[dict]:
    return [json.loads(line) for line in (DOCS / set_ / "cases.jsonl").open()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harbortask", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write Harbor task directories from document cases")
    b.add_argument("--samples", action="store_true", help="the hand-checked sample tasks committed in tasks/")
    b.add_argument("--set", choices=("id", "ood"), dest="set_")
    b.add_argument("--ids", nargs="*", default=None)
    b.add_argument("--out", type=Path, default=TASKS)
    sp = sub.add_parser("split", help="build a task split: train/validation (secret seed) or holdout-id/holdout-ood")
    sp.add_argument("--split", required=True, choices=("train", "validation", "holdout-id", "holdout-ood"))
    sp.add_argument("--n", type=int, default=None, help="households, for train and validation")
    sp.add_argument("--secret-env", default="TTUNE_TRAIN_SEED", help="environment variable holding the secret")
    sp.add_argument("--out", type=Path, default=ROOT / "build" / "splits")
    a = sub.add_parser("audit", help="score degenerate answers over every document case (writes tasks/audit.json)")
    a.add_argument("--out", type=Path, default=TASKS / "audit.json")
    args = parser.parse_args(argv)

    if args.command == "split":
        import os

        from harbortask.split import GENERATED, SplitError, build_split
        if args.split in GENERATED and not args.n:
            parser.error("--n is required for train and validation")
        try:
            meta = build_split(args.split, args.out, os.environ.get(args.secret_env, ""), args.n)
        except SplitError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({k: meta[k] for k in ("split", "n", "audit")}, indent=1))
        print(json.dumps(meta["counts"]["answer"]), f"\nwrote {len(meta['tasks'])} tasks to {args.out / args.split}")
        return 0

    if args.command == "audit":
        rows = load("id") + load("ood")
        result = audit.report(audit.run(rows), len(rows))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n")
        for name, p in result["policies"].items():
            print(f"{name:30} mean {p['mean']:.3f}  max {p['max']:.3f}  {p['dimensions']}")
        failed = [c for c in result["checks"] if c["result"] != "pass"]
        print("\n" + ("audit FAILED: " + ", ".join(c["check"] for c in failed) if failed else "audit passed"))
        return 1 if failed else 0

    audit_path = TASKS / "audit.json"
    audit_result = json.loads(audit_path.read_text()) if audit_path.is_file() else None
    if args.samples:
        rows = build.pick_samples(load("id") + load("ood"))
    elif args.set_:
        rows = load(args.set_)
        if args.ids:
            rows = [r for r in rows if r["id"] in set(args.ids)]
    else:
        parser.error("give --samples or --set")
    for row in rows:
        path = build.build(row, args.out, audit_result)
        print(f"{row['id']} -> {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
