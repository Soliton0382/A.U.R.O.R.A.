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
    return SimpleNamespace(cfg={"AURORA_VERIFY_WEB": web}, _for=lambda role: model, llm=model)   # llm: the local decoy


def test_the_kind_of_question():
    assert R.kind(_p(Model({"Classify": "FACT"})), "chi ha cantato let's go all the way") == "fact"
    assert R.kind(_p(Model({"Classify": "explain."})), "come funziona un laser") == "explain"
    assert R.kind(_p(Model({"Classify": "CASE"})), "abitiamo in affitto e il proprietario…") == "case"
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


def test_an_explanation_from_the_web_reads_the_pages_at_once(monkeypatch):
    # C307: the wine stain answered from the snippets («detergenti appropriati») — the method is in the page
    found = [{"title": "Red wine stains", "url": "https://x/wine", "text": "simple steps and tips"},
             {"title": "Stains", "url": "https://x/stains", "text": "tips for fresh and dry stains"}]
    monkeypatch.setattr(W, "query", lambda m, q, cfg: "remove red wine stain")
    monkeypatch.setattr(W, "search", lambda q, region="it-it": found)
    monkeypatch.setattr(W, "page", lambda url: "Rinse with cold water, cover with salt, then wash with dish soap.")
    m = Model({"cover with salt": "Acqua fredda, sale, poi sapone per i piatti [1]."})
    events = []
    out = R.from_web(_p(m), "come si toglie una macchia di vino?", lambda e, pl: events.append(e), "explain")
    assert out["text"].startswith("Acqua fredda") and events == ["read.web", "read.pages"] and len(m.asked) == 1
    events.clear()                                     # a fact: the snippets first, as before
    R.from_web(_p(Model({"tips": "Sale [1]."})), "chi?", lambda e, pl: events.append(e), "fact")
    assert events == ["read.web"]


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


def test_a_question_with_options_or_a_form_asked_is_an_exercise_without_asking_the_model():
    """C274: MMLU questions classified FACT or EXPLAIN were answered in substance, without the letter asked."""
    from types import SimpleNamespace
    from aurora import kno_read as R
    never = SimpleNamespace(_for=lambda role: (_ for _ in ()).throw(AssertionError("the model was asked")))
    assert R.kind(never, "Quale?\n\nA) uno\nB) due\n\nAlla fine scrivi «Risposta: X»") == "solve"
    assert R.kind(never, "Quanto fa 17*23? Risposta: N") == "solve"
    asked = SimpleNamespace(_for=lambda role: SimpleNamespace(complete=lambda s, q, n: SimpleNamespace(answer="FACT")))
    assert R.kind(asked, "Chi ha scritto I promessi sposi?") == "fact"


def test_an_answer_saying_the_texts_lack_it_is_not_an_answer():
    # C305: «I testi non specificano le attrazioni esatte…» was kept as the answer and the pages never opened
    from aurora.kno_read import EMPTY
    assert EMPTY.search("I testi non specificano le attrazioni esatte da visitare, ma indicano [2].")
    assert EMPTY.search("The texts do not mention the year.")
    assert EMPTY.search("Le fonti fornite non riportano il dato.")
    assert not EMPTY.search("Il Duomo e gli Uffizi sono le tappe principali [1]; i testi non specificano gli orari.")
    assert not EMPTY.search("Non è vero che i testi antichi non citano Firenze [2].")
