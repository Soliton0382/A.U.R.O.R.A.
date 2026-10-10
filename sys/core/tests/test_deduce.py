# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Deductions (roadmap 77, owner 10 Oct: «come un colpo di genio… una correlazione forte e verificata… guardare le cose
da un'altra prospettiva»): a bridge between distant fields that passes five tests, then the owner's judgement."""
import json
from types import SimpleNamespace as N

import pytest

from aurora import kno_deduce as D

BRIDGE = json.dumps({"a_fact": "Cubism shows an object from several viewpoints at once.",
                     "b_fact": "Synergy is information present only in the joint distribution of variables.",
                     "deduction": "A model that looks at several variables at once can see what each single view misses.",
                     "perspective": "Missing synergy is a problem of perspective, not of data.",
                     "test": "Compare single-view and joint models on data with known synergy."})


def sol(sid, domain, title, source, text="x " * 50, kind="knowledge"):
    return N(sid=sid, domain=domain, title=title, source_id=source, text=text, kind=kind)


class LLM:
    def __init__(self, replies):
        self.replies, self.asked = list(replies), []

    def complete(self, system, text, n):
        self.asked.append(system[:30])
        return N(answer=self.replies.pop(0))


def pipeline(A, B, llm, judge, hits=()):
    roles = {"synthesis": llm, "verify": judge, "translate": LLM(["tradotto"] * 10), "service": llm}
    return N(reader=N(get_many=lambda ids: {A.sid: A, B.sid: B}), _for=lambda r: roles[r],
             search=N(search=lambda q: list(hits), embedder=N(encode_queries=lambda t: [[1.0, 0.0], [0.0, 1.0]])))


CAND = {"a": "a1", "b": "b1", "da": "literature", "db": "physics", "w": 0.8, "level": 0}


def test_a_bridge_that_passes_the_five_tests_is_a_deduction(cfg):
    A = sol("a1", "literature", "Cubism", "wikipedia:Cubism")
    B = sol("b1", "physics", "Statistical Dark Matter", "arxiv:2501.1")
    other = N(sid="c1", rerank=0.9, soliton=sol("c1", "physics", "Other", "arxiv:2", "unrelated"))
    judge = LLM(["NO", "YES", "YES", "YES", "NO"])        # same subject? no; fact A, fact B, follows: yes; already said: no
    r = D.examine(pipeline(A, B, LLM([BRIDGE]), judge, [other]), cfg, CAND)
    assert (r["outcome"], r["known"], r["score"]) == ("deduction", 0.9, 0.8)


@pytest.mark.parametrize("judge, outcome", [
    (["YES"], "same subject (judged)"),
    (["NO", "NO"], "first fact not in its passage"),
    (["NO", "YES", "NO"], "second fact not in its passage"),
    (["NO", "YES", "YES", "NO"], "does not follow"),
    (["NO", "YES", "YES", "YES", "YES"], "already in the vault"),
])
def test_each_test_stops_what_fails_it(cfg, judge, outcome):
    A = sol("a1", "literature", "Cubism", "wikipedia:Cubism")
    B = sol("b1", "physics", "Statistical Dark Matter", "arxiv:2501.1")
    hit = N(sid="c1", rerank=0.95, soliton=sol("c1", "physics", "Other", "arxiv:2"))
    assert D.examine(pipeline(A, B, LLM([BRIDGE]), LLM(judge), [hit]), cfg, CAND)["outcome"] == outcome


def test_one_subject_under_two_labels_and_service_texts_are_no_pairs(cfg):
    euclid = (sol("a1", "literature", "Euclid's Elements", "wikipedia:Euclid's_Elements"),
              sol("b1", "general", "Euclid", "wikipedia:Euclid"))
    assert D.examine(pipeline(*euclid, LLM([]), LLM([])), cfg, CAND)["outcome"] == "same subject"
    boiler = (sol("a1", "economics", "Mempool", "arxiv:1", "Safeguards: [NA] Justification: no high-risk assets."),
              sol("b1", "biomedicine", "pCoMole", "arxiv:2"))
    assert D.examine(pipeline(*boiler, LLM([]), LLM([])), cfg, CAND)["outcome"] == "service text"
    assert D.examine(pipeline(sol("a1", "x", "t", "s", kind="conversation"), sol("b1", "y", "u", "v"), LLM([]), LLM([])),
                     cfg, CAND)["outcome"] == "not knowledge"


def test_the_owner_judges_and_the_pairs_are_looked_at_once(cfg, monkeypatch):
    A = sol("a1", "literature", "Cubism", "wikipedia:Cubism")
    B = sol("b1", "physics", "Statistical Dark Matter", "arxiv:2501.1")
    monkeypatch.setattr(D, "far_pairs", lambda p, c, docs: [dict(CAND)])
    monkeypatch.setattr(D, "candidates", lambda c, n: [])
    import aurora.kno_train as T
    monkeypatch.setattr(T, "documents", lambda r, n, rng: [])
    p = pipeline(A, B, LLM([BRIDGE]), LLM(["NO", "YES", "YES", "YES", "NO"]))
    out = D.round_(p, cfg, lambda e, d: None, 3)
    assert out["deductions"] == 1 and D.deduced_tonight(cfg)
    assert D.round_(p, cfg, lambda e, d: None, 3)["looked"] == 0                    # the same pair: never again
    d = D.listing(cfg)[0]
    assert d["text"] == "tradotto" and d["a_fact"].startswith("Cubism")
    assert D.judge(cfg, d["id"], "flash")["verdict"] == "flash" and D.listing(cfg)[0]["verdict"] == "flash"
    with pytest.raises(ValueError):
        D.judge(cfg, d["id"], "maybe")
    md = D.as_markdown(p, D.listing(cfg)[0])
    assert "Cubism" in md and "arxiv:2501.1" in md and "ipotesi da controllare" in md
