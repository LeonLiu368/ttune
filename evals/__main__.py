"""python -m evals run --set {id,ood} --model <slug> [--limit N] | compare <run-id> | preflight --model <slug|free>"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evals.client import FatalApiError
from evals.compare import compare
from evals.run import RESULTS_DIR, default_run_id, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run a model over a household set")
    r.add_argument("--set", choices=("id", "ood"), required=True, dest="set_")
    r.add_argument("--model", required=True, help="model slug, e.g. an OpenRouter id")
    r.add_argument("--limit", type=int, default=None, help="only the first N households")
    r.add_argument("--run-id", default=None, help="default: <UTC date-time>-<model>; reuse it for the second set")
    r.add_argument("--base-url", default=None, help="OpenAI-compatible API (default: OpenRouter)")
    r.add_argument("--households", type=Path, default=None, help="default: data/households/<set>/households.jsonl")
    r.add_argument("--concurrency", type=int, default=8)
    r.add_argument("--retries", type=int, default=5, help="tries per request (free models rate-limit hard)")
    r.add_argument("--resume", action="store_true", help="only re-run missing and failed cases")
    r.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    c = sub.add_parser("compare", help="write comparison.md for a run")
    c.add_argument("run_id")
    c.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p = sub.add_parser("preflight", help="check the model exists on OpenRouter and is free (the cost guard)")
    p.add_argument("--model", required=True, help='an OpenRouter id, or "free" for the first available free model')
    p.add_argument("--allow-paid", action="store_true", help="allow a model that costs money")
    p.add_argument("--limit", default="", help="recorded in the run id")
    p.add_argument("--github-output", type=Path, default=None, help="append model= and run_id= for later steps")
    args = parser.parse_args(argv)

    if args.command == "preflight":
        from evals.preflight import CostGuardError, choose_model, fetch_models, is_free
        try:
            model = choose_model(fetch_models(), args.model, args.allow_paid)
        except CostGuardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        free = is_free(model)
        run_id = default_run_id(model["id"]) + (f"-n{args.limit}" if args.limit else "")
        print(f"model: {model['id']} ({'free' if free else 'PAID: ' + str(model.get('pricing'))})")
        print(f"run id: {run_id}")
        if args.github_output:
            with args.github_output.open("a") as fh:
                fh.write(f"model={model['id']}\nrun_id={run_id}\nfree={str(free).lower()}\n")
        return 0

    if args.command == "compare":
        out = compare(args.results_dir / args.run_id)
        print(f"wrote {out}")
        return 0
    try:
        out_dir, s = run(args.set_, args.model, run_id=args.run_id, limit=args.limit, base_url=args.base_url,
                         households=args.households, resume=args.resume, concurrency=args.concurrency,
                         retries=args.retries, results_dir=args.results_dir)
    except FatalApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{args.set_}: {s['cases']} cases, mean reward {s['mean_reward']}, {s['malformed']} malformed, "
          f"{s['api_errors']} API errors, ${s['cost_usd']:.4f} -> {out_dir}")
    if s["api_errors"]:
        print("error: some cases got no answer; re-run with --resume", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
