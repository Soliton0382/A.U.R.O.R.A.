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
    cfg.values.update(AURORA_SHADOW_COS=0.9, AURORA_SHADOW_ANSWER=0.5)
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
