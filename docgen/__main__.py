"""python -m docgen build --set {id,ood} | pdf --set {id,ood} --out DIR [--ids ...]"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from docgen import documents, noise, render_text
from docgen.model import Packet
from envgen.describe import STATE_NAMES
from envgen.household import SETS, Household

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("snap", "eitc", "wic", "medicaid")


class BuildError(Exception):
    pass


def cover(household: Household, packet: Packet) -> str:
    where = STATE_NAMES[household.state] + (f", in {household.area}" if household.area else "")
    return (f"Case {household.id}\nLives in: {where}\n"
            f"The household's application and {len(packet.documents) - 1} supporting documents follow, "
            f"{len(packet.documents)} documents in all.\n")


def build(rows: list[dict]) -> list[dict]:
    from docgen import truth

    households = [Household.from_dict(r["household"]) for r in rows]
    packets = [documents.build(h) for h in households]
    for h, p in zip(households, packets):
        got, want = documents.established(p, h), documents.expected(h, p)
        if got != want:
            raise BuildError(f"{h.id}: the documents say {got}, the household says {want}")
    truths = truth.compute([(h, p, r["truth"]) for h, p, r in zip(households, packets, rows)])
    return [{"id": h.id, "case": render_text.render_packet(p, cover(h, p)), "household": h.to_dict(),
             "truth": t, "packet": p.to_dict()} for h, p, t in zip(households, packets, truths)]


def manifest(set_: str, source: dict, out: list[dict]) -> dict:
    from docgen import truth

    return {
        "set": set_, "n": len(out), "households": f"data/households/{set_}/households.jsonl",
        "seed": source.get("seed"), "policyengine_us": source.get("policyengine_us"),
        "application_date": documents.APPLICATION_DATE.isoformat(),
        "counts": {
            "issue": dict(sorted(Counter(i["kind"] for r in out for i in r["packet"]["issues"]).items())),
            "packets_with_gap": sum(any(i["gap"] for i in r["packet"]["issues"]) for r in out),
            "document": dict(sorted(Counter(d["kind"] for r in out for d in r["packet"]["documents"]).items())),
            "eligible": {p: dict(sorted(Counter(truth.eligible(r["truth"], p) for r in out).items()))
                         for p in PROGRAMS},
        },
    }


def report(meta: dict) -> tuple[str, bool]:
    c = meta["counts"]
    lines = [f"{meta['set']} documents: {meta['n']} packets, {c['packets_with_gap']} with a gap", "",
             f"{'program':10} {'yes':>5} {'no':>5} {'unknown':>8}"]
    ok = True
    for program, counts in c["eligible"].items():
        flag = ""
        if not counts.get("yes") or not counts.get("no"):
            ok, flag = False, "  <- all one answer"
        lines.append(f"{program:10} {counts.get('yes', 0):>5} {counts.get('no', 0):>5} {counts.get('unknown', 0):>8}{flag}")
    lines += ["", "issues: " + ", ".join(f"{k} {v}" for k, v in c["issue"].items())]
    missing = sorted(set(noise.KINDS) - set(c["issue"]))
    if missing:
        lines.append(f"never injected: {', '.join(missing)}")
    lines.append("documents: " + ", ".join(f"{k} {v}" for k, v in c["document"].items()))
    return "\n".join(lines), ok


def write_pdfs(rows: list[dict], out: Path) -> int:
    from docgen import render_pdf

    count = 0
    for row in rows:
        packet = Packet.from_dict(row["packet"])
        folder = out / row["id"]
        folder.mkdir(parents=True, exist_ok=True)
        for doc in packet.documents:
            (folder / f"{doc.name}.pdf").write_bytes(render_pdf.render(doc))
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m docgen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write document packets and their truth for a household set")
    b.add_argument("--set", choices=SETS, required=True, dest="set_")
    b.add_argument("--households", type=Path, default=None, help="default: data/households/<set>/households.jsonl")
    b.add_argument("--out", type=Path, default=None, help="default: data/documents/<set>")
    p = sub.add_parser("pdf", help="render a built set's documents as PDFs")
    p.add_argument("--set", choices=SETS, required=True, dest="set_")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ids", nargs="*", default=None, help="only these cases")
    args = parser.parse_args(argv)

    if args.command == "build":
        source = args.households or ROOT / "data" / "households" / args.set_ / "households.jsonl"
        rows = [json.loads(line) for line in source.open()]
        meta_path = source.parent / "manifest.json"
        source_meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        out_rows = build(rows)
        out = args.out or ROOT / "data" / "documents" / args.set_
        out.mkdir(parents=True, exist_ok=True)
        with (out / "cases.jsonl").open("w") as fh:
            for row in out_rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        meta = manifest(args.set_, source_meta, out_rows)
        (out / "manifest.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        text, ok = report(meta)
        print(text)
        print(f"\nwrote {out / 'cases.jsonl'} and manifest.json")
        if not ok:
            print("error: a program has only one answer across the set; the set can't measure it", file=sys.stderr)
            return 1
        return 0

    path = ROOT / "data" / "documents" / args.set_ / "cases.jsonl"
    rows = [json.loads(line) for line in path.open()]
    if args.ids:
        wanted = set(args.ids)
        rows = [r for r in rows if r["id"] in wanted]
        missing = wanted - {r["id"] for r in rows}
        if missing:
            print(f"error: no such cases: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
    print(f"wrote {write_pdfs(rows, args.out)} PDFs for {len(rows)} cases under {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
