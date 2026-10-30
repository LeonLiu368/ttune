"""Plain-text rendering of a document: what a text-only model reads. Deterministic, 80 columns."""

from __future__ import annotations

import textwrap

from docgen.model import Document, Packet

WIDTH = 80


def render(doc: Document) -> str:
    lines = [*doc.issuer, "", doc.title.upper(), f"Dated {doc.date}", ""]
    for page in doc.pages:
        if page.of > 1:
            lines += [f"[Page {page.number} of {page.of}]", ""]
        for block in page.blocks:
            lines += _block(block) + [""]
    return "\n".join(lines).rstrip() + "\n"


def _block(block: dict) -> list[str]:
    out = [block["title"]] if block.get("title") else []
    if block["type"] == "text":
        return out + textwrap.wrap(block["text"], WIDTH)
    if block["type"] == "fields":
        width = max(len(label) for label, _ in block["rows"])
        for label, value in block["rows"]:
            wrapped = textwrap.wrap(value, WIDTH - width - 3) or [""]
            out.append(f"{label + ':':<{width + 1}}  {wrapped[0]}")
            out += [" " * (width + 3) + rest for rest in wrapped[1:]]
        return out
    columns, rows, numeric = block["columns"], block["rows"], set(block.get("numeric", []))
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(columns)]

    def line(cells) -> str:
        return "  ".join(str(c).rjust(w) if i in numeric else str(c).ljust(w)
                         for i, (c, w) in enumerate(zip(cells, widths))).rstrip()

    return out + [line(columns), "  ".join("-" * w for w in widths)] + [line(r) for r in rows]


def render_packet(packet: Packet, cover: str) -> str:
    """Everything a text-only model reads for one case: a cover note, then each document in order."""
    parts = [cover.rstrip() + "\n"]
    for n, doc in enumerate(packet.documents, start=1):
        parts.append(f"{'=' * WIDTH}\nDocument {n} of {len(packet.documents)}: {doc.title}\n{'=' * WIDTH}\n"
                     + render(doc))
    return "\n".join(parts)
