# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How much to think (kno_think): each question goes the way of its kind; the vault mode stays as before."""
from types import SimpleNamespace

import pytest

from aurora import kno_think as T

READ = {"text": "ok [1]", "sources": [{"n": 1, "url": "https://x"}], "dropped": []}


def _same(r):
    return r is not None and {k: r[k] for k in READ} == READ


@pytest.fixture
def run(monkeypatch):
    def go(mode, kind, web=None, vault=None, memory=None, deep=None):
        calls, events = [], []
        monkeypatch.setattr(T.kno_read, "kind", lambda p, q: kind)
        monkeypatch.setattr(T.kno_read, "from_web", lambda p, q, ev, size="fact", open_pages=True, translation=None, native=None:
                            calls.append(f"web({size},{'pages' if open_pages else 'snippets'})") or web)
        monkeypatch.setattr(T.kno_read, "from_vault", lambda p, q, hits, size="explain": calls.append(f"vault({size})") or vault)
        monkeypatch.setattr(T.kno_read, "from_memory", lambda p, q, ev: calls.append("memory") or memory)

        def retrieve(recall):
            calls.append("search")
            return ["h"], []

        def classic(h, s):
            calls.append("deep")
            return deep
        out = T.answer(SimpleNamespace(cfg={}), "q", None, mode, retrieve, classic,
                       lambda e, pl: events.append(pl) if e == "think" else None)
        return out, calls, events[-1]
    return go


def test_vault_is_the_pipeline_of_before(run):
    (r, a, _, _), calls, ev = run("vault", "fact", deep=("x", [], []))
    assert r is None and a == ("x", [], []) and calls == ["search", "deep"] and ev["used"] == "vault"


def test_a_fact_the_vault_is_not_sure_of_goes_to_the_web(run):
    """The vault is searched (a re-rank, no reading); not sure of it, the web answers (M194)."""
    (r, a, _, _), calls, ev = run("auto", "fact", web=READ)
    assert _same(r) and calls == ["search", "web(fact,pages)"] and ev["why"] == "un fatto da cercare → web"


def test_light_reads_only_the_snippets(run):
    _, calls, _ = run("light", "fact", web=READ)
    assert calls == ["search", "web(fact,snippets)"]


def test_an_explanation_reads_the_vault_then_the_web(run):
    (r, _, _, _), calls, ev = run("auto", "explain", vault=None, web=READ)
    assert _same(r) and calls == ["search", "vault(explain)", "web(explain,pages)"] and ev["why"].endswith("→ web")


def test_a_case_goes_deep_in_auto_but_not_in_medium(run):
    (_, a, _, _), calls, ev = run("auto", "case", deep=("profonda", [], []))
    assert a == ("profonda", [], []) and calls == ["search", "deep"] and ev["why"] == "un caso → deep"
    _, calls, _ = run("medium", "case", vault=READ)
    assert "deep" not in calls and calls[-1] == "vault(explain)"


def test_no_source_then_memory_marked_never_silence(run):
    (r, a, _, _), calls, ev = run("auto", "fact", memory=READ)
    # the vault is searched first (one re-rank): not sure of it (a passage without a score) → the web, then the vault
    assert _same(r) and calls == ["search", "web(fact,pages)", "vault(fact)", "memory"] and ev["why"].endswith("→ memory")
    (r, a, _, _), _, ev = run("auto", "fact")
    assert r is None and a is None and ev["why"].endswith("nessuna fonte")


def test_an_unknown_mode_is_the_vault():
    assert T.mode_of({"AURORA_ANSWER_MODE": "turbo"}, None) == "vault" and T.mode_of({"AURORA_ANSWER_MODE": "vault"}, "AUTO") == "auto"


def test_a_source_that_breaks_does_not_break_the_answer(run, monkeypatch):
    def boom(*a, **k):
        raise TypeError("a bug in a source")
    monkeypatch.setattr(T.kno_read, "from_web", boom)
    monkeypatch.setattr(T.kno_read, "kind", lambda p, q: "fact")
    events = []
    out = T.answer(SimpleNamespace(cfg={}), "q", None, "auto", lambda r: (["h"], []), lambda h, s: None,
                   lambda e, pl: events.append(e))
    assert "read.failed" in events and events[-1] == "think"            # it went on: the vault, then memory


def test_an_explanation_the_vault_lacked_is_studied_at_night_a_fact_is_not(run):
    (r, _, _, _), _, _ = run("auto", "explain", vault=None, web=READ)
    assert r["came_from"] == "web" and r["learn"] is True
    (r, _, _, _), _, _ = run("auto", "fact", web=READ)
    assert r["came_from"] == "web" and r["learn"] is False            # a fact: the cache is enough
    (r, _, _, _), _, _ = run("auto", "explain", vault=READ)
    assert r["came_from"] == "vault" and r["learn"] is False


def test_a_follow_up_reads_the_sources_in_focus_first(run, monkeypatch):
    calls = []
    monkeypatch.setattr(T.kno_read, "kind", lambda p, q: "fact")
    monkeypatch.setattr(T.kno_read, "from_vault", lambda p, q, hits, size="explain": calls.append(f"vault({size})") or READ)
    monkeypatch.setattr(T.kno_read, "from_web", lambda *a, **k: calls.append("web") or READ)
    (r, _, _, _) = T.answer(SimpleNamespace(cfg={}), "e chi l'ha inventato?", None, "auto", lambda rc: (["h"], []),
                            lambda h, s: None, lambda e, pl: None, focused=True)
    assert calls == ["vault(fact)"] and r["came_from"] == "vault"                     # not the slow pipeline, not the web


def test_a_web_answer_is_remembered_with_its_links(monkeypatch):
    """C188: web sources carry no vault sid; remembering the answer raised KeyError and the chat showed an error."""
    from aurora.kno_answer import Pipeline
    from aurora.kno_trail import Answer
    written = []
    fake = SimpleNamespace(writer=SimpleNamespace(add_many=lambda turns, run_id: written.extend(turns) or SimpleNamespace(written=turns)),
                           indexer=SimpleNamespace(update=lambda *a, **k: 0))
    web = {"n": 1, "url": "https://example.org/a", "title": "A", "source": "https://example.org/a", "domain": "web"}
    ans = Answer("r1", "chi decide?", "L'assemblea [1].", False, sources=[web], came_from="web")
    Pipeline.remember(fake, "chi decide?", ans, "r1", lambda *a: None)
    reply = written[1].extra
    assert reply["sources"] == [] and reply["source_list"] == [web] and reply["came_from"] == "web"


def test_a_problem_is_reasoned_first_and_never_searched_in_the_vault(run, monkeypatch):
    """C272: an AIME problem has no source; the memory step (300 tokens, no thinking) said «I don't know»."""
    monkeypatch.setattr(T.kno_read, "from_reasoning", lambda p, q, ev: dict(READ, text="🧮 … Risposta: 211"))
    (r, a, _, _), calls, ev = run("auto", "solve", web=READ)
    assert r["text"].endswith("211") and r["came_from"] == "reason" and not r["learn"] and calls == []
    monkeypatch.setattr(T.kno_read, "from_reasoning", lambda p, q, ev: None)      # the room ended in the thought
    (r, a, _, _), calls, ev = run("auto", "solve", web=READ)
    assert r["came_from"] == "web" and calls == ["web(explain,pages)"]


def test_the_reasoning_keeps_the_form_asked_and_gives_up_when_it_has_no_answer():
    from aurora import kno_read as R
    asked = []
    out = SimpleNamespace(answer="Ragionando… Risposta: C", thought="…", tokens=900)
    p = SimpleNamespace(cfg={"AURORA_SOLVE_TOKENS": 24000},
                        _for=lambda role: SimpleNamespace(complete=lambda s, q, n, think=False: asked.append((n, think)) or out))
    r = R.from_reasoning(p, "Quale? A) x B) y C) z. Risposta: lettera", lambda e, d: None)
    assert r["text"].startswith("🧮") and r["text"].endswith("Risposta: C") and asked == [(24000, True)]
    out.answer = ""
    assert R.from_reasoning(p, "Quanto fa 2+2?", lambda e, d: None) is None


def test_a_fact_goes_to_the_vault_first_when_the_vault_is_sure(monkeypatch):
    """M194: the best passage's re-rank ≥ VAULT_FIRST (0.6) sends a FACT to the vault before the web."""
    from types import SimpleNamespace as NS
    calls = []
    monkeypatch.setattr(T.kno_read, "kind", lambda p, q: "fact")
    monkeypatch.setattr(T.kno_read, "from_web", lambda *a, **k: calls.append("web") or None)
    monkeypatch.setattr(T.kno_read, "from_vault", lambda p, q, h, size: calls.append("vault") or READ)
    for score, first in ((0.95, "vault"), (0.2, "web")):
        calls.clear()
        T.answer(NS(cfg={}), "q", None, "auto", lambda recall: ([NS(rerank=score)], []), lambda h, s: None, lambda e, p: None)
        assert calls[0] == first, (score, calls)


def test_a_text_to_write_is_written_never_searched_nor_refused(run, monkeypatch):
    """C355: an email, a story, an ad asked with rules on its form went to the vault, the web, memory — cited, refused,
    or with ⚠️ before a text that had to start with a quote."""
    monkeypatch.setattr(T.kno_read, "from_writing", lambda p, q, ev: {"text": "\"Caro Marco\"", "sources": [], "dropped": [],
                                                                       "written": True})
    (r, _, _, _), calls, ev = run("auto", "write", web=READ, vault=READ)
    assert r["text"] == "\"Caro Marco\"" and r["came_from"] == "write" and not r["learn"]
    assert "web" not in " ".join(calls) and "vault" not in " ".join(calls) and ev["why"] == "un testo da scrivere → write"


def test_code_in_the_question_is_an_exercise_without_asking_the_model():
    p = SimpleNamespace(_for=lambda role: (_ for _ in ()).throw(AssertionError("the router was asked")))
    assert T.kno_read.kind(p, "Complete it:\n```python\ndef add(a, b):\n    \"\"\"a + b\"\"\"\n```") == "solve"
    assert T.kno_read.kind(p, "Fix this:\n\ndef media(xs):\n    return sum(xs) / len(xs)\n") == "solve"


class Cut:
    def __init__(self, answers):
        self.answers = list(answers)

    def complete(self, system, q, tokens, think=False):
        text, cut = self.answers.pop(0)
        return SimpleNamespace(answer=text, truncated=cut, tokens=tokens)


def test_a_memory_answer_cut_is_reasoned_again_with_room():
    llm = Cut([("def fib4(n):\n    a, b, c,", True), ("def fib4(n):\n    return 0", False)])
    p = SimpleNamespace(_for=lambda role: llm, cfg={"AURORA_SOLVE_TOKENS": 8000})
    events = []
    r = T.kno_read.from_memory(p, "Write fib4", lambda e, pl: events.append(e))
    assert r["text"].endswith("return 0") and "read.memory_cut" in events and "read.reasoning" in events
    llm = Cut([("Roma.", False)])
    p = SimpleNamespace(_for=lambda role: llm, cfg={})
    assert T.kno_read.from_memory(p, "Capitale d'Italia?", lambda e, pl: None)["text"].endswith("Roma.")


@pytest.mark.parametrize("q", [
    "Scrivi un messaggio di auguri per Luca senza usare virgole.",
    "Write a short note to my neighbour about the fence in all capital letters.",
    "Describe a rainy morning in at least 120 words and end your response with \"See you soon.\"",
    "Give me a packing list for a weekend in the mountains in JSON format.",
    "Racconta una favola sul gatto Pippo in esattamente 3 paragrafi.",
])
def test_a_form_imposed_on_the_reply_is_written_without_asking_the_model(q):
    """C356 (M246): the 4-token router missed texts to write; their form is a rule the code reads."""
    p = SimpleNamespace(_for=lambda role: (_ for _ in ()).throw(AssertionError("the router was asked")))
    assert T.kno_read.kind(p, q) == "write"


@pytest.mark.parametrize("q", [
    "Chi ha vinto il campionato di Serie A nel 1990?",
    "Come funziona una pompa di calore?",
    "Rispondi in inglese: qual è la capitale del Portogallo?",
    "Quante parole conosce in media un bambino di 3 anni?",
])
def test_a_question_of_knowledge_is_not_taken_for_a_form(q):
    assert not T.kno_read.FORM.search(q)
