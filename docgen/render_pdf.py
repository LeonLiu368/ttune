"""PDF rendering of a document with reportlab, from the same blocks as the text twin. Byte-stable output."""

from __future__ import annotations

import io

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from docgen.model import Document

rl_config.invariant = 1  # no timestamps or random ids in the file, so the same document gives the same bytes

INK = colors.HexColor("#1f2328")
MUTED = colors.HexColor("#57606a")
RULE = colors.HexColor("#c8ccd1")
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, leading=11, textColor=MUTED)
ISSUER = ParagraphStyle("issuer", parent=BODY, fontName="Helvetica-Bold", fontSize=11, leading=14)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=14, leading=18, spaceBefore=6)
HEAD = ParagraphStyle("head", parent=BODY, fontName="Helvetica-Bold", fontSize=10, spaceBefore=4)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=9, leading=11.5)
WIDTH = letter[0] - 1.5 * inch


def _p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(text), style)


def render(doc: Document) -> bytes:
    buf = io.BytesIO()
    story: list = []
    for n, page in enumerate(doc.pages):
        if n:
            story.append(PageBreak())
        story += [_p(doc.issuer[0], ISSUER), *(_p(line, SMALL) for line in doc.issuer[1:]),
                  _p(doc.title, TITLE), _p(f"Dated {doc.date}", SMALL)]
        if page.of > 1:
            story.append(_p(f"Page {page.number} of {page.of}", SMALL))
        story.append(Spacer(1, 10))
        for block in page.blocks:
            story += _block(block) + [Spacer(1, 8)]
    pdf = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch, title=doc.title, author=doc.issuer[0],
                            creator="ttune docgen", producer="ttune docgen")
    pdf.build(story)
    return buf.getvalue()


def _block(block: dict) -> list:
    out = [_p(block["title"], HEAD)] if block.get("title") else []
    if block["type"] == "text":
        return out + [_p(block["text"])]
    if block["type"] == "fields":
        data = [[_p(label, CELL), _p(value, CELL)] for label, value in block["rows"]]
        table = Table(data, colWidths=[2.3 * inch, WIDTH - 2.3 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return out + [table]
    numeric = set(block.get("numeric", []))
    right = ParagraphStyle("right", parent=CELL, alignment=2)
    head = ParagraphStyle("th", parent=CELL, fontName="Helvetica-Bold")
    head_right = ParagraphStyle("thr", parent=head, alignment=2)
    data = [[_p(c, head_right if i in numeric else head) for i, c in enumerate(block["columns"])]]
    data += [[_p(str(c), right if i in numeric else CELL) for i, c in enumerate(row)] for row in block["rows"]]
    table = Table(data, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return out + [table]
