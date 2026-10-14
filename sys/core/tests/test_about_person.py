# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What she knows of the person asking reaches a question about the world (C321: a Nutella dessert advised a day after
«Sono allergico alle nocciole»)."""
from types import SimpleNamespace

from aurora import kno_about, kno_read


def note(text, **extra):
    return SimpleNamespace(soliton=SimpleNamespace(text=text, extra=extra))


def person(reply, hits):
    asked = []
    model = SimpleNamespace(complete=lambda system, text, n: asked.append(text) or SimpleNamespace(answer=reply))
    search = SimpleNamespace(search=lambda q, t, top_k, sections: hits if sections == {"memory"} else [])
    return SimpleNamespace(search=search, _for=lambda role: model), asked


def test_an_allergy_said_before_reaches_the_advice():
    p, asked = person("The person is allergic to hazelnuts.",
                      [note("Sono allergico alle nocciole, quindi niente dolci con le nocciole per me.", role="user"),
                       note("Ecco tre idee per la cena.", role="assistant"),            # her own words: not facts
                       note("Ha detto di portare il 44 di scarpe.", type="session_memory")])
    seen = []
    block = kno_about.facts(p, "Mi consigli un dolce alla Nutella per stasera?", lambda e, d: seen.append(d))
    assert "allergic to hazelnuts" in block and "say so plainly first" in block
    assert "nocciole" in asked[0] and "tre idee" not in asked[0] and "44" in asked[0]
    p.__dict__.update(_lessons="", _about=block)
    assert "allergic to hazelnuts" in kno_read._exp(p) and "allergic" not in kno_read._exp(p, about=False)


def test_nothing_is_added_when_no_fact_bears_on_the_question():
    p, _ = person("NONE", [note("Porto il 44 di scarpe.", role="user")])
    seen = []
    assert kno_about.facts(p, "Chi ha scritto il Decameron?", lambda e, d: seen.append(d)) == ""
    assert seen[0]["facts"] is None
    p, asked = person("unused", [])
    assert kno_about.facts(p, "Chi ha scritto il Decameron?", lambda e, d: None) == "" and not asked
