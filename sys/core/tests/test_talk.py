# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎙️ The quick path of a spoken turn (kno_talk) and the call's sayable pieces (sys_call.ready). Invented sentences."""
from __future__ import annotations

from types import SimpleNamespace

from aurora import kno_talk
from aurora.sys_call import ready as _ready


class Model:
    def __init__(self, search: float | None, pieces: list[str]):
        self.search, self.pieces, self.asked = search, pieces, []

    def decide(self, system, user, options):
        self.asked.append(user)
        return None if self.search is None else {"TALK": 1 - self.search, "SEARCH": self.search}

    def complete(self, system, user, n):
        return SimpleNamespace(answer="SEARCH")

    def stream(self, system, user, n, think=False):
        assert think is False                          # spoken: never the thinking
        for x in self.pieces:
            yield "answer", x


def _run(cfg, model, question="Ciao, come va?"):
    p, said = SimpleNamespace(llm=model, _for=lambda role: None), []   # never the Models page's «self»
    out = kno_talk.quick(p, cfg, question, [], lambda ev, pl: said.append((ev, pl["text"])))
    return out, said


def test_plain_talk_is_streamed_at_once(cfg):
    (text, handed), said = _run(cfg, Model(0.02, [" Tutto", " bene,", " e tu?"]))
    assert (text, handed) == ("Tutto bene, e tu?", False)
    assert [s for _, s in said] == ["Tutto", " bene,", " e tu?"]


def test_anything_to_check_goes_to_the_whole_path_unsaid(cfg):
    (text, handed), said = _run(cfg, Model(0.99, ["mai detto"]), "Che tempo fa domani?")
    assert (text, handed, said) == ("", True, [])


def test_an_unreadable_choice_is_asked_in_words_and_unsure_means_search(cfg):
    assert _run(cfg, Model(None, ["x"]))[0] == ("", True)


def test_a_lean_to_search_under_sure_still_talks(cfg):
    assert _run(cfg, Model(0.65, ["Respira piano."]))[0] == ("Respira piano.", False)


def test_a_fact_started_anyway_is_cut_and_handed_on(cfg):
    (text, handed), said = _run(cfg, Model(0.1, ["Bella domanda.", " ⏩ 0.0072"]))
    assert (text, handed) == ("Bella domanda.", True) and "0.0072" not in "".join(s for _, s in said)


def test_nothing_said_goes_to_the_whole_path(cfg):
    assert _run(cfg, Model(0.1, ["  ", ""]))[0] == ("", True)


def test_the_call_says_whole_sentences_and_a_long_one_at_its_comma():
    assert _ready("Ciao! Come") == ("Ciao! ", "Come")
    assert _ready("Pi vale 3.14 circa") == ("", "Pi vale 3.14 circa")      # a decimal point is not an end
    long = "Questa è una frase molto lunga, " * 5 + "senza fine"
    now, rest = _ready(long)
    assert now.endswith(",") and rest.endswith("senza fine") and len(now) > kno_talk.MAX_TOKENS // 4
