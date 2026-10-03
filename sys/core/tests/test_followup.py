# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Follow-ups: the sources in focus, the suggestions (kno_followup), the passages of one source (sol_reader)."""
from types import SimpleNamespace

from aurora import kno_followup as F
from aurora import sol_schema as S
from aurora.sol_reader import VaultReader
from aurora.sol_search import Hit
from aurora.sol_writer import VaultWriter

FILLER = " The measured quantity follows the model within the stated uncertainty." * 6


def sol(text, src="arxiv:a", domain="physics", lang="en"):
    return S.Soliton.new(text + FILLER, domain, "knowledge", lang, src)


def test_by_source_reads_one_source_in_order(cfg):
    VaultWriter(cfg).add_many([sol(f"Paper A part {i}.", "arxiv:a") for i in range(3)] + [sol("Paper B.", "arxiv:b")])
    r = VaultReader(cfg)
    got = r.by_source("physics", "arxiv:a")
    assert [s.source_id for s in got] == ["arxiv:a"] * 3
    assert r.by_source("physics", "arxiv:a", limit=2) and len(r.by_source("physics", "arxiv:a", limit=2)) == 2
    assert r.by_source("no_such_domain", "arxiv:a") == []


def test_clean_focus_keeps_known_domains_only():
    tax = {"physics": {}, "law_it": {}}
    raw = [{"source": "arxiv:a", "domain": "physics"}, {"source": "arxiv:a", "domain": "physics"},
           {"source": "x", "domain": "../etc"}, "junk", {"source": "", "domain": "physics"},
           {"source": "l:1", "domain": "law_it"}]
    assert F.clean_focus(raw, tax) == [{"source": "arxiv:a", "domain": "physics"}, {"source": "l:1", "domain": "law_it"}]
    assert F.clean_focus("not a list", tax) == []


class Reranker:
    def __init__(self, score):
        self.score_of = score

    def score(self, pairs):
        return [self.score_of(t) for _, t in pairs]


def fake(reader_sols, score, topk=3):
    reader = SimpleNamespace(by_source=lambda d, s, n: [x for x in reader_sols if x.source_id == s][:n])
    return SimpleNamespace(reader=reader, search=SimpleNamespace(reranker=Reranker(score)),
                           cfg={"AURORA_SEARCH_TOPK": topk})


def test_focus_competes_on_the_same_score_and_is_not_forced():
    found = [Hit(f"h{i}", sol(f"Found {i}.", "arxiv:x"), 0.5, r, "original") for i, r in enumerate((5.0, 3.0, 1.0))]
    paper = [sol("Relevant part.", "arxiv:a"), sol("Irrelevant part.", "arxiv:a")]
    p = fake(paper, lambda t: 4.0 if t.startswith("Relevant") else -2.0)
    events = []
    out = F.with_focus(p, "q", None, found, [{"source": "arxiv:a", "domain": "physics"}], lambda e, x: events.append(x))
    assert [h.rerank for h in out] == [5.0, 4.0, 3.0]                 # the relevant part enters, the weak hit leaves
    assert out[1].query_used == "focus" and events[0]["kept"] == 1
    p = fake(paper, lambda t: -5.0)                                   # nothing relevant in focus: hits unchanged
    assert F.with_focus(p, "q", None, found, [{"source": "arxiv:a", "domain": "physics"}], lambda *a: None) == found


def test_focus_of_an_answer():
    turn = SimpleNamespace(extra={"source_list": [{"source": "arxiv:a", "domain": "physics", "title": "A"},
                                                  {"source": "arxiv:a", "domain": "physics", "title": "A"},
                                                  {"source": "arxiv:b", "domain": "physics"}]})
    assert F.focus_of(turn) == [{"source": "arxiv:a", "domain": "physics"}, {"source": "arxiv:b", "domain": "physics"}]
    assert F.focus_of(None) == []


def test_suggestions_are_complete_questions_with_their_sources():
    hits = [Hit("h1", sol("Photosynthesis basics.", "arxiv:a", "biology"), 0.5, 3.0, "original"),
            Hit("h2", sol("Discovery by Ingenhousz.", "arxiv:b", "biology"), 0.5, 2.0, "original")]
    answer = ('[{"q": "Chi scoprì la fotosintesi e in quale anno?", "p": [2]}, '
              '{"q": "Chi scoprì la fotosintesi e in quale anno?", "p": [1]}, {"q": "Corta?", "p": [1]}, '
              '{"q": "Quale ruolo ha la clorofilla nella fotosintesi?", "p": [1, 9]}]')
    llm = SimpleNamespace(complete=lambda system, user, n: SimpleNamespace(answer="ecco: " + answer))
    p = SimpleNamespace(_for=lambda role: llm)
    events = []
    out = F.suggest(p, "Come funziona la fotosintesi?", "La fotosintesi…", [{"sid": "h1"}], hits,
                    lambda e, x: events.append(e))
    assert [o["question"] for o in out] == ["Chi scoprì la fotosintesi e in quale anno?",
                                             "Quale ruolo ha la clorofilla nella fotosintesi?"]   # duplicate, short: out
    assert out[0]["focus"] == [{"source": "arxiv:b", "domain": "biology"}]
    assert out[1]["focus"] == [{"source": "arxiv:a", "domain": "biology"}]                        # a wrong number: ignored
    assert events == ["answer.suggestions"]
    bad = SimpleNamespace(complete=lambda *a: SimpleNamespace(answer="no JSON here"))
    assert F.suggest(SimpleNamespace(_for=lambda r: bad), "q", "a", [], hits, lambda *a: None) == []
