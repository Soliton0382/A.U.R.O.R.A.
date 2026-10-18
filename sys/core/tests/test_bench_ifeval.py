# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""IFEval's checks and HumanEval's cage (owner, 2026-10-19): each check against an answer that follows it and one
that does not; the cage passes a right function and fails a wrong one, a loop, the network. Invented texts."""
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import bench_humaneval as H  # noqa: E402
import bench_ifeval as I  # noqa: E402


class Judge:
    def __init__(self, code):
        self.code, self.asked = code, 0

    def complete(self, system, text, tokens):
        self.asked += 1
        return SimpleNamespace(answer=self.code)


CASES = [  # (id, kwargs, followed, not followed)
    ("punctuation:no_comma", {}, "Il gatto dorme. Il cane no.", "Il gatto, il cane."),
    ("length_constraints:number_words", {"relation": "at least", "num_words": 5}, "one two three four five", "one two"),
    ("length_constraints:number_words", {"relation": "less than", "num_words": 3}, "one two", "one two three"),
    ("length_constraints:number_sentences", {"relation": "less than", "num_sentences": 3},
     "Dr. Rossi arrived. He left.", "One. Two. Three."),
    ("length_constraints:number_paragraphs", {"num_paragraphs": 2}, "first\n***\nsecond", "first\n***\n\n***\nsecond"),
    ("length_constraints:nth_paragraph_first_word", {"num_paragraphs": 2, "nth_paragraph": 2, "first_word": "rain"},
     "Sun today.\n\n\"Rain, tomorrow.", "Sun today.\n\nSnow tomorrow."),
    ("detectable_format:number_bullet_lists", {"num_bullets": 2}, "* uno\n- due", "* uno\n* due\n* tre"),
    ("detectable_format:number_highlighted_sections", {"num_highlights": 2}, "*one* and **two**", "*one* and **  **"),
    ("detectable_format:title", {}, "<<A day at sea>>\ntext", "<< >>\ntext"),
    ("detectable_format:json_format", {}, "```json\n{\"a\": 1}\n```", "{a: 1}"),
    ("detectable_format:multiple_sections", {"section_spliter": "Section", "num_sections": 2},
     "Section 1\nx\nSection 2\ny", "Section 1\nx"),
    ("detectable_format:constrained_response", {}, "My answer is maybe.", "Maybe."),
    ("detectable_content:number_placeholders", {"num_placeholders": 2}, "Dear [name], at [address]", "Dear [name]"),
    ("detectable_content:postscript", {"postscript_marker": "P.S."}, "Bye.\nP.S. see you", "Bye. PS see you"),
    ("detectable_content:postscript", {"postscript_marker": "P.P.S"}, "Bye.\nP.P.S more", "Bye.\nP.S. more"),
    ("keywords:existence", {"keywords": ["orbit", "comet"]}, "A comet in orbit.", "A comet."),
    ("keywords:forbidden_words", {"forbidden_words": ["rock"]}, "rocky shores", "a rock here"),
    ("keywords:frequency", {"keyword": "tide", "relation": "at least", "frequency": 2}, "tide and Tide", "tide"),
    ("keywords:letter_frequency", {"letter": "z", "let_relation": "less than", "let_frequency": 2}, "zero", "zizz"),
    ("change_case:capital_word_frequency", {"capital_relation": "at least", "capital_frequency": 2},
     "NASA and ESA", "NASA and esa"),
    ("change_case:english_lowercase", {}, "all quiet here", "All quiet here"),
    ("change_case:english_capital", {}, "ALL QUIET HERE", "ALL quiet"),
    ("combination:repeat_prompt", {"prompt_to_repeat": "Tell me a riddle."}, "tell me a riddle. What has keys?",
     "Sure! What has keys?"),
    ("combination:two_responses", {}, "Uno.\n******\nDue.", "Uno.\n******\nUno."),
    ("startend:end_checker", {"end_phrase": "Any questions?"}, "That is all. Any questions?\"", "Any questions? Bye."),
    ("startend:quotation", {}, "\"A quoted reply\"", "A reply"),
]


@pytest.mark.parametrize("iid,kw,good,bad", CASES, ids=[c[0] + str(i) for i, c in enumerate(CASES)])
def test_each_check_tells_followed_from_not(iid, kw, good, bad):
    judge = Judge("en")
    assert I.follows(iid, kw, good, judge=judge)
    assert not I.follows(iid, kw, bad, judge=judge)


def test_the_language_is_the_judges_code_asked_once_a_text():
    judge = Judge("Language: hi")
    assert I.follows("language:response_language", {"language": "hi"}, "नमस्ते दुनिया", judge=judge)
    assert not I.follows("language:response_language", {"language": "it"}, "नमस्ते दुनिया", judge=judge)
    assert judge.asked == 1


def test_a_prompt_is_right_only_with_every_instruction_and_loose_forgives_the_markdown():
    item = {"prompt": "x", "instructions": ["punctuation:no_comma", "startend:quotation"], "kwargs": [{}, {}]}
    assert I.score(item, "\"Yes indeed\"")["right"]
    s = I.score(item, "Yes, indeed")
    assert not s["right"] and s["got"] == "0/2" and s["missed"] == item["instructions"]
    s = I.score(item, "Here it is\n\"Yes indeed\"")                    # a line the model added before
    assert not s["right"] and s["loose_right"]


def test_items_drop_the_rows_api_empty_arguments():
    rows = [{"key": 7, "prompt": "p", "instruction_id_list": ["punctuation:no_comma"],
             "kwargs": [{"num_words": None, "relation": None}]}]
    assert I.items(rows)[0]["kwargs"] == [{}]


ITEM = {"entry_point": "add", "header": "import math\n\n\ndef add(a, b):\n    \"\"\"a + b\"\"\"\n",
        "test": "def check(c):\n    assert c(2, 3) == 5\n    assert math.pi > 3\n"}


@pytest.mark.skipif(not shutil.which("bwrap"), reason="no cage on this machine")
def test_humaneval_runs_the_answer_in_the_cage():
    assert H.score(ITEM, "Sure:\n```python\ndef add(a, b):\n    return a + b\n```")["right"]
    assert H.score(ITEM, "```\n    return a + b\n```")["right"]                       # only the body
    assert not H.score(ITEM, "```python\ndef add(a, b):\n    return a - b\n```")["right"]
    net = "```python\ndef add(a, b):\n    import socket\n    socket.create_connection(('192.0.2.1', 80), 2)\n    return a + b\n```"
    assert not H.score(ITEM, net)["right"]


@pytest.mark.skipif(not shutil.which("bwrap"), reason="no cage on this machine")
def test_humaneval_stops_a_loop(monkeypatch):
    monkeypatch.setattr(H, "SECONDS", 2)
    assert H.score(ITEM, "```python\ndef add(a, b):\n    while True:\n        pass\n```")["got"] == "more than 2 s"
