# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💰 Follow the money: the fields of a wire or a statement read, amounts as written, the names kept by the archive's
rules (a protected one never; a private person never by name; an account shown by its last four digits)."""
from evidentia import money as M


def test_a_wire_s_fields_banks_and_days():
    text = ("OUTGOING WIRE TRANSFER Date: 03/14/2005 ORDERING CUSTOMER: Southern Trust Company Inc ACCOUNT 12345678 "
            "BENEFICIARY: Gotham Holdings LLC 2nd floor ACCOUNT NAME: Mario Esempio ABA 021000021 "
            "Intermediary JPMorgan Chase Bank of New York SWIFT CHASUS33 Amount USD 1,250,000.00")
    r = M.read_page(text)
    assert "Southern Trust Company Inc" in r["parties"] and "Gotham Holdings LLC" in r["parties"] and "Mario Esempio" in r["parties"]
    assert any("JPMorgan" in b for b in r["banks"]) and r["days"] == ["2005-03-14"]


def test_amounts_as_written():
    assert M.amount("USD 1,250,000.00") == ("USD", 1250000.0)
    assert M.amount("EUR 1.250.000,50") == ("EUR", 1250000.5)
    assert M.amount("CHF 950") == ("CHF", 950.0) and M.amount("nonsense") is None


def test_who_is_named_and_who_never():
    public = {"carlo pubblico"}
    assert M.shown("Gotham Holdings LLC", public, ()) == ("Gotham Holdings LLC", "org", 0)
    assert M.shown("Carlo Pubblico", public, ()) == ("Carlo Pubblico", "person", 0)
    name, kind, prot = M.shown("Mario Esempio", public, ())
    assert name.startswith("private person #") and "Mario" not in name and prot == 0
    assert M.shown("Anna Protetta", public, ("Anna Protetta",))[2] == 1           # a victim's or a redacted name: never
    assert M.mask_account("ACCT987654321") == "…4321"


def test_the_ties_are_kept_with_their_pages(tmp_path):
    from evidentia import store
    store.create(tmp_path)
    c, f = store.connect(tmp_path, "corpus.db"), store.connect(tmp_path, "findings.db")
    c.execute("INSERT INTO pages(doc, page, text, chars, source) VALUES ('X:1', 1, ?, 99, 'pdf')",
              ("BENEFICIARY: Gotham Holdings LLC ACCOUNT NAME: Mario Esempio wire USD 5,000.00",))
    f.executemany("INSERT INTO identifiers(kind, value, valid, doc, page, start, end) VALUES (?,?,1,'X:1',1,0,0)",
                  [("account", "11112222"), ("amount", "USD 5,000.00")])
    c.commit(); f.commit()
    db = M.open_db(tmp_path)
    out = M.run(c, f, say=lambda m: None, out=db)
    assert out["pages"] == 1 and out["nodes"] >= 3
    rep = M.report(db)
    assert rep["accounts"][0]["account"] == "…2222" and rep["orgs"][0]["name"] == "GOTHAM HOLDINGS LLC"
    assert rep["hubs"] and rep["hubs"][0]["accounts"] == 1 and rep["accounts"][0]["see"] == [["X:1", 1]]
    assert not any("Mario" in str(x) for x in rep.values())                       # a private person never by name


def test_a_signer_and_a_company_and_one_bank_by_its_name():
    assert M.split_party("LAUREN SAMPLE NYSG LLC") == ["LAUREN SAMPLE", "NYSG LLC"]
    assert M.split_party("JOHN ROE J EPSTEIN & CO") == ["JOHN ROE", "J EPSTEIN & CO"]
    assert M.split_party("Gotham Holdings LLC") == ["Gotham Holdings LLC"]
    assert M.split_party("Recipient JEANNE SAMPLE FINANCIAL TRUST") == ["JEANNE SAMPLE FINANCIAL TRUST"]
    assert M.bank_name("Image Fifth Third Bank") == "FIFTH THIRD BANK" and M.bank_name("FIFTH THIRD BANK") == "FIFTH THIRD BANK"
    assert M.bank_name("Bank") is None and M.bank_name("Joseph Roe. Wachovia Bank") == "WACHOVIA BANK"
    assert M.bank_name("Bank of America") == "BANK OF AMERICA"


def test_the_ocr_s_ways_of_writing_one_company_are_one():
    m = M.merge_orgs({"NYSG LLC": 23, "NYSO LLC": 3, "NVSG LLC": 2, "ZORRO DEVELOPMENT CORP": 5, "ZORRO DEVELOPMENT CORPORATIO": 2,
                      "J EPSTEIN & CO": 16, "J EPSTEIN A CO": 2, "KETTLE LLC": 20, "MAX FOUNDATION": 29})
    assert m["NYSO LLC"] == m["NVSG LLC"] == "NYSG LLC"
    assert m["ZORRO DEVELOPMENT CORPORATIO"] == "ZORRO DEVELOPMENT CORP" and m["J EPSTEIN A CO"] == "J EPSTEIN & CO"
    assert m["KETTLE LLC"] == "KETTLE LLC" and m["MAX FOUNDATION"] == "MAX FOUNDATION"     # different ones stay apart
