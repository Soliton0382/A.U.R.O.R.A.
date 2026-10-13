# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""arXiv papers come in as HTML text with LaTeX formulas, the PDF only when there is no HTML (C137)."""
import httpx

from aurora import kno_arxiv

ARTICLE = ('<html><nav>menu</nav><article><h1>Title</h1><p>The norm <math alttext="\\|x\\|_{2}"><mi>x</mi></math> '
           'is bounded.</p>' + "<p>" + "Some text. " * 400 + "</p>"
           '<section class="ltx_bibliography"><p>[1] A reference</p></section></article></html>')


class Resp:
    def __init__(self, text="", content=b""):
        self.text, self.content = text, content


def getter(pages):
    seen = []

    def get(url):
        seen.append(url)
        if url not in pages:
            raise httpx.HTTPStatusError("404", request=httpx.Request("GET", url), response=httpx.Response(404))
        return pages[url]
    return get, seen


def test_the_html_version_is_taken_with_its_formulas_as_latex():
    get, seen = getter({"https://arxiv.org/html/2401.00001": Resp(ARTICLE)})
    name, data = kno_arxiv.paper("2401.00001", "https://arxiv.org/pdf/2401.00001", get)
    text = data.decode()
    assert name == "2401.00001.txt" and seen == ["https://arxiv.org/html/2401.00001"]
    assert "$\\|x\\|_{2}$" in text and "A reference" not in text and "menu" not in text


def test_no_html_version_means_not_taken():
    """Owner, 13 Oct: arXiv only as HTML (the PDF's formulas came out garbled): not even downloaded."""
    import pytest
    get, seen = getter({"https://arxiv.org/pdf/2401.00002": Resp(content=b"%PDF-1.5")})
    with pytest.raises(kno_arxiv.NoHTML):
        kno_arxiv.paper("2401.00002", "https://arxiv.org/pdf/2401.00002", get)
    assert seen == ["https://arxiv.org/html/2401.00002", "https://ar5iv.labs.arxiv.org/html/2401.00002"]


def test_an_older_paper_comes_from_ar5iv_but_not_its_redirect_to_the_abstract():
    import pytest
    get, _ = getter({"https://ar5iv.labs.arxiv.org/html/1205.1290": Resp(ARTICLE)})
    assert kno_arxiv.paper("1205.1290", "https://arxiv.org/pdf/1205.1290", get)[0] == "1205.1290.txt"
    abstract = Resp(ARTICLE)
    abstract.url = "https://arxiv.org/abs/2406.05411"                   # what ar5iv answers when it lacks the paper
    get, _ = getter({"https://ar5iv.labs.arxiv.org/html/2406.05411": abstract})
    with pytest.raises(kno_arxiv.NoHTML):
        kno_arxiv.paper("2406.05411", "https://arxiv.org/pdf/2406.05411", get)


def test_a_short_html_page_is_not_a_paper():
    import pytest
    get, _ = getter({"https://arxiv.org/html/hep-th/9901001": Resp("<article><p>No HTML for this one.</p></article>")})
    with pytest.raises(kno_arxiv.NoHTML):
        kno_arxiv.paper("hep-th/9901001", "https://arxiv.org/pdf/hep-th/9901001", get)
