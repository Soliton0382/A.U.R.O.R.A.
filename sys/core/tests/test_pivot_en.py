# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The English pivot (owner, 10 Oct): a question in Italian worked out in English, the answer translated back with its
citations where they were — or left in English when the translation loses one."""
from types import SimpleNamespace

from aurora.kno_answer import Pipeline


def pipeline(reply):
    p = object.__new__(Pipeline)
    asked = []
    p._for = lambda role: SimpleNamespace(complete=lambda system, text, n: asked.append(system) or
                                          SimpleNamespace(answer=reply))
    return p, asked


def test_the_answer_comes_back_in_the_language_of_the_question():
    p, asked = pipeline("La decoerenza distrugge l'interferenza [1]. Dipende dall'ambiente [2].")
    seen = []
    out = p._back("Decoherence destroys interference [1]. It depends on the environment [2].", "it",
                  lambda e, d: seen.append((e, d)))
    assert out.startswith("La decoerenza") and "Italian" in asked[0] and seen[0][1]["lang"] == "it"


def test_a_translation_that_loses_a_citation_is_not_used():
    p, _ = pipeline("La decoerenza distrugge l'interferenza e dipende dall'ambiente [1].")
    english = "Decoherence destroys interference [1]. It depends on the environment [2]."
    seen = []
    assert p._back(english, "it", lambda e, d: seen.append(d)) == english
    assert seen[0]["why"] == "citations changed"


def test_a_long_question_is_translated_whole_or_not_pivoted():
    """C269: the translation had 200 tokens; with the pivot, a long question cut short became the question."""
    from aurora.kno_answer import translate_budget, whole
    grid = "Puzzle: " + "0 1 2 3 4 5 6 7 8 9\n" * 100                       # about 2,000 characters
    assert translate_budget("Che ore sono?") == 200 and translate_budget(grid) >= len(grid) // 2
    assert whole(grid, grid.replace("Puzzle", "Puzzle (en)"))
    assert not whole(grid, "Puzzle: 0 1 2 3")                                  # cut: stay on the question as asked
    assert whole("Che ore sono?", "What time is it?") and not whole("Che ore sono?", "  ")


def test_a_translation_that_keeps_only_the_last_sentence_is_not_the_question():
    """C286: the facts of a puzzle lost in the translation made it a fact to look up on the web."""
    from aurora.kno_answer import whole
    q = ("Anna è più alta di Bruno, Bruno è più alto di Carla e Dario è più basso di Carla. "
         "Chi è il secondo più basso?")
    assert not whole(q, "Who is the second shortest?")
    assert whole(q, "Anna is taller than Bruno, Bruno is taller than Carla and Dario is shorter than Carla. "
                    "Who is the second shortest?")
    assert whole("Chi ha scritto il Decameron?", "Who wrote it?")                 # a short question: not judged


def test_no_search_of_her_own_for_a_question_asked_without_memory():
    """C287: a benchmark's question (remember: false) never starts the autonomous acquisition."""
    from pathlib import Path                                  # the route itself needs the whole app to import
    src = (Path(__file__).resolve().parents[1] / "aurora" / "api" / "core_route.py").read_text(encoding="utf-8")
    assert 'cfg["AURORA_ACQUIRE_AUTO"] and remember and ans.abstained' in src
