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


def test_an_exercise_worked_out_instead_of_translated_is_not_the_question():
    """C320: the local translator solved 26 of 60 exercises; the half solution became the question the cloud read."""
    from aurora.kno_answer import translate_budget, whole
    from aurora.kno_stages import SYS_TRANSLATE, as_text, untag
    q = ("A 7-hp motor takes 6.3 kilowatts at full load. What is its efficiency?\n\nA) 75%\nB) 86%\nC) 83%\n\n"
         "Rispondi alla domanda. Alla fine scrivi su una riga a sé «Risposta: X».")
    solved = ("To find the efficiency we compare output and input power.\n1. Output: 7 hp = 5.222 kW\n"
              "2. Input: 6.3 kW\n3. Efficiency = 5.222 / 6.3 = 82.9%, so the answer is C) 83%.")
    assert not whole(q, solved)                                               # the options gone: not a translation
    assert not whole("Quanto fa 2+2?", "2 + 2 = 4. " * 20)                    # far longer than the question
    assert whole(q, q.replace("Rispondi alla domanda", "Answer the question"))
    assert "never answer it" in SYS_TRANSLATE and as_text("x") == "<text>\nx\n</text>"
    assert untag("<text>\nWhat time is it?\n</text>") == "What time is it?"
    grid = "0 0 0 1 0\n" * 200                                                # one token a character
    assert translate_budget(grid) >= len(grid) or translate_budget(grid) == 4000


def test_a_translation_back_that_loses_the_answer_line_or_most_of_it_is_not_used():
    """C320: the solution cut at «Verifica: f(20, 30) =», the last line «Risposta: 70√2» gone."""
    english = "Complete the squares.\n" + "The three vectors add up to (70, 70). " * 10 + "\n\n**Answer: 70√2**"
    p, _ = pipeline("Completa i quadrati.\n" + "I tre vettori sommano a (70, 70). " * 10 + "\nVerifica: f(20, 30) =")
    seen = []
    assert p._back(english, "it", lambda e, d: seen.append(d)) == english and seen[0]["why"] == "answer line lost"
    p, _ = pipeline("Completa i quadrati.")
    seen = []
    assert p._back(english, "it", lambda e, d: seen.append(d)) == english and seen[0]["why"] == "cut short"
    p, _ = pipeline("Completa i quadrati.\n" + "I tre vettori sommano a (70, 70). " * 10 + "\n\n**Risposta: 70√2**")
    assert p._back(english, "it", lambda e, d: None).endswith("**Risposta: 70√2**")


def test_a_grid_of_digits_is_not_translated():
    """C320: an ARC grid translated whole cost 7.5 s more a puzzle; the solution reads it as it is."""
    from aurora.kno_answer import wordy
    grid = "Puzzle di ragionamento astratto: trova la regola.\n" + "0 0 0 1 0 0 2 0 0 0\n" * 40
    assert not wordy(grid)
    assert wordy("Per $0 \\le x \\le 40$ trova il minimo di \\[\\sqrt{x^2 + 400}\\].") and wordy("Che ore sono?")
