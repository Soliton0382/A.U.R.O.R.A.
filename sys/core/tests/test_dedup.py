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
    assert D.title_key("Attention") == ""                     # a title too short says nothing


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
