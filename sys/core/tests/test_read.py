# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Search, read, answer from what was read (kno_read, kno_web): fake models and a fake web, no network."""
from types import SimpleNamespace

from aurora import kno_read as R
from aurora import kno_web as W


class Model:
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def complete(self, system, user, max_tokens, think=False):
        self.asked.append((system[:12], user))
        for key, out in self.answers.items():
            if key in system or key in user:
                return SimpleNamespace(answer=out)
        return SimpleNamespace(answer="")


def _p(model, web=True):
    return SimpleNamespace(cfg={"AURORA_VERIFY_WEB": web}, _for=lambda role: model)


def test_the_kind_of_question():
    assert R.kind(_p(Model({"Classify": "FACT"})), "chi ha cantato let's go all the way") == "fact"
    assert R.kind(_p(Model({"Classify": "explain."})), "come funziona un laser") == "explain"
    assert R.kind(_p(Model({"Classify": "CASE"})), "viviamo in un supercondominio…") == "case"
    assert R.kind(_p(Model({"Classify": "boh"})), "?") == "fact"


def test_an_answer_keeps_only_the_sources_it_cites():
    texts = [{"text": f"t{i}", "source": {"url": f"https://x/{i}", "title": f"T{i}", "domain": "web"}} for i in (1, 2, 3)]
    out = R.read(_p(Model({"ONLY the numbered": "Lo cantavano gli Sly Fox [2]."})), "chi?", texts, "fact")
    assert out["text"] == "Lo cantavano gli Sly Fox [2]." and [s["n"] for s in out["sources"]] == [2]
    assert R.read(_p(Model({"ONLY the numbered": "NON TROVATO"})), "chi?", texts, "fact") is None
    assert R.read(_p(Model({"ONLY the numbered": "Gli Sly Fox."})), "chi?", texts, "fact") is None     # no citation: not read


def test_the_snippets_first_then_the_pages(monkeypatch):
    found = [{"title": "Let's Go All the Way (song)", "url": "https://en.wikipedia.org/wiki/x", "text": "a 1985 song"}]
    monkeypatch.setattr(W, "query", lambda m, q, cfg: "let's go all the way song")
    monkeypatch.setattr(W, "search", lambda q, region="it-it": found)
    monkeypatch.setattr(W, "page", lambda url: "Let's Go All the Way is a song by Sly Fox, released in 1985.")
    m = Model({"Sly Fox, released": "La cantavano gli Sly Fox [1].", "a 1985 song": "NON TROVATO"})
    events = []
    out = R.from_web(_p(m), "chi ha cantato let's go all the way", lambda e, pl: events.append(e), "fact")
    assert out["text"] == "La cantavano gli Sly Fox [1]." and out["sources"][0]["url"] == found[0]["url"]
    assert events == ["read.web", "read.pages"]
    assert R.from_web(_p(m, web=False), "x", lambda *a: None) is None                         # the web switched off


def test_memory_is_said_as_memory_and_never_silence():
    out = R.from_memory(_p(Model({"from what you know": "La M sta per metastasi."})), "nel TNM cosa vuol dire M?", lambda *a: None)
    assert out["text"] == "⚠️ Dalla mia memoria, non verificato da una fonte: La M sta per metastasi." and out["sources"] == []
    assert R.from_memory(_p(Model({"from what you know": "NON LO SO."})), "?", lambda *a: None) is None


def test_only_the_subject_leaves_the_machine(cfg):
    asked = "Mario Rossi di via Garibaldi 12, tel 333 1234567, mi chiede: chi ha scritto la Commedia?"
    m = Model({"web search query": "autore Divina Commedia 333 1234567 mario.rossi@example.org"})
    q = W.query(m, asked, cfg)
    assert q.startswith("autore Divina Commedia") and "333" not in q and "1234567" not in q
    assert "example" not in q and "[" not in q and m.asked[0][1] == asked     # the model reads it here, on the machine


def test_a_private_address_is_never_read():
    assert W._public("http://127.0.0.1/x") is None and W._public("http://192.168.1.1/") is None
    assert W._public("ftp://example.org/") is None and W.page("http://localhost:9700/") == ""


def test_a_page_is_read_through_a_client(monkeypatch):
    import httpx
    monkeypatch.setattr(W, "_public", lambda url: "93.184.216.34")
    real = httpx.Client
    html = "<html><head><title>t</title><script>x()</script></head><body><p>" + "Sly Fox cantava Let's Go All the Way. " * 3 + "</p></body></html>"
    monkeypatch.setattr(W.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, html=html)), **kw))
    text = W.page("https://example.org/song")
    assert "Sly Fox cantava" in text and "x()" not in text


def test_not_found_in_italian_then_in_english(monkeypatch):
    regions = []
    monkeypatch.setattr(W, "query", lambda m, q, cfg: "q " + q[:20])

    def search(q, region="it-it"):
        regions.append(region)
        if region == "it-it":
            return [{"title": "Quando ti rivedrò", "url": "https://x/it", "text": "una canzone italiana"}]
        return [{"title": "When Can I See You Again", "url": "https://x/en", "text": "a song by Owl City"}]
    monkeypatch.setattr(W, "search", search)
    monkeypatch.setattr(W, "page", lambda url: "")
    m = Model({"Owl City": "La cantano gli Owl City [1].", "canzone italiana": "NON TROVATO"})
    out = R.from_web(_p(m), "Chi ha cantato Quando posso rivederti", lambda *a: None, "fact", True,
                     "Who sang When Can I See You Again")
    assert out["text"] == "La cantano gli Owl City [1]." and regions == ["it-it", "wt-wt"]
