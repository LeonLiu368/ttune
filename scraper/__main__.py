from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from scraper.check import COMPARISONS, check_source, summary_markdown as check_summary
from scraper.extract import ParseError, extract_source
from scraper.fetch import FetchError, Http, fetch_source, import_files
from scraper.parsers import PARSERS

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Where a source can be fetched from. "local": sites that block cloud IPs (skipped with --ci).
# "manual": sites that block the scraper everywhere; download in a browser and use `import`.
WHERE = ("anywhere", "local", "manual")


def where(source: dict) -> str:
    value = source["fetch"].get("where", "anywhere")
    if value not in WHERE:
        raise ValueError(f"{source['id']}: fetch.where must be one of {WHERE}, got {value!r}")
    return value


def load_sources(data_dir: Path) -> dict:
    return json.loads((data_dir / "sources.json").read_text())


def save_sources(data_dir: Path, sources: dict) -> None:
    (data_dir / "sources.json").write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n")


def summary_markdown(rows: list[dict]) -> str:
    lines = ["## Scrape results", "", "| Source | Result | Files | Notes |", "|---|---|---|---|"]
    for r in rows:
        notes = r["notes"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{r['id']}` | {r['result']} | {r['files']} | {notes} |")
    return "\n".join(lines) + "\n"


def cmd_fetch(args: argparse.Namespace) -> int:
    sources = load_sources(args.data_dir)
    fetchable = [s for s in sources["sources"] if s.get("fetch")]
    rows: list[dict] = []
    if args.source:
        unknown = set(args.source) - {s["id"] for s in fetchable}
        if unknown:
            print(f"unknown or non-fetchable source(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        selected = [s for s in fetchable if s["id"] in args.source]
    else:
        skip = {"manual", "local"} if args.ci else {"manual"}
        selected = [s for s in fetchable if where(s) not in skip]
        for s in fetchable:
            if where(s) in skip:
                hint = "use `import`" if where(s) == "manual" else "run locally"
                rows.append({"id": s["id"], "result": "skipped", "files": 0, "notes": f"{where(s)} only; {hint}"})

    try:
        with httpx.Client(timeout=60) as client:
            http = Http(client)
            for source in selected:
                row = fetch_source(http, source, args.data_dir)
                rows.append(row)
                print(f"{row['id']}: {row['result']} ({row['files']} files) {row['notes']}".rstrip())
                save_sources(args.data_dir, sources)
    finally:
        if args.summary:
            Path(args.summary).write_text(summary_markdown(rows))
    return 1 if any(r["result"] in ("error", "partial") for r in rows) else 0


def cmd_import(args: argparse.Namespace) -> int:
    sources = load_sources(args.data_dir)
    source = next((s for s in sources["sources"] if s["id"] == args.source_id), None)
    if source is None:
        print(f"unknown source: {args.source_id}", file=sys.stderr)
        return 2
    missing = [str(p) for p in args.files if not p.is_file()]
    if missing:
        print(f"not a file: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        row = import_files(source, args.files, args.url or source["url"], args.data_dir)
    except FetchError as exc:
        print(exc, file=sys.stderr)
        return 1
    save_sources(args.data_dir, sources)
    print(f"{row['id']}: {row['result']} ({row['files']} files)")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    sources = load_sources(args.data_dir)["sources"]
    if args.source:
        unknown = set(args.source) - {s["id"] for s in sources}
        if unknown:
            print(f"unknown source(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        sources = [s for s in sources if s["id"] in args.source]
    failed = False
    for source in sources:
        try:
            row = extract_source(source, args.data_dir, PARSERS)
        except ParseError as exc:
            failed = True
            print(f"{source['id']}: error {exc}")
            continue
        detail = f" -> {row['output']} ({row['rows']} rows)" if row["output"] else ""
        print(f"{row['id']}: {row['result']}{detail}")
    return 1 if failed else 0


def cmd_check(args: argparse.Namespace) -> int:
    ids = args.source or list(COMPARISONS)
    unknown = set(ids) - set(COMPARISONS)
    if unknown:
        print(f"no comparison for: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    reports = [check_source(source_id, args.data_dir, COMPARISONS[source_id]) for source_id in ids]
    for report in reports:
        if report["result"] != "checked":
            print(f"{report['id']}: {report['result']}")
            continue
        counts = ", ".join(f"{n} {status}" for status, n in report["counts"].items() if n)
        print(f"{report['id']}: {counts} -> {report['output']}")
        for r in report["differences"][: args.show]:
            size = f" size {r.household_size}" if r.household_size else ""
            print(f"    {r.parameter} {r.region}{size}: official {r.official}, PolicyEngine {r.policyengine}"
                  + (f" ({r.note})" if r.note else ""))
        hidden = len(report["differences"]) - args.show
        if hidden > 0:
            print(f"    ... and {hidden} more")
    summary = args.data_dir / "processed" / "checks" / "summary.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(check_summary(reports))
    print(f"summary -> {summary.relative_to(args.data_dir).as_posix()}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    for s in load_sources(args.data_dir)["sources"]:
        how = where(s) if s.get("fetch") else "by hand"
        print(f"{s['id']:30} {s.get('status', ''):9} {how:9} {s.get('latest_snapshot') or s.get('local_path', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scraper")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download sources listed in sources.json")
    fetch.add_argument("--source", action="append", help="only this source id (repeatable)")
    fetch.add_argument("--summary", help="write a markdown results table to this file")
    fetch.add_argument("--ci", action="store_true", help="also skip sources marked where=local")
    fetch.set_defaults(func=cmd_fetch)

    imp = sub.add_parser("import", help="snapshot files you downloaded by hand")
    imp.add_argument("source_id")
    imp.add_argument("files", nargs="+", type=Path)
    imp.add_argument("--url", help="where the files were downloaded from (default: the source's url)")
    imp.set_defaults(func=cmd_import)

    extract = sub.add_parser("extract", help="parse latest snapshots into data/processed/<id>.csv")
    extract.add_argument("--source", action="append", help="only this source id (repeatable)")
    extract.set_defaults(func=cmd_extract)

    check = sub.add_parser("check", help="compare processed values with PolicyEngine")
    check.add_argument("--source", action="append", help="only this source id (repeatable)")
    check.add_argument("--show", type=int, default=10, help="differences to print per source (default 10)")
    check.set_defaults(func=cmd_check)

    status = sub.add_parser("status", help="show each source's status")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
