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
        return {s: SimpleNamespace(sid=s, domain=P[s], text=s) for s in sids if s in P}


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


def test_synapses_of_synapses_and_concepts(cfg):
    """A↔B↔C: A↔C of level 2 only when A and C are similar themselves; strong groups become named concepts (M108)."""
    from aurora import kno_synapse2 as S2
    cfg.values.update(AURORA_SYNAPSE_L2_MIN=0.6, AURORA_SYNAPSE_L2_EVERY=2)
    S.link(cfg, ("p1", "physics"), ("b1", "biomedicine"), 0.8)
    S.link(cfg, ("b1", "biomedicine"), ("l1", "literature"), 0.8)
    S.link(cfg, ("b1", "biomedicine"), ("x1", "history"), 0.8)
    vec = {"p1": [1, 0, 0], "l1": [0.9, 0.1, 0], "x1": [0, 0, 1]}          # p1~l1 related, x1 apart

    class Emb:
        def encode_queries(self, texts):
            return [vec[t] for t in texts]

    class R:
        def get_many(self, sids):
            dom = {"p1": "physics", "b1": "biomedicine", "l1": "literature", "x1": "history"}
            return {s: SimpleNamespace(sid=s, text=s, title=s.upper(), domain=dom[s]) for s in sids}

    class Namer:
        def complete(self, *a, **k):
            return SimpleNamespace(answer="Modelli di crescita\n")
    assert S2.due(cfg)
    out = S2.round_(cfg, R(), Emb(), Namer())
    assert out["candidates"] == 3 and out["made"] == 1                     # only p1↔l1
    assert [(x["a"], x["b"], x["level"]) for x in S.listing(cfg, level=2)] == [("l1", "p1", 2)]
    c = S2.list_concepts(cfg)
    assert len(c) == 1 and c[0]["name"] == "Modelli di crescita" and len(c[0]["members"]) == 4
    assert not S2.due(cfg)                                                 # nothing new since the round


def test_the_owner_pins_wakes_and_deletes(cfg):
    S.link(cfg, ("p1", "physics"), ("b1", "biomedicine"), 0.55)
    S.edit(cfg, "b1", "p1", pinned=True)
    later = time.time() + 60 * 86400
    for _ in range(30):
        S.fade(cfg, later)
    assert S.listing(cfg)[0]["w"] == 0.55                                  # pinned: never fades
    S.edit(cfg, "p1", "b1", pinned=False)
    for _ in range(10):
        S.fade(cfg, later)
    assert S.listing(cfg) == [] and len(S.listing(cfg, active=False)) == 1  # asleep, not gone
    assert S.edit(cfg, "p1", "b1", active=True)["active"] == 1              # woken by the owner
    assert S.edit(cfg, "p1", "b1", delete=True) is None and S.listing(cfg, active=False) == []


def test_no_synapse_between_two_copies_of_one_document(cfg):
    """An article harvested in two domains (Existentialism in literature and religion) is not a link (M108)."""
    assert S.strengthen(cfg, [("e1", "literature", "wikipedia:Existentialism"), ("e2", "religion", "wikipedia:Existentialism"),
                              ("k1", "philosophy", "wikipedia:Kafka")]) == 2
    assert {(x["a"], x["b"]) for x in S.listing(cfg)} == {("e1", "k1"), ("e2", "k1")}
    assert S.same_source(SimpleNamespace(source_id="x"), SimpleNamespace(source_id="x"))
    assert not S.same_source(SimpleNamespace(source_id=None), SimpleNamespace(source_id=None))


def test_the_same_article_twice_is_one_document():
    a = SimpleNamespace(source_id="legacy:wiki_Existentialism", title="Existentialism")
    b = SimpleNamespace(source_id="doc:0d60e5", title="Existentialism")
    assert S.same_source(a, b) and not S.same_source(a, SimpleNamespace(source_id="doc:1", title="Kafka"))


def test_an_answer_citing_sources_wires_them_and_never_fails(cfg):
    """C151: the Hebb step inside every cited answer unpacked pairs from triples and crashed the answer."""
    from aurora.kno_answer import hebb
    one = [{"sid": "p1", "domain": "physics", "source": "arxiv:1"}]
    assert hebb(cfg, one) == 0                                               # one domain: nothing to wire, no error
    two = one + [{"sid": "b1", "domain": "biomedicine", "source": "arxiv:2"},
                 {"sid": "m1", "domain": "conversation", "source": "chat"}]
    assert hebb(cfg, two) == 1 and S.stats(cfg)["kinds"] == {"hebb": 1}
