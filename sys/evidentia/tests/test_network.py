# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""R20 (owner, 10 Nov: «i movimenti laterali in una rete network»): who wrote to whom from the e-mail headers, each
tie of a stated kind with its message; private persons by label, protected names never; the chain between two."""
import importlib
import sqlite3

from starlette.testclient import TestClient

from conftest import make_pdf


def mail(frm, to, day, subject, cc=""):
    return f"From: {frm} Sent: {day} To: {to}" + (f" Cc: {cc}" if cc else "") + f" Subject: {subject} Body text here."


def setup(tmp_path, monkeypatch, peers=2, docs=2):
    from evidentia import inventory, network, store
    monkeypatch.setattr(network, "PUBLIC_PEERS", peers)       # who may be named is decided when the network is built
    monkeypatch.setattr(network, "PUBLIC_DOCS", docs)
    src = tmp_path / "src"
    src.mkdir()
    pages = [mail("Ada Lovelace", "Bob Baker", "Monday, March 3, 2014 9:00 AM", "Dinner"),
             mail("Bob Baker", "Ada Lovelace; Carl Cole", "Tuesday, March 4, 2014", "Re: Dinner", cc="Dora Dunn"),
             mail("Carl Cole", "Bob Baker", "Friday, May 2, 2014", "Introduction"),
             mail("Carl Cole", "Eve Evans <eve@example.org>", "June 1, 2014", "The fund"),
             mail("Eve Evans <eve@example.org>", "Carl Cole", "June 2, 2014", "Re: The fund"),
             mail("Rare Person", "Ada Lovelace", "July 1, 2014", "hello")]
    for i, p in enumerate(pages):
        make_pdf(src / f"ABCD0000010{i}.pdf", [p + " Received and recorded by the clerk, copy to the file."])
    data = tmp_path / "data"
    inventory.run(src, data, workers=1, say=lambda *_: None)
    f = sqlite3.connect(data / "findings.db")
    network.build(store.connect(data, "corpus.db", readonly=True), f, say=lambda *_: None)
    env = tmp_path / ".env"
    env.write_text(f"EVD_DATA_DIR={data}\n")
    monkeypatch.setenv("EVD_ENV_FILE", str(env))
    from evidentia import api
    importlib.reload(api)
    return TestClient(api.app), f, network


def test_ties_are_read_from_headers_with_their_kind_and_message(tmp_path, monkeypatch):
    c, f, N = setup(tmp_path, monkeypatch)
    out = c.get("/network/contacts", params={"name": "Baker, Bob"}).json()
    ties = {(x["name"], x["tie"]) for x in out["contacts"]}
    assert ("Ada Lovelace", "wrote_to") in ties and ("Ada Lovelace", "wrote_to_by") in ties
    assert ("Carl Cole", "wrote_to") in ties and any(t == "copied" for _, t in ties)
    assert all(x["seen_in"] for x in out["contacts"])
    msgs = c.get("/network/between", params={"a": "Ada Lovelace", "b": "Bob Baker"}).json()["messages"]
    assert [m["day"] for m in msgs] == ["2014-03-03", "2014-03-04"] and msgs[0]["doc"].startswith("ABCD:")
    names = {x["name"] for x in c.get("/network/contacts", params={"name": "Ada Lovelace"}).json()["contacts"]}
    assert not any("Rare" in n for n in names) and any(n.startswith("persona privata") for n in names)   # by label


def test_a_chain_goes_through_public_people_and_never_a_protected_one(tmp_path, monkeypatch):
    c, f, N = setup(tmp_path, monkeypatch)
    ch = c.get("/network/path", params={"a": "Ada Lovelace", "b": "Eve Evans"}).json()["chain"]
    assert [x["to"] for x in ch][-1] == "Eve Evans" and len(ch) == 3 and all(x["doc"] for x in ch)
    N.protect(f, "Carl Cole", "test")
    assert c.get("/network/path", params={"a": "Ada Lovelace", "b": "Eve Evans"}).json()["chain"] == []
    # a protected name answers as a name nobody has: no 403, no count in stats (B16)
    got, none = (c.get("/network/contacts", params={"name": n}) for n in ("Carl Cole", "Zed Nobody"))
    assert got.status_code == none.status_code == 200 and got.json()["contacts"] == none.json()["contacts"] == []
    assert {k: v for k, v in got.json()["person"].items() if k not in ("name", "key")} == \
           {k: v for k, v in none.json()["person"].items() if k not in ("name", "key")}
    assert c.get("/network/between", params={"a": "Carl Cole", "b": "Bob Baker"}).json()["messages"] == []
    assert c.get("/network/path", params={"a": "Carl Cole", "b": "Eve Evans"}).json()["chain"] == []
    assert "protected" not in c.get("/network/stats").json()
    assert "Carl Cole" not in {x["name"] for x in c.get("/network/contacts", params={"name": "Bob Baker"}).json()["contacts"]}


def test_names_and_kinds():
    from evidentia import network as N
    assert N.key("Rossi, Mario E.") == N.key("Mario E. Rossi") == N.key("Mr Mario Rossi") == "mario rossi"
    assert N.key("Luca Luca Bianchi") == "luca bianchi" and N.key("Dr Ann Lee") == "dr ann lee"
    assert N.messages("From: Sent: Monday To: Gary Stein Subject: x") == []          # a redacted sender: no tie
    assert N.kind_of("UNITED STATES DISTRICT COURT Case No. 1") == "court"
    assert N.aliases("From: Mario Rossi <mrossi@example.com>") == [("mrossi@example.com", "mario rossi")]


def test_a_part_of_a_name_finds_the_people_it_fits(tmp_path, monkeypatch):
    """Owner, 10 Nov: «anche solo un nome o un cognome o suffissi come president»."""
    c, f, N = setup(tmp_path, monkeypatch, peers=1, docs=1)
    assert [p["name"] for p in c.get("/network/people", params={"q": "cole"}).json()["people"]] == ["Carl Cole"]
    assert c.get("/network/contacts", params={"name": "Cole"}).json()["person"]["name"] == "Carl Cole"   # one fits
    amb = c.get("/network/contacts", params={"name": "a"})                       # too short: no word to look for
    assert amb.status_code == 422
    two = c.get("/network/contacts", params={"name": "e"}).status_code
    assert two in (300, 422)


def test_a_private_label_is_keyed_and_an_asked_private_person_is_not_called_public(tmp_path, monkeypatch):
    """Audit, 11 Nov (B25): the label was sha256(key)[:6], no salt — whoever guessed a name confirmed its tie; a
    private person asked by name came back «public: true»."""
    import hashlib
    c, f, N = setup(tmp_path, monkeypatch)
    rare = c.get("/network/contacts", params={"name": "Ada Lovelace"}).json()["contacts"]
    labels = [x["name"] for x in rare if x["name"].startswith("persona privata")]
    assert labels and all(lab[-6:] != hashlib.sha256(N.key("Rare Person").encode()).hexdigest()[:6] for lab in labels)
    assert labels == [x["name"] for x in c.get("/network/contacts", params={"name": "Ada Lovelace"}).json()["contacts"]
                      if x["name"].startswith("persona privata")]                  # stable
    who = c.get("/network/contacts", params={"name": "Rare Person"}).json()["person"]
    assert who["public"] is False and who["asked"] is True and who["name"] == "Rare Person"
