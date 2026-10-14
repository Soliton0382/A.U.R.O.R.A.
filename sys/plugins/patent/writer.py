# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The patent texts as PDF with real, searchable text (fpdf2, the plugin's own library), in each office's form
(rules.py): the description, the claims on their own sheets, the abstract on its own sheet. No AI notice, printed
or in the metadata: a filing goes to a public office and is signed by its inventor (owner, 2026-10-14)."""
from __future__ import annotations

from pathlib import Path

from rules import PAGES

FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial Unicode.ttf",
         "C:/Windows/Fonts/arial.ttf")
SIZE = 12                                                  # pt: capitals ≈ 3.1 mm, above every office's 2.1 mm
HEAD = {"IT": {"description": "DESCRIZIONE", "claims": "RIVENDICAZIONI", "abstract": "RIASSUNTO"},
        "EP": {"description": "DESCRIPTION", "claims": "CLAIMS", "abstract": "ABSTRACT"},
        "US": {"description": "SPECIFICATION", "claims": "CLAIMS", "abstract": "ABSTRACT"}}
CLAIMED = {"IT": "", "EP": "", "US": "What is claimed is:"}


def _pdf(rule: dict):
    import logging
    logging.getLogger("fontTools").setLevel(logging.WARNING)        # its subsetting talks at INFO: noise in the log
    from fpdf import FPDF
    w, h = PAGES[rule["page"]]
    m = rule["text_margins"]

    class Doc(FPDF):
        def footer(self):                                  # pages numbered, centred, inside the text area
            self.set_y(-(m["bottom"] + 6))
            self.set_font("body", size=10)
            self.cell(0, 5, str(self.page_no()), align="C")

    pdf = Doc(unit="mm", format=(w, h))
    pdf.set_margins(m["left"], m["top"], m["right"])
    pdf.set_auto_page_break(True, m["bottom"] + 12)        # the text stops above the page number
    font = next((f for f in FONTS if Path(f).is_file()), None)
    if not font:
        raise RuntimeError("no Unicode font found for the PDF")
    pdf.add_font("body", "", font)
    pdf.set_font("body", size=SIZE)
    pdf.set_creator("")                                   # nothing about who or what wrote it: the inventor signs
    pdf.set_producer("")
    return pdf


def _lines(pdf, text: str, rule: dict, number: int | None = None) -> None:
    lh = SIZE * 0.3528 * 1.2 * rule["spacing"]             # 1½ line spacing
    prefix = f"[{number:04d}] " if number is not None else ""
    pdf.multi_cell(0, lh, prefix + text.strip(), align="J")
    pdf.ln(lh * 0.5)


def write(out: Path, code: str, rule: dict, title: str, description: list[dict], claims: list[str],
          abstract: str) -> list[Path]:
    """description: [{"heading": "…", "text": "paragraph\\n\\nparagraph"}]. Returns the files written."""
    out.mkdir(parents=True, exist_ok=True)
    head, files = HEAD[code], []
    # the description (US: «specification»), its paragraphs numbered [0001] where the office uses it
    pdf = _pdf(rule)
    pdf.add_page()
    pdf.multi_cell(0, 7, title.strip().upper() if code == "US" else title.strip(), align="C")
    pdf.ln(4)
    n = 1
    for sec in description:
        if sec.get("heading"):
            pdf.multi_cell(0, 7, str(sec["heading"]).strip().upper(), align="L")
            pdf.ln(1)
        for para in [p for p in str(sec.get("text", "")).split("\n\n") if p.strip()]:
            _lines(pdf, para, rule, n if rule["paragraph_numbers"] else None)
            n += 1
    files.append(out / "01_description.pdf")
    pdf.output(str(files[-1]))
    if claims:                                             # on their own sheets (37 CFR 1.75(h); EPC; IT)
        pdf = _pdf(rule)
        pdf.add_page()
        pdf.multi_cell(0, 7, head["claims"], align="C")
        pdf.ln(3)
        if CLAIMED[code]:
            _lines(pdf, CLAIMED[code], rule)
        for i, c in enumerate(claims, 1):
            _lines(pdf, f"{i}. {c.strip().lstrip('0123456789. ')}", rule)
        files.append(out / "02_claims.pdf")
        pdf.output(str(files[-1]))
    pdf = _pdf(rule)                                       # the abstract, a sheet of its own
    pdf.add_page()
    pdf.multi_cell(0, 7, head["abstract"], align="C")
    pdf.ln(3)
    _lines(pdf, abstract, rule)
    files.append(out / "03_abstract.pdf")
    pdf.output(str(files[-1]))
    return files
