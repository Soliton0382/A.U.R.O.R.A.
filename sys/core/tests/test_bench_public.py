# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The public test sets' scoring (bench_public_data): what is read from Aurora's answer, as each set defines it."""
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import bench_public_data as D  # noqa: E402


def test_the_letter_the_number_and_the_grid_are_read_after_the_last_answer_line():
    assert D.letter("Ragiono… l'opzione B sembra… ma no.\nRisposta: **D**") == "D"
    assert D.letter("Answer: (K) thirteen options") == "K"
    assert D.letter("non lo so") == ""
    assert D.integer("passaggi 12, 30…\nRisposta: 1,024") == "1024" and D.integer("Risposta: \\boxed{70}") == "70"
    assert D.grid("Prima prova:\n1 2\nRisposta:\n0 1 2\n3 4 5\n\nFine.") == "0 1 2\n3 4 5"


def test_math_is_compared_as_text_first_and_judged_only_when_it_differs():
    item = {"kind": "math", "answer": "\\frac{1}{2}"}
    calls = []

    class Judge:
        def complete(self, system, user, n):
            calls.append(user)
            return SimpleNamespace(answer="YES")
    assert D.score(item, "… quindi \\boxed{\\dfrac{1}{2}}", Judge())["right"] and calls == []
    assert D.score(item, "Risposta: 0.5", Judge()) == {"right": True, "got": "0.5", "judged": True} and len(calls) == 1


def test_simpleqa_has_three_grades_and_only_correct_counts():
    item = {"kind": "simpleqa", "prompt": "Q?", "answer": "Rome"}
    for word, right in (("CORRECT", True), ("INCORRECT", False), ("NOT_ATTEMPTED", False)):
        j = SimpleNamespace(complete=lambda *a, w=word: SimpleNamespace(answer=w))
        out = D.score(item, "…", j)
        assert out["grade"] == word and out["right"] is right


def test_the_sample_is_the_same_every_run_and_options_are_shuffled_with_the_right_one_kept():
    items = [{"id": str(i)} for i in range(100)]
    assert D.sample(items, 10) == D.sample(items, 10) and len(D.sample(items, 10)) == 10 and D.sample(items, 0) == items
    opts, letter = D._shuffled("right", ["w1", "w2", "w3"], random.Random(3))
    assert opts[D.LETTERS.index(letter)] == "right" and sorted(opts) == ["right", "w1", "w2", "w3"]


def test_what_only_aurora_has_is_scored_on_the_truth_of_now(cfg, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda: cfg)                # bench_forge reads the settings when imported
    import bench_edge as E
    nums = {"kind": "numbers", "answer": {"active": 30, "total": 31}}
    assert E.score(nums, "Hai 30 routine attive su 31.", None)["right"]
    assert not E.score(nums, "Non posso saperlo: non ho accesso alle tue routine.", None)["right"]
    sw = {"kind": "onoff", "answer": {"state": "on"}}
    assert E.score(sw, "In questo momento è acceso.", None)["right"]
    assert not E.score(sw, "È spento.", None)["right"] and not E.score(sw, "Non lo so.", None)["right"]
