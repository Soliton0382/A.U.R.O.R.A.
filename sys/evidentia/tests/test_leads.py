# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The leads (owner, 10 Nov: «un lavoro già fatto non lo ripetiamo… si scatenano agenti investigativi… messaggi nella
chat investigativa»): chased once, the evidence checked on its pages, posted in every case that needs it."""
import importlib

from starlette.testclient import TestClient


def setup(tmp_path, monkeypatch, pdfs):
    from evidentia import inventory
    inventory.run(pdfs, tmp_path / "data", workers=1, say=lambda *_: None)
    env = tmp_path / ".env"
    env.write_text(f"EVD_DATA_DIR={tmp_path / 'data'}\nEVD_SOURCES_DIR={pdfs}\n")
    monkeypatch.setenv("EVD_ENV_FILE", str(env))
    from evidentia import api
    importlib.reload(api)
    return TestClient(api.app)


def test_a_lead_is_chased_once_and_its_evidence_reaches_every_case(tmp_path, monkeypatch, pdfs):
    c = setup(tmp_path, monkeypatch, pdfs)
    one = c.post("/cases", json={"title": "Voli"}).json()["id"]
    lead = c.post(f"/cases/{one}/leads", json={"what": "Where did flight N908JE leave from", "agent": "sniper"}).json()
    assert lead["status"] == "open" and lead["reused"] is False
    assert c.post(f"/cases/{one}/leads", json={"what": "x", "agent": "sniper"}).status_code == 422
    assert c.post(f"/cases/{one}/leads", json={"what": "Where did it leave from", "agent": "nobody"}).status_code == 422
    work = c.post("/leads/claim", json={"worker": "w1"}).json()
    assert work["lead"]["id"] == lead["id"] and "report_lead" in work["prompt"] and "never identified" in work["prompt"]
    token = work["lead"]["token"]
    assert "token" not in c.get(f"/leads/{lead['id']}").json() and "lease_hash" not in c.get(f"/leads/{lead['id']}").json()
    assert c.post("/leads/claim", json={"worker": "w2"}).json() == {"lead": None}            # leased: not twice
    ev = [{"doc": "ABCD:ABCD00000001", "page": 2, "quote": "Flight N908JE from  teterboro", "note": "the departure"},
          {"doc": "ABCD:ABCD00000001", "page": 2, "quote": "Flight N908JE from Miami", "note": "invented"},
          {"doc": "ABCD:ABCD00000001", "page": 9, "quote": "Flight N908JE from Teterboro"}]
    for wrong in ({"worker": "w1"}, {"token": "guessed"}):                       # the name proves nothing (audit)
        assert c.post(f"/leads/{lead['id']}/report", json={**wrong, "status": "done", "summary": "s" * 30,
                                                            "evidence": ev}).status_code == 409
    bad = c.post(f"/leads/{lead['id']}/report", json={"token": token, "status": "done", "summary": "s" * 30,
                                                       "evidence": ev[1:]})
    assert bad.status_code == 422 and {r["why"] for r in bad.json()["refused"]} == \
        {"the page does not say these words", "no such page"}                                  # nothing that holds
    out = c.post(f"/leads/{lead['id']}/report", json={"token": token, "status": "done", "evidence": ev,
                                                       "summary": "It left from Teterboro, says page 2."}).json()
    assert out["status"] == "done" and [e["cite"] for e in out["evidence"]] == ["ABCD00000001 p. 2"]
    assert len(out["refused"]) == 2
    diary = c.get(f"/cases/{one}").json()["diary"]
    assert [s["kind"] for s in diary] == ["lead", "evidence"] and diary[1]["docs"] == ["ABCD:ABCD00000001"]
    # another case, the same work in other words: not opened again, its evidence there at once
    two = c.post("/cases", json={"title": "Partenze"}).json()["id"]
    again = c.post(f"/cases/{two}/leads", json={"what": "where did flight N908JE leave from?", "agent": "sniper"}).json()
    assert again["reused"] is True and again["id"] == lead["id"] and set(again["cases"]) == {one, two}
    d2 = c.get(f"/cases/{two}").json()["diary"]
    assert [s["kind"] for s in d2] == ["evidence"] and d2[0]["content"]["reused"] is True
    assert c.post("/leads/claim", json={"worker": "w1"}).json() == {"lead": None}            # nothing to redo
    assert "🧾" in c.get(f"/cases/{two}/export.md").text and "«Flight N908JE from Teterboro»" in \
        c.get(f"/cases/{one}/export.md").text                     # the page's words, not the model's spelling (B17)


def test_a_quote_is_kept_as_the_page_writes_it(tmp_path, monkeypatch, pdfs):
    """Audit E2 (B17): «1000⁰» matched «10000» once normalized, and was saved as the model wrote it."""
    setup(tmp_path, monkeypatch, pdfs)
    from evidentia import leads, store
    corpus = store.connect(tmp_path / "data", "corpus.db", readonly=True)
    page = "Wire transfer to IBAN GB82 WEST 1234 5698 7654 32 on 12 March 2004."
    for wrote in ("WIRE TRANSFER to iban gb82", "Ｗｉｒｅ ｔｒａｎｓｆｅｒ to IBAN GB82", "transfer   to IBAN GB82 WEST 1234 5698 7654 32 on 12 March 2⁰04"):
        kept, refused = leads.check(corpus, [{"doc": "ABCD:ABCD00000001", "page": 1, "quote": wrote}])
        assert not refused and kept[0]["quote"] in page, wrote
    kept, refused = leads.check(corpus, [{"doc": "ABCD:ABCD00000001", "page": 1, "quote": "Wire transfer " * 5000}])
    assert not kept and "at most" in refused[0]["why"] and len(refused[0]["quote"]) < 100   # refused unread


def test_the_owner_reopens_a_lead_closed_cold(tmp_path, monkeypatch, pdfs):
    """Audit E5 (B20): a worker led astray closed it «cold» for ever; the owner opens it again, the case is told."""
    c = setup(tmp_path, monkeypatch, pdfs)
    one = c.post("/cases", json={"title": "Prova — piste"}).json()["id"]
    lead = c.post(f"/cases/{one}/leads", json={"what": "Who signed the bill of lading", "agent": "sniper"}).json()
    assert c.post(f"/leads/{lead['id']}/reopen", json={"why": "x"}).status_code == 422    # open: nothing to reopen
    work = c.post("/leads/claim", json={"worker": "w1"}).json()["lead"]
    c.post(f"/leads/{lead['id']}/report", json={"token": work["token"], "status": "cold", "summary": "nothing found at all"})
    assert c.post("/leads/claim", json={"worker": "w2"}).json() == {"lead": None}
    again = c.post(f"/leads/{lead['id']}/reopen", json={"why": "the worker searched the wrong words"})
    assert again.status_code == 200 and again.json()["status"] == "open" and again.json()["summary"] is None
    note = c.get(f"/cases/{one}").json()["diary"][-1]
    assert note["kind"] == "note" and "w1" in note["content"]["text"] and "nothing found at all" in note["content"]["text"]
    assert c.post("/leads/claim", json={"worker": "w2"}).json()["lead"]["id"] == lead["id"]  # in the queue again
    assert c.post("/leads/99999/reopen", json={}).status_code == 404


def test_the_autonomous_work_has_limits(tmp_path, monkeypatch, pdfs):
    from evidentia import leads
    c = setup(tmp_path, monkeypatch, pdfs)
    cid = c.post("/cases", json={"title": "Catena"}).json()["id"]
    parent = None
    for depth in range(leads.MAX_DEPTH + 1):
        r = c.post(f"/cases/{cid}/leads", json={"what": f"step {depth} of the chain of payments", "agent": "chains",
                                                "parent": parent}).json()
        assert r["depth"] == depth
        parent = r["id"]
    too_deep = c.post(f"/cases/{cid}/leads", json={"what": "one more step of the chain", "agent": "chains",
                                                   "parent": parent})
    assert too_deep.status_code == 422 and "deep" in too_deep.json()["detail"]
    for n in range(leads.MAX_OPEN - leads.MAX_DEPTH - 1):
        assert c.post(f"/cases/{cid}/leads", json={"what": f"lead number {n} here", "agent": "sniper"}).status_code == 200
    full = c.post(f"/cases/{cid}/leads", json={"what": "one lead too many", "agent": "sniper"})
    assert full.status_code == 422 and "still open" in full.json()["detail"]
    lid = c.get("/leads", params={"case": cid, "status": "open"}).json()["leads"][0]["id"]
    assert c.request("DELETE", f"/leads/{lid}", json={"why": "not worth it"}).json()["status"] == "dropped"
    assert c.post(f"/cases/{cid}/leads", json={"what": "one lead too many", "agent": "sniper"}).status_code == 200


def test_a_lease_that_runs_out_gives_the_lead_back(tmp_path, monkeypatch, pdfs):
    from evidentia import leads
    c = setup(tmp_path, monkeypatch, pdfs)
    cid = c.post("/cases", json={"title": "Pause"}).json()["id"]
    lid = c.post(f"/cases/{cid}/leads", json={"what": "who signed the bill of lading", "agent": "sniper"}).json()["id"]
    assert c.post("/leads/claim", json={"worker": "crashed"}).json()["lead"]["id"] == lid
    monkeypatch.setattr(leads, "LEASE", -1)
    monkeypatch.setattr(leads.time, "time", lambda: 4e9)
    assert c.post("/leads/claim", json={"worker": "next"}).json()["lead"]["worker"] == "next"


def test_copies_of_one_text_are_one_hit(tmp_path, monkeypatch, pdfs):
    from conftest import make_pdf
    make_pdf(pdfs / "ABCD00000009.pdf", ["Wire transfer to IBAN GB82 WEST 1234 5698 7654 32 on 12 March 2004. "
                                         "Received and recorded by the clerk of the office on the same day, copy to "
                                         "the file. ABCD_R1_00000009"])
    c = setup(tmp_path, monkeypatch, pdfs)
    hits = c.get("/search", params={"q": "wire transfer clerk"}).json()["hits"]
    assert len(hits) == 1 and len(hits[0]["copies"]) == 1


def test_a_long_question_is_capped_in_words_and_in_time(tmp_path, monkeypatch, pdfs):
    """Audit E6 (B21): a hundred words ran a hundred queries on the event loop; now 16 words, a time budget."""
    from evidentia import search, store
    setup(tmp_path, monkeypatch, pdfs)
    corpus = store.connect(tmp_path / "data", "corpus.db", readonly=True)
    asked = []
    real = search.search
    monkeypatch.setattr(search, "search", lambda con, w, *a: asked.append(w) or real(con, w, *a))
    out = search.ask(corpus, " ".join(f"word{i:03d}x" for i in range(100)))
    assert out["hits"] == [] and len(asked) <= 1 + search.TERMS_MAX
    monkeypatch.setattr(search, "TICK", 1)                                        # a tiny archive: look at every step
    late = search.ask(corpus, "Teterboro pallets", budget_s=-1)                  # past its time: partial, never a 500
    assert late["partial"] is True and late["hits"] == []
    assert search.ask(corpus, "Teterboro pallets")["hits"]                         # the handler is taken off again


def test_two_notices_on_one_form_with_another_amount_are_two_hits(tmp_path, monkeypatch, pdfs):
    """Audit E3 (B18): the same form, the same payee, another amount: 80 % of the words shared, and one vanished."""
    from conftest import make_pdf
    form = ("Payment notice: the bank of the office pays the consignee Acme Ltd the amount of {} dollars by wire "
            "transfer, received and recorded by the clerk on the same day, copy to the file.")
    make_pdf(pdfs / "ABCD00000011.pdf", [form.format("25000")])
    make_pdf(pdfs / "ABCD00000012.pdf", [form.format("98000")])
    c = setup(tmp_path, monkeypatch, pdfs)
    hits = c.get("/search", params={"q": "payment notice consignee"}).json()["hits"]
    assert {h["doc"] for h in hits} == {"ABCD:ABCD00000011", "ABCD:ABCD00000012"} and not any(h["copies"] for h in hits)


def test_a_quote_of_common_words_padded_with_spaces_is_not_evidence(tmp_path, monkeypatch, pdfs):
    """Audit, 10 Nov: «of          the» flattened to «of the» was on every page; now four words, twenty characters
    after the spaces are flattened, and one word that is not a common one."""
    from evidentia import leads, store
    c = setup(tmp_path, monkeypatch, pdfs)
    corpus = store.connect(tmp_path / "data", "corpus.db", readonly=True)
    tricks = ["of          the", "of\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0the", "on the same day", "to the file, copy to the"]
    kept, refused = leads.check(corpus, [{"doc": "ABCD:ABCD00000001", "page": 2, "quote": q} for q in tricks])
    assert kept == [] and len(refused) == 4
    kept, _ = leads.check(corpus, [{"doc": "ABCD:ABCD00000001", "page": 2, "quote": "Flight N908JE from Teterboro"}])
    assert len(kept) == 1
    assert c.get("/search", params={"q": "clerk", "n": -1}).json()["hits"].__len__() <= 1   # a negative n is one hit


def test_a_body_too_large_or_not_an_object_is_refused(tmp_path, monkeypatch, pdfs):
    c = setup(tmp_path, monkeypatch, pdfs)
    assert c.post("/cases", content=b"[1, 2]", headers={"content-type": "application/json"}).status_code == 400
    assert c.post("/cases", content=b"not json").status_code == 400
    assert c.post("/cases", content=b"{" + b" " * 1_000_001 + b"}").status_code == 400


def test_a_proposal_cannot_smuggle_another_agents_name(tmp_path, monkeypatch):
    """Audit, 10 Nov: a title with a newline and «name: sniper» re-parsed as the sniper."""
    from evidentia import agents
    import importlib
    env = tmp_path / ".env"
    env.write_text(f"EVD_DATA_DIR={tmp_path / 'data'}\n")
    monkeypatch.setenv("EVD_ENV_FILE", str(env))
    from evidentia import api
    importlib.reload(api)
    api.PROPOSED = tmp_path / "proposed"
    c = TestClient(api.app)
    card = {"name": "helper_x", "profile": "common", "title": "Helper\nname: sniper", "description": "Helps.",
            "instructions": "Help with everything you are asked. " * 5}
    assert c.post("/agents/proposed", json=card).status_code == 422
    (tmp_path / "proposed").mkdir(exist_ok=True)
    (tmp_path / "proposed" / "helper_x.md").write_text(agents.card_text({**card, "title": "Helper"}).replace(
        "name: helper_x", "name: sniper"))
    import pytest
    with pytest.raises(ValueError, match="its name"):
        agents.load(tmp_path / "proposed")


def test_a_report_after_the_lease_changed_hands_is_refused(tmp_path, monkeypatch, pdfs):
    """Audit, 11 Nov (B28): the lease checked, the pages read, then the UPDATE without looking at the lease again."""
    c = setup(tmp_path, monkeypatch, pdfs)
    from evidentia import leads
    one = c.post("/cases", json={"title": "Prova — affitto"}).json()["id"]
    lead = c.post(f"/cases/{one}/leads", json={"what": "Where did the pallets go", "agent": "sniper"}).json()
    token = c.post("/leads/claim", json={"worker": "slow"}).json()["lead"]["token"]
    real = leads.check

    def meanwhile(corpus, evidence, mask=None):          # the lease runs out and another worker takes it
        import sqlite3
        out = real(corpus, evidence, mask)
        con = sqlite3.connect(tmp_path / "data" / "cases.db")
        con.execute("UPDATE leads SET worker = 'fast', lease_hash = 'other' WHERE id = ?", (lead["id"],))
        con.commit()
        return out
    monkeypatch.setattr(leads, "check", meanwhile)
    r = c.post(f"/leads/{lead['id']}/report", json={"token": token, "status": "cold", "summary": "nothing about pallets"})
    assert r.status_code == 409
    assert c.get(f"/leads/{lead['id']}").json()["status"] == "working"            # the other worker's, untouched


def test_the_next_page_of_a_search_never_shows_a_hit_of_the_first(tmp_path, monkeypatch, pdfs):
    """Audit, 11 Nov (B29): offset counted passages while the hits are merged copies: the same text on page 3."""
    from conftest import make_pdf
    from evidentia import search, store
    text = "Ledger of the depot: pallets counted {} and signed by the clerk of the warehouse on the same day."
    for i in range(6):
        make_pdf(pdfs / f"ABCD0000010{i}.pdf", [text.format(1000 + i)])
        make_pdf(pdfs / f"ABCD0000020{i}.pdf", [text.format(1000 + i) + " ABCD_R1_0000020" + str(i)])   # its copy
    setup(tmp_path, monkeypatch, pdfs)
    corpus = store.connect(tmp_path / "data", "corpus.db", readonly=True)
    seen = []
    for off in (0, 2, 4):
        page = search.search(corpus, "ledger depot pallets", limit=2, offset=off)
        seen += [h["snippet"] for h in page]
    assert len(seen) == 6 and len(set(seen)) == 6
