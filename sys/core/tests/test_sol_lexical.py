# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The words' index (hybrid search, M200): built with the vectors, dropped with them, its candidates re-ranked."""
from aurora import sol_lexical
from aurora import sol_schema as S
from aurora.sol_index import Indexer
from aurora.sol_search import Searcher
from aurora.sol_writer import VaultWriter

from test_sol_index import FakeEncoder, FakeReranker, doc


def test_the_words_index_follows_the_vectors(cfg):
    w = VaultWriter(cfg)
    w.add_many([doc(i) for i in range(8)])
    ix = Indexer(FakeEncoder(), cfg)
    ix.update("physics")
    assert sol_lexical.path(cfg).exists()
    found = sol_lexical.search(cfg, ["Which study is about plate tectonics?"], 3)
    reader = ix.reader
    assert found and "tectonics" in reader.get_many(found[:1])[found[0]].text
    w.add_many([doc(8, "the Runge-Kutta integrator with an adaptive grid")])
    ix.update("physics")                                     # incremental: only the new passage
    hit = sol_lexical.search(cfg, ["Quale integratore Runge-Kutta a griglia adattiva?"], 1)
    assert "Runge-Kutta" in reader.get_many(hit)[hit[0]].text
    assert ix.drop("physics", hit) == 1 and hit[0] not in sol_lexical.search(cfg, ["Runge-Kutta adaptive"], 5)


def test_the_words_candidates_reach_the_re_ranker(cfg):
    w = VaultWriter(cfg)
    w.add_many([doc(i) for i in range(8)] + [doc(9, "the Strang splitting scheme")])
    Indexer(FakeEncoder(), cfg).update("physics")
    rr = FakeReranker()
    s = Searcher(FakeEncoder(), rr, cfg)
    q = "prime numbers and the zeta function, or Strang"           # the vectors' one candidate: the prime numbers
    assert [h for h in s.search(q, candidates=1, top_k=3) if "Strang" in h.soliton.text]
    cfg.values["AURORA_SEARCH_LEXICAL"] = 0                          # vector search only: the Strang passage unseen
    assert not [h for h in s.search(q, candidates=1, top_k=3) if "Strang" in h.soliton.text]


def test_a_question_without_words_or_without_an_index_finds_nothing(cfg):
    assert sol_lexical.search(cfg, ["what is it?"], 5) == []          # no index yet
    assert sol_lexical.query("Qual è il della che?") == ""
    VaultWriter(cfg).add_many([S.Soliton.new("A note on " + "words " * 30, "physics", "knowledge", "en", "src:x")])
    Indexer(FakeEncoder(), cfg).update("physics")
    assert sol_lexical.search(cfg, ["what is it?"], 5) == []
