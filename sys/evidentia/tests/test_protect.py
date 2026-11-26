# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F5 in the code (audit, 11 Nov, B24): a protected name masked in all the server gives and keeps; accounts and IBANs
masked in what is kept as an answer; the sources in clear. Invented names only."""
import importlib

from starlette.testclient import TestClient

from evidentia import protect


def test_the_forms_a_document_writes_a_name_in():
    ks = ("jane roe",)
    for said in ("Jane Roe", "JANE ROE", "Jane A. Roe", "Roe, Jane", "Roe, Jane A.", "Ms. Roe", "J. Roe", "Jane  Roe"):
        assert protect.names(f"signed by {said} on 3 May", ks) == f"signed by {protect.MASK} on 3 May", said
    assert protect.names("Richard Roe and Janet Roebuck", ks) == "Richard Roe and Janet Roebuck"   # namesakes stay
    assert protect.names("anything", ()) == "anything"
    assert protect.ids("to IBAN GB82 WEST 1234 5698 7654 32 today") == "to IBAN …5432 today"


def setup(tmp_path, monkeypatch, pdfs):
    from conftest import make_pdf
    from evidentia import inventory, network, store
    make_pdf(pdfs / "ABCD00000077.pdf", ["Statement of Jane A. Roe, received by the clerk of the office on 3 May 2004, "
                                         "copy to the file of the bank."])
    inventory.run(pdfs, tmp_path / "data", workers=1, say=lambda *_: None)
    network.protect(store.connect(tmp_path / "data", "findings.db"), "Jane Roe", "test")
    env = tmp_path / ".env"
    env.write_text(f"EVD_DATA_DIR={tmp_path / 'data'}\nEVD_SOURCES_DIR={pdfs}\n")
    monkeypatch.setenv("EVD_ENV_FILE", str(env))
    from evidentia import api
    importlib.reload(api)
    return TestClient(api.app)


def test_a_protected_name_never_leaves_the_server_and_is_never_kept(tmp_path, monkeypatch, pdfs):
    c = setup(tmp_path, monkeypatch, pdfs)
    page = c.get("/doc/ABCD:ABCD00000077/page/1").json()
    assert "Roe" not in page["text"] and protect.MASK in page["text"] and page["cite"] == "ABCD00000077 p. 1"
    hits = c.get("/search", params={"q": "statement clerk bank"}).json()["hits"]
    assert hits and not any("Roe" in h["snippet"] for h in hits)
    cid = c.post("/cases", json={"title": "Prova — protetti"}).json()["id"]
    c.post(f"/cases/{cid}/steps", json={"kind": "answer", "text": "Jane Roe paid IBAN GB82 WEST 1234 5698 7654 32."})
    export = c.get(f"/cases/{cid}/export.md").text
    assert "Roe" not in export and "…5432" in export and "GB82 WEST" not in export
    lead = c.post(f"/cases/{cid}/leads", json={"what": "Who is Jane Roe for the bank", "agent": "sniper"}).json()
    assert "Roe" not in lead["what"]
    token = c.post("/leads/claim", json={"worker": "w"}).json()["lead"]["token"]
    ev = [{"doc": "ABCD:ABCD00000077", "page": 1, "quote": "Statement of Jane A. Roe, received by the clerk"},
          {"doc": "ABCD:ABCD00000077", "page": 1, "quote": f"Statement of {protect.MASK}, received by the clerk"}]
    out = c.post(f"/leads/{lead['id']}/report", json={"token": token, "status": "done", "evidence": ev,
                                                       "summary": "Ms. Roe gave a statement to the clerk."}).json()
    assert [e["quote"] for e in out["evidence"]] == [ev[1]["quote"]] and "Roe" not in out["summary"]
    assert out["refused"][0]["why"] == "the page does not say these words"
    assert "Roe" not in c.get(f"/cases/{cid}").text                                # the diary as served
