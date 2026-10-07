# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A case told as a story, searched as the questions it holds (kno_split, C183)."""
from types import SimpleNamespace

from aurora import kno_split

CASE = ("Viviamo in un contesto di villette, quindi un supercondominio. Vogliamo togliere i contalitri dell'acqua per "
        "avere i contatori nominali, ma il costruttore manda lettere di avvocati. In più una vicina ci accusa di allacci "
        "abusivi ai box, quando è stato l'architetto ad allacciarli alle parti comuni.")


class Model:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def complete(self, system, user, max_tokens, think=False):
        self.asked.append(user)
        return SimpleNamespace(answer=self.answer)


def _hit(sid, rerank, kind="law", role=None, text="testo"):
    return SimpleNamespace(sid=sid, rerank=rerank, soliton=SimpleNamespace(kind=kind, text=text, extra={"role": role} if role else {}))


def test_only_a_long_message_is_split():
    assert kno_split.wanted(CASE, 220) and not kno_split.wanted("cos'è l'entropia?", 220) and not kno_split.wanted(CASE, 0)


def test_the_model_s_lines_become_at_most_four_clean_searches():
    m = Model("1. sostituzione dei contatori dell'acqua nel supercondominio: chi decide\n- Sostituzione dei contatori "
              "dell'acqua nel supercondominio: chi decide\n• opposizione del costruttore ai lavori condominiali\n\n"
              "«allacciamento dei box alle parti comuni: responsabilità»\n4) a\nuso delle parti comuni\nquinta ricerca")
    assert kno_split.split(m, CASE) == ["sostituzione dei contatori dell'acqua nel supercondominio: chi decide",
                                        "opposizione del costruttore ai lavori condominiali",
                                        "allacciamento dei box alle parti comuni: responsabilità",
                                        "uso delle parti comuni"]


def test_the_owner_s_same_message_asked_again_is_not_a_source():
    again = _hit("c1", 1.0, kind="conversation", role="user", text=CASE.upper() + "  ")
    other = _hit("c2", 0.9, kind="conversation", role="user", text="Il mio box è il numero 4.")
    assert kno_split.same_message(again, CASE) and not kno_split.same_message(other, CASE)
    assert not kno_split.same_message(_hit("l1", 1.0, text=CASE), CASE)          # a law is never «the same message»


def test_each_search_brings_its_best_first_then_the_rest_by_score():
    whole = [_hit("w1", 0.18), _hit("w2", 0.09)]
    found = [[_hit("a1", 0.97), _hit("a2", 0.96), _hit("a3", 0.5), _hit("a4", 0.4)],
             [_hit("b1", 0.81), _hit("w1", 0.79), _hit("b3", 0.2)]]
    out = [h.sid for h in kno_split.merge(whole, found, top_k=4)]
    assert out == ["a1", "a2", "a3", "b1", "w1", "b3"]                          # top_k + one per search; each once


def test_the_gate_reads_the_problems_too():
    q = kno_split.with_searches("storia", ["contatori nel supercondominio", "allacci ai box"])
    assert q.startswith("storia\n\nTHE PROBLEMS IT HOLDS") and "- allacci ai box" in q
    assert kno_split.with_searches("storia", []) == "storia"


def test_verified_sentences_keep_their_paragraphs_and_headings():
    from aurora.kno_stages import PARA, _layout
    kept = ["**Contatori nel supercondominio**", "Le spese sono proporzionali [2].", "Decide l'assemblea [1].", PARA,
            "**Allacci ai box**", PARA, "**Il costruttore**", "Può essere diffidato [3].", PARA]
    assert _layout(kept) == ("**Contatori nel supercondominio**\nLe spese sono proporzionali [2]. Decide l'assemblea [1]."
                             "\n\n**Il costruttore**\nPuò essere diffidato [3].")      # a heading left alone goes


def test_a_provision_is_read_from_its_number():
    from aurora import kno_cites
    assert kno_cites.parse("art. 1117-bis c.c.") == ("1117-bis", kno_cites.CODES["c.c."])
    assert kno_cites.parse("Art. 9 d.lgs. 102/2014") == ("9", "normattiva:urn:nir:stato:decreto.legislativo:2014-%;102")
    assert kno_cites.parse("art. 6 d.P.R. 380/2001")[1].endswith("presidente.della.repubblica:2001-%;380")
    assert kno_cites.parse("il condominio") is None and kno_cites.parse("art. 3 Costituzione") is None


def test_a_case_whose_provisions_were_refused_is_read_again_as_the_story():
    """C189: with the problems listed the extraction said NONE to the civil code; once more on the story alone."""
    import pytest
    from aurora.kno_stages import Stages

    asked, answers = [], iter(["NONE", "- Art. 1117: gli impianti idrici sono parti comuni [1]."])

    def complete(system, user, max_tokens, think=False):
        asked.append(user)
        return SimpleNamespace(answer=next(answers))

    events = []
    me = SimpleNamespace(cfg={"AURORA_PIPELINE_GATE": False}, _for=lambda role: SimpleNamespace(complete=complete))
    hit = SimpleNamespace(sid="a", rerank=0.9, query_used="cited",
                          soliton=SimpleNamespace(domain="law_it", title="Codice civile", source_id="cc", text="Art. 1117"))
    question = kno_split.with_searches(CASE, ["chi decide i contatori?"])
    with pytest.raises(KeyError):                  # no synthesis settings: it stops there, the extraction is under test
        Stages._answer(me, question, [hit], "", lambda e, p: events.append((e, p)))
    assert kno_split.MARK in asked[0] and asked[1].startswith(f"QUESTION: {CASE}\n\nPASSAGES")
    assert [p["kept"] for e, p in events if e == "synthesis.domain"] == [True]
