# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The vault watched every night (kno_vault_audit): a document in two copies, an arXiv paper still as PDF and a
misplaced article are found; a misplaced one is confirmed only on a second night, then fixed by aurora-rem (C607).
Nothing is a notification: the owner is told what was done."""
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
    assert not told and "vault_realign.py" in out["text"] and A.done_tonight(cfg)      # no notification (C607)
    assert [a[1:] for a in A.fix_argv(cfg)] == [["--apply"]]                            # the PDF: fixed by aurora-rem
    A.mark_fixed(cfg, [{"ok": True}])
    assert A.fix_argv(cfg) == []                                                        # once
    clean = A.audit(cfg, Said("religion"), lambda e, p: told.append(p))       # the article where it belongs
    assert clean["misplaced"] == 0


def test_a_misplaced_article_is_confirmed_on_a_second_night_then_fixed(cfg, monkeypatch):
    """C607: one night's word is the chooser's noise (C405: 6 of 40 on 15 Nov, 1 the night after); the same other
    domain the night after is a fix — only for those entries, their domain kept where vault_realign reads it."""
    import json
    from aurora import kno_dedup
    kno_dedup._index.clear()
    imp = Importer(VaultWriter(cfg), Indexer(Emb(), cfg), cfg)
    monkeypatch.setattr(imp.indexer, "update", lambda *a, **k: 0)
    for i in range(3):
        body = f"Article {i} about the history of a small invented town and its people, told at length. " * 6
        imp.add(f"Town_{i}.txt", body.encode(), "religion", title=f"Town {i}", origin=f"wikipedia:Town {i}")
    told = []
    out = A.audit(cfg, Said("history"), lambda e, p: told.append(p))
    assert out["misplaced"] == 3 and out["confirmed"] == 0 and A.fix_argv(cfg) == [] and not told
    wavered = A.audit(cfg, Said("society"), lambda e, p: told.append(p))          # it changed its mind: nothing
    assert wavered["confirmed"] == 0 and A.fix_argv(cfg) == []
    A.audit(cfg, Said("history"), lambda e, p: told.append(p))                    # tonight's doubts: «history»
    out = A.audit(cfg, Said("history"), lambda e, p: told.append(p))              # and again the night after
    assert out["confirmed"] == 3 and not told
    (argv,) = A.fix_argv(cfg)
    assert argv[1:3] == ["--wikipedia", "--only"] and argv[-1] == "--apply" and len(argv[3].split(",")) == 3
    kept = json.loads((cfg.path("AURORA_STATUS_DIR") / "realign" / "wikipedia.json").read_text())
    assert {v["target"] for v in kept.values()} == {"history"}
