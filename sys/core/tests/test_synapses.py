# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Synapses (owner, 2026-10-05): links between passages of different domains that grow, strengthen and fade."""
import time
from types import SimpleNamespace

from aurora import kno_synapse as S

P = {"p1": "physics", "p2": "physics", "b1": "biomedicine", "l1": "literature"}


class Reader:
    layout = SimpleNamespace(domains=lambda section: ["physics", "biomedicine"])

    def iter_domain(self, d, after=None):
        rows = [(k, i, SimpleNamespace(sid=k, text=k, domain=d)) for i, k in enumerate(x for x in P if P[x] == d)]
        return [r for r in rows if after is None or r[1] > after[1]]

    def get_many(self, sids):
        return {s: SimpleNamespace(sid=s, domain=P[s]) for s in sids if s in P}


class Index:
    NEAR = {"p1": [("p2", 0.95), ("b1", 0.81), ("l1", 0.60)], "p2": [("p1", 0.95)], "b1": [("p1", 0.81)]}

    def search(self, vecs, k, sections, user):
        return [[(sid, sc, 0, 0) for sid, sc in self.NEAR[q]] for q in self.queries]


class Embedder:
    def __init__(self, index):
        self.index = index

    def encode_queries(self, texts):
        self.index.queries = list(texts)
        return [[0.0] for _ in texts]


def test_links_grow_only_across_domains_above_the_threshold_and_spread(cfg):
    cfg.values["AURORA_SYNAPSE_MIN"] = 0.72
    idx = Index()
    out = S.grow(cfg, Reader(), idx, Embedder(idx), 10)
    assert out["seen"] == 3 and out["made"] == 2                     # p1→b1 and b1→p1: the same link; p2 same domain
    assert S.stats(cfg)["links"] == 1                                # l1 at 0.60 is below the threshold
    assert S.neighbours(cfg, ["p1"], 5) == [("b1", 0.81, "p1")]
    assert S.grow(cfg, Reader(), idx, Embedder(idx), 10)["seen"] == 0   # each domain resumes where it stopped


def test_cited_together_they_wire_and_unused_links_fade(cfg):
    assert S.strengthen(cfg, [("p1", "physics"), ("l1", "literature"), ("p2", "physics")]) == 2   # same domain: no
    st = S.stats(cfg)
    assert st["links"] == 2 and st["kinds"] == {"hebb": 2}
    S.strengthen(cfg, [("p1", "physics"), ("l1", "literature")])
    w = dict((s, w) for s, w, _ in S.neighbours(cfg, ["p1"], 5))["l1"]
    assert abs(w - (S.HEBB_NEW + S.HEBB_STEP)) < 1e-9                    # used again: stronger
    later = time.time() + 30 * 86400
    for _ in range(15):
        S.fade(cfg, later)                                           # a month unused, then 15 daily fades
    assert S.stats(cfg)["links"] == 0                                # below the floor: gone


def test_activity_makes_synapses_once_per_passage(cfg):
    cfg.values["AURORA_SYNAPSE_MIN"] = 0.72
    idx = Index()

    class R(Reader):
        def get_many(self, sids):
            return {s: SimpleNamespace(sid=s, domain=P[s], text=s, kind="knowledge") for s in sids if s in P}
    assert S.grow_for(cfg, R(), idx, Embedder(idx), ["p1"]) == 1          # p1 ↔ b1, used: linked now
    assert S.grow_for(cfg, R(), idx, Embedder(idx), ["p1"]) == 0          # looked at already: not again
    assert S.stats(cfg)["kinds"] == {"activity": 1}
