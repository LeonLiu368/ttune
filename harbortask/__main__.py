"""python -m harbortask audit | build [--samples | --set {id,ood} --ids ...] | split --split ... [--n N] | agentic ..."""

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
    ag = sub.add_parser("agentic", help="the agentic baseline on the holdout tasks: pick a shard's tasks, collect trials")
    agsub = ag.add_subparsers(dest="action", required=True)
    pk = agsub.add_parser("pick", help="build this shard's holdout tasks")
    pk.add_argument("--out", type=Path, required=True)
    pk.add_argument("--limit", type=int, default=None, help="only the first N cases of each holdout set")
    pk.add_argument("--shard", default=None, help="K/N: cases whose index %% N == K, as evals run --shard")
    pk.add_argument("--split", default=None, choices=("train", "validation"),
                    help="a secret-seeded split instead of the holdout (needs the secret in --secret-env)")
    pk.add_argument("--n-cases", type=int, default=1000, help="the split's size, as built (for --split)")
    pk.add_argument("--start", type=int, default=0, help="first case index to use (for --split)")
    pk.add_argument("--secret-env", default="TTUNE_TRAIN_SEED")
    sh = agsub.add_parser("show", help="print a trial's result, answer file and agent turns")
    sh.add_argument("job_dir", type=Path)
    sc = sub.add_parser("scripted", help="scripted SFT demonstrations ($0): terminus-2 conversations from a split")
    sc.add_argument("--split", choices=("train", "validation"), default=None, help="a secret-seeded split")
    sc.add_argument("--n-cases", type=int, default=None, help="the split's size, as built (default: 1000 / 200)")
    sc.add_argument("--holdout", choices=("id", "ood"), default=None, help="public holdout cases instead (to preview)")
    sc.add_argument("--limit", type=int, default=None)
    sc.add_argument("--secret-env", default="TTUNE_TRAIN_SEED")
    sc.add_argument("--out", type=Path, required=True)
    te = sub.add_parser("teacher", help="teacher trajectories for the SFT warm-start (training split only)")
    tesub = te.add_subparsers(dest="action", required=True)
    tp = tesub.add_parser("price", help="the teacher's OpenRouter price, refusing one above the ceiling")
    tp.add_argument("--model", required=True)
    tp.add_argument("--out", type=Path, required=True, help="write the prices as JSON here")
    tc = tesub.add_parser("can-start", help="exit 0 if one more task fits in the budget, 3 if not")
    tc.add_argument("--jobs", type=Path, required=True)
    tc.add_argument("--prices", type=Path, required=True)
    tc.add_argument("--budget", type=float, required=True, help="USD for this shard")
    ts = tesub.add_parser("sft", help="the good trials as chat transcripts (JSONL)")
    ts.add_argument("--jobs", type=Path, nargs="+", required=True)
    ts.add_argument("--out", type=Path, required=True)
    ts.add_argument("--min-reward", type=float, default=None)
    tm = tesub.add_parser("summary", help="aggregate numbers only (safe to publish)")
    tm.add_argument("--jobs", type=Path, nargs="+", required=True)
    tm.add_argument("--prices", type=Path, required=True)
    tm.add_argument("--model", required=True)
    tm.add_argument("--out", type=Path, required=True)
    co = agsub.add_parser("collect", help="score Harbor's trials into an evals run (evals/results/<run id>)")
    co.add_argument("run_id")
    co.add_argument("--jobs", type=Path, nargs="+", required=True, help="Harbor jobs directories, one or more per shard")
    co.add_argument("--model", required=True)
    co.add_argument("--limit", type=int, default=None, help="the --limit the shards used")
    co.add_argument("--base-url", default=None)
    co.add_argument("--model-info", type=Path, default=None, help="JSON describing a self-hosted model")
    co.add_argument("--max-turns", type=int, default=None)
    co.add_argument("--agent-timeout-sec", type=float, default=None)
    co.add_argument("--temperature", type=float, default=None)
    co.add_argument("--compare-to", default=None, help="a one-shot run on the same households, for comparison.md")
    args = parser.parse_args(argv)

    if args.command == "scripted":
        import os
        from harbortask import scripted
        if bool(args.split) == bool(args.holdout):
            parser.error("give --split or --holdout")
        if args.split:
            n = args.n_cases or {"train": 1000, "validation": 200}[args.split]
            rows = scripted.generated_cases(args.split, n, os.environ.get(args.secret_env, ""))
        else:
            rows = load(args.holdout)
        rows = rows[:args.limit] if args.limit else rows
        counts = scripted.build_all(rows, args.out)
        print(json.dumps(counts))
        return 0 if counts.get("kept") else 1

    if args.command == "teacher":
        from harbortask import teacher
        try:
            if args.action == "price":
                from evals.preflight import fetch_models
                prices = teacher.price(fetch_models(), args.model)
                args.out.write_text(json.dumps(prices) + "\n")
                print(f"{args.model}: {prices['input'] * 1e6:.3f} / {prices['output'] * 1e6:.3f} USD per million "
                      "input / output tokens")
                return 0
            if args.action == "can-start":
                ok, so_far = teacher.can_start([args.jobs], json.loads(args.prices.read_text()), args.budget)
                print(f"spent ${so_far:.3f} of ${args.budget:.2f}")
                return 0 if ok else 3
            if args.action == "sft":
                kw = {} if args.min_reward is None else {"min_reward": args.min_reward}
                print(json.dumps(teacher.sft(args.jobs, args.out, **kw)))
                return 0
            text = teacher.summary(args.jobs, json.loads(args.prices.read_text()), args.model)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text)
            print(text)
            return 0
        except teacher.TeacherError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if args.command == "agentic":
        from harbortask import agentic
        if args.action == "pick":
            from evals.__main__ import _shard
            if args.split:
                import os
                paths = agentic.pick_generated(args.out, args.split, args.n_cases, os.environ.get(args.secret_env, ""),
                                               args.start, args.limit, _shard(args.shard))
            else:
                paths = agentic.pick(args.out, args.limit, _shard(args.shard))
            for path in paths:
                print(path.name)
            return 0
        if args.action == "show":
            print(agentic.show(args.job_dir))
            return 0
        info = json.loads(args.model_info.read_text()) if args.model_info and args.model_info.is_file() else None
        harness = {k: v for k, v in (("max_turns", args.max_turns), ("agent_timeout_sec", args.agent_timeout_sec),
                                     ("temperature", args.temperature)) if v is not None}
        try:
            out = agentic.collect(args.run_id, args.jobs, model=args.model, limit=args.limit, harness=harness,
                                  model_info=info, compare_to=args.compare_to, base_url=args.base_url)
        except agentic.CollectError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        summary = json.loads((out / "summary.json").read_text())
        for set_, s in summary["sets"].items():
            print(set_, {k: s[k] for k in ("cases", "mean_reward", "malformed", "api_errors")}, s["agent"])
        return 0

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
