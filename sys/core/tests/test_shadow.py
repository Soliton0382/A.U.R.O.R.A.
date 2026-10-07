# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The shadow of an answer (owner, 2026-10-05): a question close enough, whose answer the old one really is, gets it."""
from aurora import kno_shadow as K

VEC = {"Cos'è la decoerenza quantistica?": [1, 0, 0], "Che cos'è la decoerenza quantistica?": [0.97, 0.24, 0],
       "Chi ha scoperto la decoerenza?": [0.8, 0.6, 0], "Che ore sono?": [0, 0, 1]}


class Emb:
    def encode_queries(self, texts):
        return [VEC[t] for t in texts]


class RR:
    def __init__(self, s):
        self.s = s

    def score(self, pairs):
        return [self.s for _ in pairs]


def test_a_close_question_gets_the_answer_a_far_one_does_not(cfg):
    cfg.values.update(AURORA_SHADOW_COS=0.9, AURORA_SHADOW_ANSWER=0.5, AURORA_SHADOW_SURE=0.97)
    K.add(cfg, Emb(), "Cos'è la decoerenza quantistica?", "La decoerenza è… [1]", [{"source": "arxiv:1", "n": 1}])
    hit = K.find(cfg, Emb(), RR(0.99), "Che cos'è la decoerenza quantistica?")
    assert hit and hit["question"] == "Cos'è la decoerenza quantistica?" and hit["cos"] >= 0.9
    assert hit["follow"] == []
    assert K.find(cfg, Emb(), RR(0.99), "Chi ha scoperto la decoerenza?") is None      # 0.8: the same subject is not enough
    assert K.find(cfg, Emb(), RR(0.1), "Che cos'è la decoerenza quantistica?") is None  # the old answer does not answer it
    assert K.find(cfg, Emb(), RR(0.99), "Che ore sono?") is None
    assert K.stats(cfg) == {"answers": 1, "served": 1, "seed": 0}


def test_an_answer_without_sources_casts_no_shadow(cfg):
    K.add(cfg, Emb(), "Che ore sono?", "Le 10.", [])
    assert K.stats(cfg)["answers"] == 0


def test_only_seed_answers_with_public_sources_leave_and_come_back(cfg):
    pub = [{"source": "arxiv:2401.1", "n": 1, "sid": "a", "title": "T", "domain": "quantum_physics"}]
    mine = [{"source": "legacy:my_notes_pdf", "n": 1}]
    K.add(cfg, Emb(), "Cos'è la decoerenza quantistica?", "La decoerenza è… [1]", pub, origin="seed")
    K.add(cfg, Emb(), "Che ore sono?", "Le 10 [1]", mine, origin="seed")
    K.add(cfg, Emb(), "Chi ha scoperto la decoerenza?", "Zeh [1]", pub)                  # asked by the owner: stays here
    out = K.export_seed(cfg)
    assert [r["question"] for r in out] == ["Cos'è la decoerenza quantistica?"]
    imported = [{"source": "doc:76b1", "origin": "arxiv:2609.25188"}]                     # public by its passage's origin
    assert K.public(imported) and not K.public(mine) and not K.public([])
    out.append({"question": "Che ore sono?", "answer": "x", "sources": mine})              # a tampered seed
    assert K.import_seed(cfg, Emb(), out) == {"added": 0, "skipped": 2}                  # already here / not public


class ByText:
    """A re-ranker that likes one answer."""
    def __init__(self, good):
        self.good = good

    def score(self, pairs):
        return [0.9 if self.good in a else 0.6 for _, a in pairs]


def test_overlapping_shadows_the_reranker_chooses_and_the_bands(cfg):
    cfg.values.update(AURORA_SHADOW_COS=0.9, AURORA_SHADOW_ANSWER=0.5, AURORA_SHADOW_SURE=0.97)
    VEC["Decoerenza?"] = [0.96, 0.28, 0]
    K.add(cfg, Emb(), "Cos'è la decoerenza quantistica?", "Risposta A [1]", [{"source": "x", "n": 1}])
    K.add(cfg, Emb(), "Decoerenza?", "Risposta B [1]", [{"source": "y", "n": 1}])
    hit = K.find(cfg, Emb(), ByText("B"), "Che cos'è la decoerenza quantistica?")
    assert hit["text"] == "Risposta B [1]" and hit["overlap"] == 2           # not the nearest: the better answer
    assert hit["sure"] is True                                                # 0.999: no recheck
    cfg.values["AURORA_SHADOW_SURE"] = 0.98
    hit = K.find(cfg, Emb(), ByText("A"), "Che cos'è la decoerenza quantistica?")
    assert hit["text"] == "Risposta A [1]" and hit["sure"] is False          # cosine 0.9707 < 0.98: rechecked


def test_adapt_writes_again_from_the_same_passages_and_verifies():
    from types import SimpleNamespace as N
    seen = {}

    class Model:
        def stream(self, system, user, budget, think=False):
            seen["user"] = user
            yield "answer", "La decoerenza è la perdita di coerenza [1]. Inventato [2]."

    class P:
        cfg = {"AURORA_PIPELINE_THINK_TOKENS": 100, "AURORA_CHAT_STREAMING": True, "AURORA_PIPELINE_VERIFY": True}
        reader = N(get_many=lambda sids: {"a": N(text="passaggio sulla decoerenza")} if "a" in sids else {})

        def _for(self, role):
            return Model()

        def _verify(self, text, hits, emit):
            assert hits[0].soliton.text == "passaggio sulla decoerenza"
            return text.split(" Inventato")[0], ["Inventato [2]."]

    hit = {"question": "Cos'è la decoerenza?", "text": "La decoerenza… [1]", "sources": [{"n": 1, "sid": "a"}]}
    events = []
    out = K.adapt(P(), "E la decoerenza cos'è?", hit, lambda e, d: events.append(e))
    assert out == "La decoerenza è la perdita di coerenza [1]."
    assert "[1] passaggio sulla decoerenza" in seen["user"] and "NEW QUESTION: E la decoerenza cos'è?" in seen["user"]
    assert "synthesis.delta" in events
    gone = {**hit, "sources": [{"n": 1, "sid": "zz"}]}                       # a seed whose passages are not here
    assert K.adapt(P(), "E la decoerenza cos'è?", gone, lambda e, d: None) == ""


def test_a_web_answer_is_cached_until_it_expires(cfg, monkeypatch):
    cfg.values.update(AURORA_SHADOW_COS=0.9, AURORA_SHADOW_ANSWER=0.5, AURORA_SHADOW_SURE=0.97, AURORA_SHADOW_WEB_DAYS=30)
    web = [{"n": 1, "url": "https://it.wikipedia.org/wiki/Decoerenza", "title": "Decoerenza", "domain": "web"}]
    K.add(cfg, Emb(), "Cos'è la decoerenza quantistica?", "La decoerenza è… [1]", web)
    assert K.find(cfg, Emb(), RR(0.99), "Che cos'è la decoerenza quantistica?")              # the cache first
    now = K.time.time()
    monkeypatch.setattr(K.time, "time", lambda: now + 31 * 86400)                            # a month later: facts change
    assert K.find(cfg, Emb(), RR(0.99), "Che cos'è la decoerenza quantistica?") is None      # the web again
