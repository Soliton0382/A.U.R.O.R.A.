# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""One document, one copy (owner, 2026-10-05: the vault must be solid): the same paper as PDF and then as HTML, or an
article of the previous installation harvested again, is recognised and not written twice (C150)."""
from aurora import kno_dedup as D
from aurora.kno_ingest import Importer
from aurora.sol_index import Indexer
from aurora.sol_writer import VaultWriter

PAPER = ("Dark energy quintessence models are studied with a scalar field whose potential drives the late acceleration "
         "of the universe; the stability of the solutions and the swampland conjectures constrain the parameters. ") * 6


class Emb:
    dim = 4

    def encode_documents(self, texts):
        return [[1.0, 0, 0, 0] for _ in texts]


def test_signatures_tell_a_copy_from_another_document():
    other = "Abraham Lincoln was the sixteenth president of the United States during the civil war " * 5
    assert D.similarity(D.signature(PAPER), D.signature(PAPER.replace("universe", "Universe"))) >= D.SAME
    assert D.similarity(D.signature(PAPER), D.signature(other)) < D.SAME
    assert D.title_key("Karl Marx") == "karl marx" and D.title_key("Ok") == ""   # 13 Oct: short titles are looked at too


def test_the_same_document_in_another_form_is_not_written_twice(cfg, monkeypatch):
    D._index.clear()
    imp = Importer(VaultWriter(cfg), Indexer(Emb(), cfg), cfg)
    monkeypatch.setattr(imp.indexer, "update", lambda *a, **k: 0)
    first = imp.add("2401.00001-pdf.txt", PAPER.encode(), "physics", title="A Dark Energy Quintessence Model")
    again = imp.add("2401.00001.txt", (PAPER + " Figure 1.").encode(), "relativity", title="A dark-energy quintessence model")
    assert first.written > 0 and not first.duplicate_of
    assert again.written == 0 and again.duplicate_of == f"physics/{first.source_id}"
    forced = imp.add("2401.00001.html.txt", (PAPER + " v2").encode(), "physics", title="A Dark Energy Quintessence Model",
                     meta={"replace": "yes"})                    # an explicit replacement (A19's way) still goes in
    assert forced.written > 0


def test_two_official_identities_are_two_documents(cfg, monkeypatch):
    """Normattiva: hundreds of acts share a title and nearly a text; their URNs say they are distinct."""
    D._index.clear()
    imp = Importer(VaultWriter(cfg), Indexer(Emb(), cfg), cfg)
    monkeypatch.setattr(imp.indexer, "update", lambda *a, **k: 0)
    statute = "Modificazioni allo statuto dell'Università degli studi: l'articolo è sostituito dal seguente testo. " * 8
    a = imp.add("a.txt", statute.encode(), "law_it", title="Modificazioni allo statuto dell'Università di Roma",
                origin="normattiva:urn:nir:stato:decreto:1948-12-24;1619")
    b = imp.add("b.txt", (statute + "1949").encode(), "law_it", title="Modificazioni allo statuto dell'Università di Roma",
                origin="normattiva:urn:nir:stato:decreto:1949-10-20;989")
    assert a.written > 0 and b.written > 0 and not b.duplicate_of


def test_the_same_official_identity_is_one_document_whatever_its_form_or_domain(cfg, monkeypatch):
    """13 Oct census: an arXiv paper taken as HTML and as PDF (under half its words in common) went in twice, in two
    domains; a v1 Wikipedia article and the same one harvested again by v2 were both kept («Karl Marx», 9 letters)."""
    D._index.clear()
    imp = Importer(VaultWriter(cfg), Indexer(Emb(), cfg), cfg)
    monkeypatch.setattr(imp.indexer, "update", lambda *a, **k: 0)
    html = "Neural networks of any architecture can be written as decision trees, layer by layer, exactly. " * 6
    pdf = "We show an equivalence between piecewise linear activations and oblique trees with many leaves. " * 6
    a = imp.add("2210.05189.html.txt", html.encode(), "biomedicine", title="Neural networks as decision trees", origin="arxiv:2210.05189")
    b = imp.add("2210.05189.pdf.txt", pdf.encode(), "condensed_matter", title="Neural Networks are Decision Trees", origin="arxiv:2210.05189")
    assert a.written > 0 and b.written == 0 and b.duplicate_of == f"biomedicine/{a.source_id}"
    assert D.official("legacy:wiki_Karl_Marx_txt_done") == "wikipedia:Karl Marx"
    marx = "Karl Marx was a German philosopher, economist, historian and revolutionary socialist of the nineteenth century. " * 6
    v1 = imp.add("wiki_Karl_Marx.txt", marx.encode(), "history", title="Karl Marx", origin="legacy:wiki_Karl_Marx_txt_done")
    v2 = imp.add("Karl_Marx.txt", ("Revised article. " + marx).encode(), "general", title="Karl Marx", origin="wikipedia:Karl Marx")
    assert v1.written > 0 and v2.written == 0 and v2.duplicate_of.startswith("history/")


def test_a_document_sent_as_ready_passages_is_known_by_its_identity(cfg, monkeypatch):
    """POST /v1/aurora/solitons (Normattiva's articles) had no document check: the same identity is now refused."""
    D._index.clear()
    imp = Importer(VaultWriter(cfg), Indexer(Emb(), cfg), cfg)
    monkeypatch.setattr(imp.indexer, "update", lambda *a, **k: 0)
    urn = "normattiva:urn:nir:stato:legge:2020-01-01;1"
    imp.add("legge.txt", ("Art. 1. La presente legge disciplina la materia in modo organico e completo. " * 8).encode(),
            "law_it", title="Legge di prova", origin=urn)
    from aurora.sol_reader import VaultReader
    assert D.known(cfg, VaultReader(cfg), urn)[0] == "law_it"
    assert D.known(cfg, VaultReader(cfg), "normattiva:urn:nir:stato:legge:2020-01-01;2") is None
    assert D.known(cfg, VaultReader(cfg), "upload") is None                   # no official identity: not this check


def test_one_preprint_on_two_archives_is_one_document(cfg, monkeypatch):
    """13 Oct census: the same paper on bioRxiv and on arXiv went in twice, in two domains."""
    D._index.clear()
    imp = Importer(VaultWriter(cfg), Indexer(Emb(), cfg), cfg)
    monkeypatch.setattr(imp.indexer, "update", lambda *a, **k: 0)
    text = "Neural networks of any architecture can be written as decision trees, layer by layer, exactly as shown. " * 6
    a = imp.add("2610.08228.txt", text.encode(), "condensed_matter", title="Neural networks as decision trees: an analytical solution",
                origin="arxiv:2610.08228")
    b = imp.add("biorxiv.txt", (text + " Supplement.").encode(), "biomedicine", title="Neural networks as decision trees: an analytical solution",
                origin="biorxiv:10.64898/2026.09.23.753718")
    assert a.written > 0 and b.written == 0 and b.duplicate_of.startswith("condensed_matter/")
