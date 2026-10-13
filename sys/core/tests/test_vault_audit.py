# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The vault watched every night (kno_vault_audit): a document in two copies, an arXiv paper still as PDF and a
misplaced article are found and told; a clean vault says nothing."""
from types import SimpleNamespace

from aurora import kno_vault_audit as A
from aurora.kno_ingest import Importer
from aurora.sol_index import Indexer
from aurora.sol_writer import VaultWriter


class Emb:
    dim = 4

    def encode_documents(self, texts):
        return [[1.0, 0, 0, 0] for _ in texts]


class Said:
    def __init__(self, word):
        self.word = word

    def complete(self, system, user, n):
        return SimpleNamespace(answer=self.word)


def test_copies_pdfs_and_misplaced_articles_are_told(cfg, monkeypatch):
    from aurora import kno_dedup
    kno_dedup._index.clear()
    w = VaultWriter(cfg)
    imp = Importer(w, Indexer(Emb(), cfg), cfg)
    monkeypatch.setattr(imp.indexer, "update", lambda *a, **k: 0)
    body = "Karl Marx was a German philosopher and economist of the nineteenth century, author of Capital. " * 6
    imp.add("Karl_Marx.txt", body.encode(), "religion", title="Karl Marx", origin="wikipedia:Karl Marx")
    from aurora.sol_schema import Soliton                        # a paper that came as PDF (before C293)
    w.add_many([Soliton.new("A paper about quintessence and dark energy in cosmology, with equations. " * 6, "astrophysics",
                            "knowledge", "en", "doc:pdfpaper", "Quintessence", chunk_index=0, chunk_count=1,
                            extra={"file": "2401.00001.pdf", "origin": "arxiv:2401.00001"})])
    told = []
    out = A.audit(cfg, Said("history"), lambda e, p: told.append(p))
    assert out["arxiv_pdf"] == 1 and out["duplicates"] == 0
    assert out["misplaced"] == 1 and out["misplaced_examples"][0]["would_be"] == "history"
    assert told and "vault_realign.py" in told[0]["text"] and A.done_tonight(cfg)
    clean = A.audit(cfg, Said("religion"), lambda e, p: told.append(p))       # the article where it belongs
    assert clean["misplaced"] == 0
