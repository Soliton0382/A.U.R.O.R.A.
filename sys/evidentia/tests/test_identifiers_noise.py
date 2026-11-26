"""B2, B3 (measured on the archive, 12 Nov): an «IBAN» is a valid one or one of a country's exact length; a «tail» has
the form of a US registration, and a short one stands beside words of flying."""
from evidentia import identifiers as I


def kinds(text, kind):
    return [h.value for h in I.find(text) if h.kind == kind]


def test_securities_codes_run_into_a_word_are_not_ibans():
    assert kinds("ISIN GB0007188757SEDOL and XS0460546442SEDOL", "iban") == []
    assert kinds("IBAN GB82 WEST 1234 5698 7654 32", "iban") == ["GB82WEST12345698765432"]
    assert kinds("FR2330002004690000060269070 wire", "iban") == ["FR2330002004690000060269070"]   # France's 27, mod-97 off
    assert [h.valid for h in I.find("FR2330002004690000060269070") if h.kind == "iban"] == [False]


def test_a_tail_has_the_form_of_a_registration_and_a_short_one_needs_flying_around_it():
    assert kinds("the Gulfstream N908JE and N212JE", "tail") == ["N908JE", "N212JE"]
    assert kinds("see note N1 and N0V and N00000", "tail") == []
    assert kinds("flight log: aircraft N4G, pilot", "tail") == ["N4G"]
    assert kinds("N1O4 NI2AB", "tail") == []                            # I and O are never in a registration


def test_the_pages_already_read_are_found_again_with_todays_rules():
    import sqlite3
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import evd_reidentify as R
    corpus, findings = sqlite3.connect(":memory:"), sqlite3.connect(":memory:")
    corpus.execute("CREATE TABLE pages (doc TEXT, page INT, text TEXT)")
    corpus.execute("INSERT INTO pages VALUES ('ABCD:1', 1, ?)",
                   ("note N1" + " lorem" * 60 + " the jet N908JE, code GB0007188757SEDOL",))
    findings.execute("CREATE TABLE identifiers (kind, value, valid, doc, page, start, end)")
    findings.executemany("INSERT INTO identifiers VALUES (?,?,?,?,?,?,?)",
                         [("tail", "N1", 1, "ABCD:1", 1, 5, 7), ("tail", "N908JE", 1, "ABCD:1", 1, 20, 26),
                          ("iban", "GB0007188757SEDOL", 0, "ABCD:1", 1, 33, 50), ("amount", "USD 5", 1, "ABCD:1", 1, 0, 1)])
    assert R.again(corpus, findings, dry=True)["after"] == {"tail": 1}
    R.again(corpus, findings)
    assert sorted(r[0] for r in findings.execute("SELECT value FROM identifiers")) == ["N908JE", "USD 5"]
