# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A document's domain by what it says (kno_domain, M195): the model's answer when it is a knowledge domain, the
list's domain otherwise; the descriptions travel with the names."""
from types import SimpleNamespace

from aurora import kno_domain as K


class Said:
    def __init__(self, word):
        self.word, self.seen = word, []

    def complete(self, system, user, n):
        if isinstance(self.word, Exception):
            raise self.word
        self.seen.append(system)
        return SimpleNamespace(answer=self.word)


def test_the_model_reads_and_a_wrong_answer_keeps_the_lists_domain():
    m = Said("philosophy")
    assert K.choose(m, "Philosophy of science", "The philosophy of science studies…", "religion") == "philosophy"
    assert "Italian law only" in m.seen[0]                       # law_it described: «Genocide» is not Italian law
    assert K.choose(Said("music"), "Louis Armstrong", "…", "general") == "general"          # not a domain
    assert K.choose(Said("conversation"), "x", "…", "general") == "general"                 # memory is not knowledge
    assert K.choose(Said(RuntimeError("down")), "x", "…", "history") == "history"
