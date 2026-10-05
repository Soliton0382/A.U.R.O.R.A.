# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""An arXiv paper's text with readable formulas: arXiv's HTML version (or ar5iv's) first, the PDF only when none.

The PDF's extracted text garbles formulas (the norm ‖x‖ comes out as "kxk", subscripts on other lines) and the
verifier then refuses a right sentence that re-typesets them (BUGS C135, M92, M97). arXiv's HTML version carries every
formula as LaTeX in the MathML's alttext: on 107 of 120 garbled papers it gave a clean text (M97).
"""
from __future__ import annotations

import html
import re
from typing import Callable

MIN_CHARS = 3000                                  # an HTML page shorter than this is an error page or an abstract


def clean_text(page: str) -> str:
    """arXiv's HTML (LaTeXML) as plain text: the article only, formulas as $LaTeX$, no bibliography."""
    m = re.search(r"<article.*?</article>", page, re.S)
    page = m.group(0) if m else page
    page = re.sub(r'<section[^>]*class="[^"]*ltx_bibliography.*?</section>', " ", page, flags=re.S)
    page = re.sub(r"<(script|style|nav|footer)[^>]*>.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r'<math[^>]*alttext="([^"]*)"[^>]*>.*?</math>', lambda m: " $" + html.unescape(m.group(1)) + "$ ",
                  page, flags=re.S)
    page = re.sub(r"</(p|h[1-6]|li|div|section|figcaption|tr)>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


# arXiv's own HTML (papers since December 2023), then ar5iv (arXiv's conversion of the older ones)
HTML = ("https://arxiv.org/html/{}", "https://ar5iv.labs.arxiv.org/html/{}")


def paper(arxiv_id: str, pdf_url: str, get: Callable) -> tuple[str, bytes]:
    """(file name, data) to import: the HTML's text as .txt when arXiv has it, else the PDF. `get(url)` returns a
    response (the caller's own client: its pace, its user agent); an error on the HTML falls back to the PDF."""
    base = arxiv_id.replace("/", "_")
    for url in HTML:
        try:
            r = get(url.format(arxiv_id))
        except Exception:                             # noqa: BLE001 — no HTML version (404) or a network error
            continue
        if "/html/" not in str(getattr(r, "url", "/html/")):   # ar5iv without the paper redirects to the abstract
            continue
        text = clean_text(r.text)
        if len(text) >= MIN_CHARS:
            return f"{base}.txt", text.encode("utf-8")
    return f"{base}.pdf", get(pdf_url).content
