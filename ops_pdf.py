"""Layout comum dos PDFs. A4, margem de 20 mm, Helvetica, preto e cinza."""

from __future__ import annotations

import hashlib
from datetime import datetime


PAGE_W = 595
PAGE_H = 842
MARGIN = 57


def filename(number: str, slug: str, moment: datetime) -> str:
    day = moment.date().isoformat() if isinstance(moment, datetime) else str(moment)[:10]
    return f"{_slug(number)}_{_slug(slug)}_{day}.pdf"


def render(doc: dict) -> bytes:
    sections = doc.get("sections") or []
    verify = ""
    if doc.get("verify"):
        raw = "\n".join(_section_text(section) for section in sections)
        verify = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8].upper()
    pages: list[list[str]] = [[]]
    y = PAGE_H - MARGIN - 52

    def page():
        return pages[-1]

    def ensure(height: float) -> None:
        nonlocal y
        if y - height >= MARGIN + 28:
            return
        pages.append([])
        y = PAGE_H - MARGIN - 52

    def text(x: float, yy: float, size: int, body: str, bold: bool = False, gray: bool = False) -> None:
        color = "0.35 0.35 0.35 rg" if gray else "0 0 0 rg"
        font = "/F2" if bold else "/F1"
        page().append(f"{color} BT {font} {size} Tf {x:.1f} {yy:.1f} Td ({_pdf_text(body)}) Tj ET")

    def rule(yy: float) -> None:
        page().append(f"0.75 0.75 0.75 RG 0.6 w {MARGIN} {yy:.1f} m {PAGE_W - MARGIN} {yy:.1f} l S")

    for section in sections:
        ensure(28)
        text(MARGIN, y, 9, str(section.get("title") or "").upper(), bold=True, gray=True)
        y -= 16
        pairs = section.get("pairs") or []
        col = 0
        for label, value in pairs:
            ensure(16)
            x = MARGIN if col == 0 else MARGIN + 250
            text(x, y, 9, str(label), gray=True)
            text(x + 78, y, 10, str(value or "—"))
            col = 1 - col
            if col == 0:
                y -= 14
        if col == 1:
            y -= 14
        for line in section.get("lines") or []:
            ensure(14)
            text(MARGIN, y, 10, str(line))
            y -= 13
        table = section.get("table")
        if table:
            headers = table.get("headers") or []
            rows = table.get("rows") or []
            aligns = table.get("align") or []
            width = (PAGE_W - MARGIN * 2) / max(1, len(headers))
            ensure(18)
            page().append(f"0.93 0.93 0.93 rg {MARGIN} {y - 4:.1f} {PAGE_W - MARGIN * 2:.1f} 16 re f")
            for index, header in enumerate(headers):
                text(MARGIN + index * width + 4, y, 9, str(header), bold=True)
            y -= 16
            rule(y + 12)
            for row in rows:
                ensure(16)
                for index, cell in enumerate(row):
                    offset = 4
                    if aligns[index:] and aligns[index] == "right":
                        offset = width - 8 - min(len(str(cell)), 18) * 5
                    text(MARGIN + index * width + max(4, offset), y, 9, str(cell))
                y -= 14
                rule(y + 11)
        for caption in section.get("signs") or []:
            ensure(36)
            y -= 18
            page().append(f"0 0 0 RG 0.6 w {MARGIN} {y:.1f} m {MARGIN + 180:.1f} {y:.1f} l S")
            text(MARGIN, y - 12, 9, caption, gray=True)
            y -= 22
        y -= 8

    streams = []
    total = len(pages)
    issued = doc.get("issued_at") or ""
    issuer = doc.get("issued_by") or "sistema"
    number = doc.get("number") or ""
    title = doc.get("title") or "Documento"
    org = doc.get("org") or "F.O.G.O."
    ident = doc.get("id") or number or "documento"
    for index, commands in enumerate(pages, start=1):
        header = [
            f"0 0 0 rg BT /F2 11 Tf {MARGIN} {PAGE_H - MARGIN:.1f} Td ({_pdf_text(org)}) Tj ET",
            f"BT /F2 14 Tf {MARGIN} {PAGE_H - MARGIN - 18:.1f} Td ({_pdf_text(title)}) Tj ET",
            f"0.35 0.35 0.35 rg BT /F1 9 Tf {MARGIN} {PAGE_H - MARGIN - 32:.1f} Td ({_pdf_text(f'{number}   {issued}   {issuer}')}) Tj ET",
            f"0.8 0.8 0.8 RG 0.6 w {MARGIN} {PAGE_H - MARGIN - 40:.1f} m {PAGE_W - MARGIN} {PAGE_H - MARGIN - 40:.1f} l S",
        ]
        footer_bits = [f"Página {index} de {total}", ident, "Gerado pelo sistema F.O.G.O."]
        if verify:
            footer_bits.append(f"Verificação {verify}")
        footer = [
            f"0.8 0.8 0.8 RG 0.6 w {MARGIN} {MARGIN - 8:.1f} m {PAGE_W - MARGIN} {MARGIN - 8:.1f} l S",
            f"0.35 0.35 0.35 rg BT /F1 8 Tf {MARGIN} {MARGIN - 22:.1f} Td ({_pdf_text('  ·  '.join(footer_bits))}) Tj ET",
        ]
        streams.append("\n".join(header + commands + footer))
    return _pack(streams)


def _section_text(section: dict) -> str:
    parts = [str(section.get("title") or "")]
    parts.extend(f"{label} {value}" for label, value in section.get("pairs") or [])
    parts.extend(str(line) for line in section.get("lines") or [])
    for row in (section.get("table") or {}).get("rows") or []:
        parts.append(" ".join(str(cell) for cell in row))
    return "\n".join(parts)


def _slug(value: str) -> str:
    folded = _plain(value).lower()
    out: list[str] = []
    for char in folded:
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != "-":
            out.append("-")
    text = "".join(out).strip("-")
    return (text[:48] or "registro")


def _plain(text: str) -> str:
    folded = str(text).translate(str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ",
        "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN",
    ))
    return folded.replace("\\", " ").replace("(", " ").replace(")", " ")


def _pdf_text(text: str) -> str:
    return _plain(text)[:180]


def _pack(streams: list[str]) -> bytes:
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    bold = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    objects: dict[int, bytes] = {3: font, 4: bold}
    kids = []
    number = 5
    for stream in streams:
        raw = stream.encode("latin-1", errors="replace")
        page_id = number
        content_id = number + 1
        number += 2
        kids.append(f"{page_id} 0 R".encode())
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
        ).encode()
        objects[content_id] = b"<< /Length " + str(len(raw)).encode() + b" >>\nstream\n" + raw + b"\nendstream"
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = b"<< /Type /Pages /Count " + str(len(streams)).encode() + b" /Kids [" + b" ".join(kids) + b"] >>"
    body = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for obj_number in sorted(objects):
        offsets[obj_number] = len(body)
        body.extend(f"{obj_number} 0 obj\n".encode())
        body.extend(objects[obj_number])
        body.extend(b"\nendobj\n")
    xref = len(body)
    size = max(objects) + 1
    body.extend(f"xref\n0 {size}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for obj_number in range(1, size):
        body.extend(f"{offsets.get(obj_number, 0):010d} 00000 n \n".encode())
    body.extend(f"trailer << /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(body)
