"""python -m evals run --set {id,ood} --model <slug> [--limit N] | compare <run-id> | preflight --model <slug|free>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evals.client import FatalApiError
from evals.compare import compare
from evals.run import RESULTS_DIR, MergeError, default_run_id, merge, run


def _shard(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    k, n = (int(x) for x in text.split("/"))
    if not 0 <= k < n:
        raise SystemExit(f"error: --shard {text}: need 0 <= K < N")
    return k, n


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
    r.add_argument("--max-tokens", type=int, default=8000, help="reply length cap, reasoning included")
    r.add_argument("--timeout", type=float, default=180.0, help="seconds per request (raise it for CPU-hosted models)")
    r.add_argument("--shard", default=None, help="K/N: run households whose index % N == K (for parallel jobs)")
    r.add_argument("--model-info", type=Path, default=None, help="JSON describing a self-hosted model, kept in summary.json")
    r.add_argument("--reasoning-effort", choices=("none", "minimal", "low", "medium", "high"), default=None,
                   help="for thinking models (OpenRouter's reasoning.effort); default: the model's own")
    r.add_argument("--resume", action="store_true", help="only re-run missing and failed cases")
    r.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    lm = sub.add_parser("model", help="resolve or download an open model to serve locally")
    lm.add_argument("action", choices=("resolve", "fetch"))
    lm.add_argument("preset")
    lm.add_argument("--models-dir", type=Path, default=Path("models"))
    lm.add_argument("--github-output", type=Path, default=None, help="append file=, sha256= and revision=")
    m = sub.add_parser("merge", help="combine shard results into one run")
    m.add_argument("run_id")
    m.add_argument("--parts", type=Path, nargs="+", required=True, help="run directories, one per shard")
    m.add_argument("--limit", type=int, default=None, help="the --limit the shards used")
    m.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
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

    if args.command == "model":
        from evals import local_model
        try:
            resolved = local_model.resolve(args.preset)
            if args.action == "fetch":
                path = local_model.fetch(resolved, args.models_dir)
                info = {**resolved, "path": str(path), "llama_cpp_python": local_model.server_version()}
                (args.models_dir / "model.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
                print(f"verified {path} (sha256 {resolved['sha256'][:12]}...)")
        except local_model.ModelError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(resolved, indent=2))
        if args.github_output:
            with args.github_output.open("a") as fh:
                fh.write("".join(f"{k}={resolved[k]}\n" for k in ("file", "sha256", "revision")))
        return 0
    if args.command == "merge":
        try:
            out = merge(args.run_id, args.parts, limit=args.limit, results_dir=args.results_dir)
        except MergeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"merged {len(args.parts)} parts -> {out}")
        return 0
    if args.command == "compare":
        out = compare(args.results_dir / args.run_id)
        print(f"wrote {out}")
        return 0
    try:
        out_dir, s = run(args.set_, args.model, run_id=args.run_id, limit=args.limit, base_url=args.base_url,
                         households=args.households, resume=args.resume, concurrency=args.concurrency,
                         retries=args.retries, max_tokens=args.max_tokens, reasoning_effort=args.reasoning_effort,
                         timeout=args.timeout, shard=_shard(args.shard),
                         model_info=json.loads(args.model_info.read_text()) if args.model_info else None,
                         results_dir=args.results_dir)
    except FatalApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{args.set_}: {s['cases']} cases, mean reward {s['mean_reward']}, {s['malformed']} malformed "
          f"({s['cut_off']} cut off at the token limit), "
          f"{s['api_errors']} API errors, ${s['cost_usd']:.4f} -> {out_dir}")
    if s["api_errors"]:
        print("error: some cases got no answer; re-run with --resume", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
