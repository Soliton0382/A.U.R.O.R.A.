# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The law gate (kno_lawgate, C694), the neutral split (C694) and the self route's «casa» (C696). Invented questions."""
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import kno_lawgate as G
from aurora import kno_split


class Emb:
    def __init__(self, vec):
        self.vec, self.calls = vec, 0

    def encode_queries(self, texts):
        self.calls += 1
        if self.vec is None:
            raise ConnectionError("encoder down")
        return np.array([self.vec], dtype=np.float32)


@pytest.fixture
def two_domains(monkeypatch):
    names = ["law_it", "mathematics"]
    c = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    monkeypatch.setattr(G, "centroids", lambda cfg: (names, c))


def _pipe(vec, threshold=-0.01, band=0.0, model=None):
    cfg = {"AURORA_PIPELINE_LAW_GATE": threshold, "AURORA_PIPELINE_LAW_GATE_BAND": band}
    return SimpleNamespace(cfg=cfg, search=SimpleNamespace(embedder=Emb(vec)), llm=model)


def test_an_explicit_article_or_act_is_legal_whatever_the_margin():
    for q in ("cosa dice l'art. 2043 c.c.?", "il d.lgs. 30/2005 sulla proprietà industriale", "articolo 3 della Costituzione",
              "what does article 1571 say?", "la legge n. 392/1978 sull'equo canone"):
        assert G.cites_an_act(q), q
    for q in ("quanto fa 3/4 più 2/3?", "cosa dice la legge di gravitazione di Newton?", "le regole del fuorigioco",
              "quanto costa riscaldare casa?", "un'opera d'arte del 1500"):
        assert not G.cites_an_act(q), q


def test_off_by_default_every_question_as_before():
    p = SimpleNamespace(cfg={}, search=SimpleNamespace(embedder=Emb([0.0, 1.0])))
    events = []
    assert G.legal(p, "how is the area of a trapezoid calculated?", lambda e, x: events.append(e))
    assert p.search.embedder.calls == 0 and events == []


def test_below_the_threshold_the_law_stays_out_above_it_comes_in(two_domains):
    events = []
    ev = lambda e, x: events.append(x)                                                       # noqa: E731
    assert not G.legal(_pipe([0.2, 0.98]), "Why does my phone get hot while charging?", ev)
    assert events[-1]["legal"] is False and events[-1]["why"] == "margin" and events[-1]["margin"] < -0.01
    assert G.legal(_pipe([0.9, 0.3]), "Can an employer reduce working hours without consent?", ev)
    assert events[-1]["legal"] is True and events[-1]["uncertain"] is False


def test_an_attachment_an_act_or_a_follow_up_on_legal_sources_stays_legal(two_domains):
    far = [0.0, 1.0]                                                                        # clearly not legal
    events = []
    ev = lambda e, x: events.append(x)                                                       # noqa: E731
    assert G.legal(_pipe(far), "summarise it", ev, attached=True)
    assert G.legal(_pipe(far), "what does it say?", ev, native="cosa dice l'art. 1571 c.c.?")
    assert G.legal(_pipe(far), "and for a short let?", ev, focus=[{"source": "x", "domain": "law_it"}])
    assert [e["why"] for e in events] == ["attachment", "act named", "follow-up on legal sources"]


def test_in_the_band_the_local_model_breaks_the_tie(two_domains):
    near = [0.7071, 0.7071]                                                                 # margin 0: in the band
    asked = []
    law = SimpleNamespace(decide=lambda s, u, o: asked.append(u) or {"LAW": 0.9, "OTHER": 0.1})
    other = SimpleNamespace(decide=lambda s, u, o: {"LAW": 0.1, "OTHER": 0.9})
    events = []
    ev = lambda e, x: events.append(x)                                                       # noqa: E731
    assert G.legal(_pipe(near, band=0.02, model=law), "Who pays for the repair?", ev)
    assert events[-1]["why"] == "model" and events[-1]["p_law"] == 0.9
    assert not G.legal(_pipe(near, band=0.02, model=other), "Who pays for the repair?", ev)
    assert asked == ["QUESTION: Who pays for the repair?"]
    assert G.legal(_pipe(near, band=0.0, model=other), "Who pays for the repair?", ev)      # no band: the margin
    assert events[-1]["why"] == "margin"


def test_still_uncertain_the_law_stays_out_and_the_event_says_so(two_domains):
    near = [0.7071, 0.7071]
    unsure = SimpleNamespace(decide=lambda s, u, o: {"LAW": 0.55, "OTHER": 0.45})
    silent = SimpleNamespace(decide=lambda s, u, o: None,
                             complete=lambda s, u, n: SimpleNamespace(answer="maybe"))
    events = []
    ev = lambda e, x: events.append(x)                                                       # noqa: E731
    assert not G.legal(_pipe(near, band=0.02, model=unsure), "And how long do I have?", ev)
    assert events[-1]["uncertain"] is True and events[-1]["why"] == "the model unsure"
    # C706: the model silent (absent, late): the margin decides (here 0 > -0.01), said uncertain
    assert G.legal(_pipe(near, band=0.02, model=silent), "And how long do I have?", ev)
    assert events[-1]["uncertain"] is True and events[-1]["why"] == "the model did not answer: the margin"
    assert not G.legal(_pipe(None), "anything", ev)                                          # the encoder down
    assert events[-1]["uncertain"] is True and events[-1]["legal"] is False


def test_the_tie_break_reads_the_turns_before(two_domains):
    from datetime import datetime
    asked = []
    model = SimpleNamespace(decide=lambda s, u, o: asked.append(u) or {"LAW": 0.8, "OTHER": 0.2})
    p = _pipe([0.7071, 0.7071], band=0.02, model=model)
    p.cfg["AURORA_REM_SESSION_GAP_MIN"] = 30
    p._turns = lambda recent, n, cut: "Owner: mi è arrivata una multa per eccesso di velocità"
    turn = SimpleNamespace(created_at=datetime.now().astimezone().isoformat())
    events = []
    import aurora.sns_clock as clock
    real = clock.now
    clock.now = lambda cfg: datetime.now().astimezone()
    try:
        assert G.legal(p, "And how much time do I have?", lambda e, x: events.append(x), recent=[turn], followup=True)
    finally:
        clock.now = real
    assert asked[0].startswith("EARLIER TURNS:\nOwner: mi è arrivata una multa") and events[-1]["why"].endswith("turns before")


def test_the_centroids_are_computed_again_when_a_domain_lost_passages(monkeypatch):
    G.forget()
    counts = {"law_it": 1000, "mathematics": 500}
    built = []
    monkeypatch.setattr(G, "_counts", lambda cfg: {d: (None, {"count": n}) for d, n in counts.items()})
    monkeypatch.setattr(G, "_compute", lambda cfg, found: built.append(dict(counts)) or (sorted(found), np.eye(2)))
    monkeypatch.setattr(G, "COUNTS_S", 0)
    G.centroids(None)
    counts["mathematics"] = 510                       # grown a little, within REFRESH_S: kept
    G.centroids(None)
    assert len(built) == 1
    counts["law_it"] = 900                            # passages moved out (C695): computed again
    G.centroids(None)
    assert len(built) == 2 and built[-1]["law_it"] == 900
    G.forget()


def test_a_legal_hit_is_a_law_domain_s_passage_or_a_named_provision():
    hit = lambda d, q="original": SimpleNamespace(soliton=SimpleNamespace(domain=d), query_used=q)   # noqa: E731
    assert G.legal_hit(hit("law_it")) and G.legal_hit(hit("general", "cited"))
    assert not G.legal_hit(hit("society")) and not G.legal_hit(hit("medicine"))


class Model:
    def __init__(self, answer):
        self.answer, self.systems, self.users = answer, [], []

    def complete(self, system, user, max_tokens, think=False):
        self.systems.append(system)
        self.users.append(user)
        return SimpleNamespace(answer=self.answer)


def test_the_split_prompt_is_neutral_and_in_the_pivot_s_language():
    """C694: «the questions a lawyer would look up», two tenancy examples in Italian, the searches in Italian."""
    assert "lawyer" not in kno_split.SYS_SPLIT and "cactus" in kno_split.SYS_SPLIT and "refund" in kno_split.SYS_SPLIT
    m = Model("Why does a phone overheat while gaming?\nHow long should a phone battery last?")
    assert kno_split.split(m, "My phone gets very hot when I play...", english=True)[0].startswith("Why does a phone")
    assert m.systems[0].endswith("Write them in English. One per line, nothing else.")
    kno_split.split(m, "Il telefono si scalda tanto...")
    assert "Same language as the message." in m.systems[1] and "{lang}" not in m.systems[1]


def test_not_legal_no_provision_is_named_and_the_pivot_s_searches_are_not_translated(monkeypatch):
    from aurora import kno_cites
    named = []
    monkeypatch.setattr(kno_cites, "hits", lambda p, q, ev: named.append(q) or [])
    model = Model("Why does a phone overheat while gaming?\nHow long should a phone battery last?")
    searched = []
    hit = SimpleNamespace(sid="s1", rerank=0.5, soliton=SimpleNamespace(domain="engineering"), query_used="original")
    p = SimpleNamespace(cfg={"AURORA_PIPELINE_SPLIT_CHARS": 50, "AURORA_SEARCH_TOPK": 12}, _pivot=True,
                        _for=lambda role: model,
                        search=SimpleNamespace(search=lambda s, tr, **kw: searched.append((s, tr)) or [hit]))
    long_q = "My phone gets very hot when I play and the battery lasts less than half a day, although it is new."
    hits, subs = kno_split.search(p, long_q, lambda: [], lambda e, x: None, legal=False)
    assert named == [] and len(subs) == 2
    assert searched == [(subs[0], None), (subs[1], None)]          # English already: no translation call
    assert len(model.users) == 1                                   # the split only
    kno_split.search(p, long_q, lambda: [], lambda e, x: None)     # legal (the default): the provisions asked for
    assert named == [long_q]


def test_a_legal_case_on_the_pivot_is_split_in_the_user_s_language_and_translated(monkeypatch):
    """M318: English searches dropped the cases' best law re-rank (0.98 → 0.10): statutes are found by their words."""
    from aurora import kno_cites
    monkeypatch.setattr(kno_cites, "hits", lambda p, q, ev: [])
    model = Model("Il datore può ridurre l'orario?\nSi può licenziare chi rifiuta?")
    searched = []
    p = SimpleNamespace(cfg={"AURORA_PIPELINE_SPLIT_CHARS": 50, "AURORA_SEARCH_TOPK": 12}, _pivot=True,
                        _for=lambda role: model, search=SimpleNamespace(search=lambda s, tr, **kw: searched.append((s, tr)) or []))
    long_q = "My employer told me he will cut my hours to twenty a week from next month, nothing in writing. Can he?"
    kno_split.search(p, long_q, lambda: [], lambda e, x: None, legal=True, lang="it")
    assert "Write them in Italian." in model.systems[0]
    assert len(model.users) == 3 and all(tr is not None for _, tr in searched)       # each search translated
    model.systems.clear()
    kno_split.search(p, long_q, lambda: [], lambda e, x: None, legal=False, lang="it")
    assert "Write them in English." in model.systems[0]


def test_a_person_s_own_home_is_not_aurora_in_the_route_prompt():
    """C696: «perché il wifi di casa va lento la sera?» went the self route. The prompt now says a person's home is a
    question about the world; the three invented questions of the brief are checked live (M318)."""
    from aurora.kno_self import SYS_ROUTE
    assert "A person's own house" in SYS_ROUTE and "«casa mia»" in SYS_ROUTE and "KNOWLEDGE" in SYS_ROUTE
    for q in ("perché il wifi di casa va lento la sera?", "la mia casa è fredda", "quanto costa riscaldare casa?"):
        assert q not in SYS_ROUTE                                   # the measured questions are not its examples
