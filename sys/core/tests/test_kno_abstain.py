# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""M188: a declined answer says why — the future cannot be known, what has no trace is not told — and only the rest
is studied at night."""
from datetime import date
from types import SimpleNamespace

from aurora import kno_abstain


class Said:
    def __init__(self, word):
        self.word, self.seen = word, []

    def complete(self, system, user, n):
        if isinstance(self.word, Exception):
            raise self.word
        self.seen.append((system, user))
        return SimpleNamespace(answer=self.word)


def test_the_future_is_said_as_unknowable_not_promised_for_tonight():
    llm = Said("FUTURE")
    assert kno_abstain.kind(llm, "Chi vincerà il Nobel per la fisica 2031?", date(2026, 10, 13)) == "future"
    assert "2026-10-13" in llm.seen[0][0]                      # the model knows what today is
    t = kno_abstain.text("future", "it", date(2026, 10, 13))
    assert "13/10/2026" in t and "nessuno può saperlo" in t and "stanotte" not in t


def test_a_thing_with_no_trace_is_not_told_nor_studied():
    assert kno_abstain.kind(Said("No trace."), "Riassumi «Le nebbie di Tarvelion»") == "no_trace"
    t = kno_abstain.text("no_trace", "it")
    assert "non esiste" in t and "stanotte" not in t
    assert set(kno_abstain.NOT_STUDIED) == {"future", "no_trace"}


def test_anything_else_or_a_failure_keeps_the_old_sentence():
    assert kno_abstain.kind(Said("OPEN"), "x") == "open"
    assert kno_abstain.kind(Said("boh"), "x") == "open"
    assert kno_abstain.kind(Said(RuntimeError("down")), "x") == "open"
    assert "stanotte" in kno_abstain.text("open", "it") and "tonight" in kno_abstain.text("weird", "en")


def test_only_a_later_year_is_asked_before_searching():
    today = date(2026, 10, 13)
    assert kno_abstain.later_year("Chi ha vinto il Nobel per la fisica nel 2031?", today)
    assert not kno_abstain.later_year("Chi ha vinto il Nobel per la fisica nel 2025?", today)
    assert not kno_abstain.later_year("Quanto fa 2027 per 3?", date(2027, 1, 1))
    assert "forecasts, projections" in kno_abstain.SYS_WHY        # an IPCC projection for 2050 is not «future»
