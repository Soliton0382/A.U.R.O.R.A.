# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Reading a page whole (owner, 30 Oct: «le ho dato il link del mio paper ha letto solo l'abstract e non il PDF»): a
paper's page opens its own PDF; redirects followed, each hop checked again (a private address refused); a PDF link
read as text. A made-up site, no network."""
import httpx
import pytest

from aurora import kno_web as W

PAPER = ('<html><head><meta name="citation_pdf_url" content="/records/1/files/paper.pdf?download=1"></head><body>'
         '<p>' + "Abstract: a made-up study of solitons in a made-up lattice, long enough to be kept. " * 3 + '</p></body></html>')
PDF = b"%PDF-1.4 made-up"


def routes(request):
    path = request.url.path
    if path == "/records/1":
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAPER)
    if path == "/records/1/files/paper.pdf":
        return httpx.Response(302, headers={"location": "https://files.example.org/real.pdf"})
    if path == "/real.pdf":
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=PDF)
    if path == "/to-private":
        return httpx.Response(302, headers={"location": "http://intranet.example.org/secret"})
    return httpx.Response(404)


@pytest.fixture
def site(monkeypatch):
    real = httpx.Client
    monkeypatch.setattr(W.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(routes), **kw))
    monkeypatch.setattr(W, "_public", lambda url: None if "intranet" in url else "93.184.216.34")
    from aurora import sec_linkcheck
    checked = []
    monkeypatch.setattr(sec_linkcheck, "check", lambda url: checked.append(url) or {"blocked": False})
    monkeypatch.setattr(W, "_pdf_text", lambda r: "Section 1. The full text of the made-up paper. " * 30)
    return checked


def test_a_paper_s_page_opens_its_own_pdf(site):
    text = W.page("https://zenodo.example.org/records/1")
    assert text.startswith("Abstract: a made-up study") and "[PDF]" in text and "The full text of the made-up paper" in text
    assert len(text) > 1200                                           # more than the abstract
    assert {"zenodo.example.org", "files.example.org"} <= {httpx.URL(u).host for u in site}   # each new site checked


def test_a_redirect_to_a_private_address_is_refused(site):
    assert W.page("https://zenodo.example.org/to-private") == ""


def test_a_pdf_link_is_read_as_text(site):
    assert W.page("https://files.example.org/real.pdf").startswith("Section 1.")
