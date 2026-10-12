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
