from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from scraper.fetch import Http, fetch_source

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


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
    if args.source:
        known = {s["id"] for s in fetchable}
        unknown = set(args.source) - known
        if unknown:
            print(f"unknown or non-fetchable source(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        fetchable = [s for s in fetchable if s["id"] in args.source]

    rows: list[dict] = []
    try:
        with httpx.Client(timeout=60) as client:
            http = Http(client)
            for source in fetchable:
                row = fetch_source(http, source, args.data_dir)
                rows.append(row)
                print(f"{row['id']}: {row['result']} ({row['files']} files) {row['notes']}".rstrip())
                save_sources(args.data_dir, sources)
    finally:
        if args.summary:
            Path(args.summary).write_text(summary_markdown(rows))
    return 1 if any(r["result"] in ("error", "partial") for r in rows) else 0


def cmd_status(args: argparse.Namespace) -> int:
    for s in load_sources(args.data_dir)["sources"]:
        status = s.get("status", "") if s.get("fetch") else f"{s.get('status', '')} (manual)"
        print(f"{s['id']:30} {status:18} {s.get('latest_snapshot') or s.get('local_path', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scraper")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download sources listed in sources.json")
    fetch.add_argument("--source", action="append", help="only this source id (repeatable)")
    fetch.add_argument("--summary", help="write a markdown results table to this file")
    fetch.set_defaults(func=cmd_fetch)

    status = sub.add_parser("status", help="show each source's status")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
