# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""search_vault (agt_vault): the vault's passages for an agent's phase, with title and source; Aurora's own answers,
reflections and the conversations are never returned as sources."""
from types import SimpleNamespace

from aurora import agt_vault


def _hit(title, kind="paper", text="testo"):
    return SimpleNamespace(rerank=0.8, soliton=SimpleNamespace(title=title, kind=kind, domain="physics",
                                                               source_id="arxiv:1", text=text))


class _Search:
    def __init__(self, hits):
        self.hits, self.asked = hits, []

    def search(self, q, top_k=None):
        self.asked.append((q, top_k))
        return self.hits


def test_passages_come_with_their_source_and_own_answers_are_dropped():
    s = _Search([_hit("Mia risposta", "conversation"), _hit("Coreless AFPM coil shapes", text="x" * 5000),
                 _hit("Un sogno", "reflection"), _hit("Halbach arrays")])
    seen = []
    out = agt_vault.run(SimpleNamespace(search=s), {"query": "axial flux coil shape", "top_k": 2},
                        lambda e, p: seen.append((e, p)))
    assert "[1] Coreless AFPM coil shapes — physics — arxiv:1" in out and "[2] Halbach arrays" in out
    assert "Mia risposta" not in out and "Un sogno" not in out
    assert len(out) < 2 * agt_vault.PASSAGE_CHARS + 300                          # passages clipped
    assert seen == [("vault.search", {"query": "axial flux coil shape", "hits": 2})]


def test_empty_vault_and_bad_input_say_so():
    nothing = SimpleNamespace(search=_Search([]))
    assert "nothing" in agt_vault.run(nothing, {"query": "x"}, lambda e, p: None)
    assert agt_vault.run(nothing, {"query": " "}, lambda e, p: None).startswith("ERROR")
    s = _Search([])
    agt_vault.run(SimpleNamespace(search=s), {"query": "x", "top_k": 99}, lambda e, p: None)
    assert s.asked[0][1] == agt_vault.MAX_K + 4
