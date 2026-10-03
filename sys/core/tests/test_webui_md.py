# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The chat's Markdown: formulas (KaTeX), tables, and prices that are not formulas (webui/js/md.js under node)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
MD = HERE.parent / "webui" / "js" / "md.js"
CASES = {
    "La varianza è $V = M_2 - M_1^2$ [1].": "div.md(p(La varianza è  span.math[V = M_2 - M_1^2]  [1].))",
    "Costa $5 e $10 al mese.": "div.md(p(Costa $5 e $10 al mese.))",
    "Formula: \\(E = mc^2\\) qui.": "div.md(p(Formula:  span.math[E = mc^2]  qui.))",
    "$$\n\\int_0^1 x\\,dx = \\frac{1}{2}\n$$": "div.md(div.math.math-block[\\int_0^1 x\\,dx = \\frac{1}{2}])",
    "\\[ a^2 + b^2 = c^2 \\]": "div.md(div.math.math-block[a^2 + b^2 = c^2])",
    "| A | B |\n|---|---|\n| off | **2** |\n| on | $6$ |":
        "div.md(div.table-wrap(table(tr(th(A) th(B)) tr(td(off) td(strong[2])) tr(td(on) td(span.math[6])))))",
    "Testo con `codice $x$` e *corsivo*.": "div.md(p(Testo con  code[codice $x$]  e  em[corsivo] .))",
}


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_formulas_tables_and_prices():
    out = subprocess.run(["node", str(HERE / "js" / "md_render.mjs"), MD.as_uri(), json.dumps(list(CASES))],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    assert dict(zip(CASES, json.loads(out))) == CASES


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_what_is_read_aloud_has_no_markdown_citations_formulas_or_links():
    voice = (HERE.parent / "webui" / "js" / "voice.js").as_uri()
    text = ("## Risposta\nLa varianza è **quadratica** [1]. La formula $V = M_2 - M_1^2$ vale [2, 3].\n\n| A | B |\n"
            "|---|---|\n| 1 | 2 |\n\nVedi https://arxiv.org/abs/1 e `codice`.\n```py\nx=1\n```\nFine.")
    out = subprocess.run(["node", "--input-type=module", "-e",
                          f"const {{ speakable }} = await import({json.dumps(voice)}); console.log(speakable({json.dumps(text)}))"],
                         capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    assert out == "Risposta La varianza è quadratica. La formula vale. Vedi e codice. Fine."
