#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Write the invented law-office corpus into ../fonti/<matter>/ and its manifest (every file with its SHA-256).
Forms: pdf (text layer), scan (a PDF of page pictures, no text), png (a photographed page), eml, docx.
Usage: /usr/bin/python3 -I genera_corpus.py"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus_a  # noqa: E402
import corpus_b  # noqa: E402
import corpus_c  # noqa: E402
import corpus_fill  # noqa: E402
import render  # noqa: E402

ROOT = HERE.parent
FONTI = ROOT / "fonti"
MATTERS = {"A": "A_fornitura_Ferri_Lumen", "B": "B_licenziamento_Rinaldi", "C": "C_condominio_Tigli18"}


def docx(path: Path, text: str) -> None:
    """A minimal .docx (WordprocessingML), enough for Word to open it."""
    paras = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{p.replace('&', '&amp;').replace('<', '&lt;')}</w:t></w:r></w:p>"
                    for p in text.split("\n"))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{paras}</w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
                   'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/'
                   'document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
                   '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)


def eml(path: Path, text: str) -> None:
    head, _, body = text.partition("\n")
    lines = text.split("\n")
    hdr = {l.split(":", 1)[0]: l.split(":", 1)[1].strip() for l in lines[:4] if ":" in l}
    msg = (f"From: {hdr.get('Da', '')}\nTo: {hdr.get('A', '')}\nDate: {hdr.get('Data', '')}\nSubject: {hdr.get('Oggetto', '')}\n"
           "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\n" + "\n".join(lines[4:]) + "\n")
    path.write_text(msg, encoding="utf-8")


def main() -> None:
    tmp = ROOT / "tmp_render"
    tmp.mkdir(exist_ok=True)
    manifest = []
    allsets = [("A", corpus_a.DOCS), ("B", corpus_b.DOCS), ("C", corpus_c.DOCS)] + \
              [(k[0], [d]) for d in corpus_fill.DOCS for k in [d[0]]]
    for m, docs in allsets:
        for stem, form, pages in docs:
            folder = FONTI / MATTERS[m]
            folder.mkdir(parents=True, exist_ok=True)
            if form == "pdf":
                p = folder / f"{stem}.pdf"; render.text_pdf(p, pages)
            elif form == "scan":
                p = folder / f"{stem}.pdf"; render.scanned_pdf(p, pages, tmp)
            elif form == "png":
                p = folder / f"{stem}.png"; render.png_page(p, pages[0])
            elif form == "eml":
                p = folder / f"{stem}.eml"; eml(p, pages[0])
            elif form == "docx":
                p = folder / f"{stem}.docx"; docx(p, pages[0])
            else:
                raise ValueError(form)
            manifest.append({"matter": m, "stem": stem, "form": form, "pages": len(pages), "file": str(p.relative_to(ROOT)),
                             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({m: sum(1 for d in manifest if d["matter"] == m) for m in "ABC"}),
          json.dumps({f: sum(1 for d in manifest if d["form"] == f) for f in ("pdf", "scan", "png", "eml", "docx")}))


if __name__ == "__main__":
    main()
