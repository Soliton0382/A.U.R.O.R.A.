# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The memory searched while the person still speaks (sol_ahead; owner, 19 Oct): the answer takes the search done on
the same words, waits for it when it is running, and never gets the recall of other words. Invented questions."""
import threading
import time

from aurora import sol_ahead

KW = {"translation": None, "candidates": None, "top_k": 12, "sections": {"memory"}, "recall": None}


class Slow:
    def __init__(self, seconds=0.0):
        self.asked, self.seconds, self.gate = [], seconds, threading.Event()

    def __call__(self, question, **kw):
        self.asked.append(question)
        time.sleep(self.seconds)
        return [f"hit for {question}"]


def wait_idle(a, s=2.0):
    end = time.monotonic() + s
    while a._worker is not None and time.monotonic() < end:
        time.sleep(0.01)


def test_the_same_text_is_taken_once_spaces_aside_never_another_case():
    search = Slow()
    a = sol_ahead.Ahead(search)
    a.submit(" Come si chiama  il mio gatto? ", **KW)
    wait_idle(a)
    assert a.take("come si chiama il mio gatto", KW) is None           # the re-ranker reads case and punctuation
    assert a.take("Come si chiama il mio gatto?", KW) == ["hit for  Come si chiama  il mio gatto? "]
    assert a.take("Come si chiama il mio gatto?", KW) is None          # once: a second ask searches again
    assert search.asked == [" Come si chiama  il mio gatto? "]


def test_other_words_or_other_parameters_are_never_given_the_result():
    a = sol_ahead.Ahead(Slow())
    a.submit("Come si chiama il mio", **KW)
    wait_idle(a)
    assert a.take("Come si chiama il mio gatto?", KW) is None          # the last word was not in it yet
    assert a.take("Come si chiama il mio", {**KW, "sections": None}) is None   # the knowledge route's search


def test_the_answer_waits_for_its_words_still_being_searched():
    search = Slow(0.3)
    a = sol_ahead.Ahead(search)
    a.submit("Che lavoro faccio?", **KW)
    time.sleep(0.05)
    t = time.monotonic()
    assert a.take("Che lavoro faccio?", KW) == ["hit for Che lavoro faccio?"]
    assert time.monotonic() - t < 0.5 and search.asked == ["Che lavoro faccio?"]   # not searched twice


def test_only_the_latest_words_wait_never_a_queue():
    search = Slow(0.2)
    a = sol_ahead.Ahead(search)
    a.submit("mi consigli", **KW)
    time.sleep(0.05)                                          # running
    a.submit("mi consigli un dolce", **KW)
    a.submit("mi consigli un dolce per stasera", **KW)          # replaces the one still waiting
    wait_idle(a)
    assert search.asked == ["mi consigli", "mi consigli un dolce per stasera"]


def test_words_not_started_yet_are_searched_by_the_asker_itself():
    search = Slow(0.3)
    a = sol_ahead.Ahead(search)
    a.submit("prima frase", **KW)
    time.sleep(0.05)
    a.submit("Che numero di scarpe porto?", **KW)                # waiting behind the first
    assert a.take("Che numero di scarpe porto?", KW) is None    # taken out of the queue: the asker searches now
    wait_idle(a)
    assert search.asked == ["prima frase"]


def test_an_old_result_is_not_used():
    a = sol_ahead.Ahead(Slow())
    a.submit("Ti ricordi ieri?", **KW)
    wait_idle(a)
    k = sol_ahead.key("Ti ricordi ieri?", KW)
    hits, at = a._done[k]
    a._done[k] = (hits, at - sol_ahead.KEEP_S - 1)
    assert a.take("Ti ricordi ieri?", KW) is None
