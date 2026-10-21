# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A filing package checked against an office's rules of form (rules.py), file by file: page size, the margins
(where the ink is), black only in the drawings, the abstract's words, the claims' numbering, every reference sign
of the drawings recalled in the description (IT art. 22.3), no AI notice printed or in the metadata, dates written
in the documents. A report — it changes nothing."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from rules import AI_MARKS, PAGES

OK, WARN, BAD = "✅", "⚠️", "❌"


def _text(pdf: Path) -> tuple[str, dict, list[tuple[float, float]]]:
    from pypdf import PdfReader
    r = PdfReader(str(pdf))
    meta = {k.lstrip("/"): str(v) for k, v in (r.metadata or {}).items()}
    sizes = [(float(p.mediabox.width) * 25.4 / 72, float(p.mediabox.height) * 25.4 / 72) for p in r.pages]
    return "\n".join(p.extract_text() or "" for p in r.pages), meta, sizes


def _pages(pdf: Path, dpi: int = 40) -> list[np.ndarray]:
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), f"{d}/p"], check=True, capture_output=True,
                       timeout=300)
        return [np.asarray(Image.open(p).convert("RGB")) for p in sorted(Path(d).glob("p*.png"))]


def _margins(img: np.ndarray, dpi: int) -> tuple[dict, dict] | None:
    """(the margins of the ink, of the ink without a lone header or footer line) in mm: a running line with the page
    number in the top or bottom margin is told apart from text that runs into it."""
    ink = img.min(axis=2) < 200
    rows = np.nonzero(ink.any(axis=1))[0]
    if not len(rows):
        return None
    mm = 25.4 / dpi
    h, w = ink.shape

    def edges(r0, r1):
        sub = ink[r0:r1 + 1]
        xs = np.nonzero(sub.any(axis=0))[0]
        return {"top": r0 * mm, "left": xs.min() * mm, "right": (w - 1 - xs.max()) * mm, "bottom": (h - 1 - r1) * mm}
    groups = np.split(rows, np.nonzero(np.diff(rows) > max(2, round(2 / mm)))[0] + 1)     # lines of ink, 2 mm apart
    line = round(6 / mm)                                                                     # one text line high
    lone_top = len(groups) > 2 and groups[0][-1] - groups[0][0] <= line
    lone_bottom = len(groups) > 2 and groups[-1][-1] - groups[-1][0] <= line
    r0 = groups[1][0] if lone_top else rows[0]
    r1 = groups[-2][-1] if lone_bottom else rows[-1]
    return edges(rows[0], rows[-1]), edges(r0, r1)


def check(folder: Path, rule: dict) -> list[tuple[str, str]]:
    """[(mark, what)] for every PDF of the folder and the package as a whole."""
    out: list[tuple[str, str]] = []
    pdfs = sorted(p for p in folder.glob("*.pdf"))
    if not pdfs:
        return [(BAD, f"no PDF in {folder}")]
    page = PAGES[rule["page"]]
    texts: dict[str, str] = {}
    for f in pdfs:
        kind = "drawings" if re.search(r"draw|disegn|tavol", f.name, re.I) else "text"
        text, meta, sizes = _text(f)
        texts[f.name] = text
        ok_size = all(any(abs(w - a) < 2 and abs(h - b) < 2 for a, b in PAGES.values()) for w, h in sizes)
        out.append((OK if ok_size else BAD, f"{f.name}: {len(sizes)} pages, {sizes[0][0]:.0f} × {sizes[0][1]:.0f} mm"
                    + ("" if ok_size else " — not A4 nor letter")))
        if rule["page"] == "A4" and any(abs(w - 215.9) < 2 for w, _ in sizes):
            out.append((BAD, f"{f.name}: letter size; this office asks for A4"))
        want = rule["drawing_margins" if kind == "drawings" else "text_margins"]
        dpi, worst, lone = 40, {}, set()
        for i, img in enumerate(_pages(f, dpi), 1):
            m = _margins(img, dpi)
            if m:
                full, inner = m
                for side, v in full.items():
                    if v + 0.8 < want[side]:                     # 0.8 mm: a pixel at 40 dpi and the anti-aliasing
                        if side in ("top", "bottom") and inner[side] + 0.8 >= want[side]:
                            lone.add(side)                       # only a running header/footer line is there
                        else:
                            worst[side] = min(worst.get(side, 99), v)
            if kind == "drawings":
                rgb = img.astype(int)
                colour = (rgb.max(axis=2) - rgb.min(axis=2) > 40).mean()
                if colour > 0.001:
                    out.append((BAD, f"{f.name} p. {i}: colours in a drawing ({colour:.1%} of the page): black lines only"))
        if lone:
            out.append((WARN, f"{f.name}: a running {'/'.join(sorted(lone))} line (page number, name) inside the "
                              f"{'/'.join(sorted(lone))} margin — move it into the text area or remove it"))
        out.append((BAD, f"{f.name}: margins under the minimum — " + ", ".join(f"{s} {v:.1f} mm (≥ {want[s]})"
                                                                              for s, v in worst.items()))
                   if worst else (OK, f"{f.name}: margins at least {want['top']}/{want['left']}/{want['right']}/"
                                      f"{want['bottom']} mm"))
        low = (text + " " + " ".join(meta.values())).lower()
        marks = [m for m in AI_MARKS if m in low]
        out.append((WARN if marks == ["aurora"] else BAD, f"{f.name}: AI notice or name found: {', '.join(marks)}")
                   if marks else (OK, f"{f.name}: no AI notice, printed or in the metadata"))
    abstract = next((t for n, t in texts.items() if re.search(r"abstract|riassunto", n, re.I)), "")
    if abstract and rule["abstract_words"]:
        lines = [ln for ln in abstract.splitlines() if ln.strip()]
        counted = [ln for ln in lines if re.search(r"(?i)word count|numero di parole", ln)]
        body = [ln for ln in lines if ln not in counted and not re.match(r"(?i)\s*(abstract|riassunto)\b", ln)
                and not re.search(r"(?i)\bpage \d+\s*$|\bpag(ina)?\.? \d+\s*$", ln)]
        words = len(re.findall(r"\b\w[\w'-]*\b", " ".join(body)))
        out.append((OK if words <= rule["abstract_words"] else BAD,
                    f"abstract: {words} words (≤ {rule['abstract_words']})"))
        if counted:
            out.append((BAD, f"abstract: a line that is not the abstract — «{counted[0].strip()[:60]}»: it would be "
                             "published with it"))
    claims = next((t for n, t in texts.items() if re.search(r"claim|rivendic", n, re.I)), "")
    if claims:
        # «Claim 1 (…)», «Rivendicazione 1», or «1. A method…» — not a number that starts a line of a claim's text
        nums = [int(a or b) for a, b in re.findall(r"(?m)^\s*(?:(?:[Cc]laim|[Rr]ivendicazione)\s+(\d{1,3})\b(?!\s*[-–])|"
                                                     r"(\d{1,3})\.\s+[A-ZÀ-Ú])", claims)]
        seq = nums == list(range(1, len(nums) + 1))
        out.append((OK if seq and nums else BAD, f"claims: {len(nums)}, numbered " + ("1…n" if seq else str(nums[:12]))))
    elif rule["claims_required"]:
        out.append((BAD, "claims: none found — this office asks for them"))
    desc = next((t for n, t in texts.items() if re.search(r"descri|specif", n, re.I)), "")
    signs = folder / "reference_signs.md"
    if desc and signs.is_file() and rule["signs_in_description"]:
        # a line «12  name» or a Markdown table row «| 12 | name |» (C382: a table read as no sign at all, «0 recalled»)
        want = re.findall(r"(?m)^\|?\s*(\d{1,4})\s*[|\s]", signs.read_text(encoding="utf-8"))
        missing = [s for s in want if not re.search(rf"\b{s}\b", desc)]
        if not want:
            out.append((WARN, "reference_signs.md lists no sign («12  name» or «| 12 | name |» per line): nothing checked"))
        else:
            out.append((BAD, f"reference signs not recalled in the description: {', '.join(missing)}") if missing
                       else (OK, f"all {len(want)} reference signs recalled in the description"))
    dates = sorted(set(re.findall(r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|"
                                  r"October|November|December|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
                                  r"agosto|settembre|ottobre|novembre|dicembre) 20\d\d\b", " ".join(texts.values()))))
    if dates:
        out.append((WARN, f"dates written in the documents (check them against the real filing date): {', '.join(dates)}"))
    return out
