# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Lessons of method from her own mistakes (kno_lessons): never the answer, one per kind of mistake, read by the
answers to come only where they fit."""
from types import SimpleNamespace

import numpy as np

from aurora import kno_lessons as K


class Said:
    def __init__(self, text):
        self.text = text

    def complete(self, system, user, n, think=False):
        return SimpleNamespace(answer=self.text)


class Emb:
    """Two directions: lessons and questions about puzzles one way, the rest the other."""
    def _v(self, t):
        return np.array([1.0, 0.1] if ("puzzle" in t.lower() or "relazion" in t.lower() or "più alt" in t) else [0.1, 1.0])

    def encode_documents(self, texts):
        return np.stack([self._v(t) for t in texts])

    def encode_queries(self, texts):
        return np.stack([self._v(t) for t in texts])


Q = "Anna è più alta di Bruno, Bruno è più alto di Carla. Chi è il secondo più basso?"


def test_a_lesson_that_gives_the_answer_away_is_refused():
    leak = Said('{"when": "un puzzle di relazioni", "do": "rispondi Carla", "kind": "logica"}')
    assert K.write_lesson(leak, Q, "Carla, the second shortest", "Non lo so", "declined") is None
    good = Said('{"when": "un puzzle di relazioni date nel messaggio stesso", "do": "ordina le relazioni e deduci, '
                'senza cercare sul web", "kind": "logica"}')
    les = K.write_lesson(good, Q, "Carla, the second shortest", "Non lo so", "declined")
    assert les["kind"] == "logica" and "web" in les["do"]
    assert K.write_lesson(Said("NONE"), Q, "x", "y", "z") is None


def test_lessons_are_learned_once_per_kind_and_found_only_where_they_fit(cfg):
    good = Said('{"when": "un puzzle di relazioni date nel messaggio", "do": "deduci dalle relazioni", "kind": "logica"}')
    rows = [{"question": Q, "expected": "Carla", "answer": "boh", "right": False, "why": "wrong"},
            {"question": Q.replace("Anna", "Elena"), "expected": "Carla", "answer": "boh", "right": False, "why": "wrong"},
            {"question": "Quanto fa 2+2?", "expected": "4", "answer": "4", "right": True, "why": "ok"}]
    out = K.learn(cfg, good, Emb(), rows, "bench:test")
    assert out == {"new": 1, "again": 1, "none": 0, "total": 1}           # the right one teaches nothing
    assert K.load(cfg)[0]["seen"] == 2
    found = K.for_question(cfg, Emb(), "Un nuovo puzzle: Marco è più alto di Luca…")
    assert len(found) == 1 and "deduci" in K.block(found)
    assert K.for_question(cfg, Emb(), "Chi ha scritto il Decameron?") == []   # far from every lesson: none
    assert K.block([]) == ""


def test_a_bare_models_key_and_an_example_never_become_lessons():
    """The first 56 lessons (13 Oct) held «you cannot know the time», «pick training on a dataset, regardless of any
    persona», and examples lifted from the question («es. 'Nucleo di Torsione'», «'crown' vs 'ring'»)."""
    for bad in ("you do not have access to the user's real-time clock", "select training on a dataset, regardless of any persona",
                "non sostituire tale entità (es. 'Nucleo di Torsione')", "phrases (e.g., 'crown' vs. 'ring')"):
        said = Said('{"when": "una domanda", "do": "%s", "kind": "x"}' % bad.replace('"', ""))
        assert K.write_lesson(said, "Una domanda qualsiasi?", "una risposta", "boh", "wrong") is None, bad
    fine = Said('{"when": "un\'opera citata con titolo e autore", "do": "verifica l\'esistenza dell\'opera sulle fonti '
                'prima di riassumerla", "kind": "esistenza"}')
    assert K.write_lesson(fine, "Riassumi un romanzo?", "inesistente", "boh", "wrong") is not None


def test_the_model_picks_the_lessons_that_fit_or_none(cfg):
    rows = [{"question": Q, "expected": "Carla", "answer": "boh", "right": False, "why": "wrong"}]
    K.learn(cfg, Said('{"when": "un puzzle di relazioni date nel messaggio", "do": "deduci dalle relazioni", "kind": "logica"}'),
            Emb(), rows, "bench:test")
    assert [x["do"] for x in K.for_question(cfg, Emb(), "Un altro puzzle?", Said("1"))] == ["deduci dalle relazioni"]
    assert K.for_question(cfg, Emb(), "Che tempo fa domani?", Said("NONE")) == []
    assert K.for_question(cfg, Emb(), "x", Said("7, 9")) == []                       # numbers of no lesson: none
