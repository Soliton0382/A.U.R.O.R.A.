# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The foundations: identifiers checked, document ids for both collections, the archive, the inventory on real PDFs,
the search with no FTS5 syntax smuggled in, the case files."""
import re
from pathlib import Path

import pytest

from evidentia import cases, docids, identifiers as I, inventory, search, store


def test_identifiers_are_checked_before_they_may_link():
    assert I.iban_ok("GB82 WEST 1234 5698 7654 32") and not I.iban_ok("GB82 WEST 1234 5698 7654 33")   # one digit off
    assert I.aba_ok("011000015") and not I.aba_ok("011000016")
    assert I.bic_ok("DEUTDEFF") and I.bic_ok("DEUTDEFF500") and not I.bic_ok("DEUT1EFF")
    hits = I.find("SWIFT: DEUTDEFF, ABA 011000015, acct no. 1234-5678-90, $1,250,000.00 at 40.712800, -74.006000; N908JE")
    kinds = {h.kind: h for h in hits}
    assert kinds["bic"].valid and kinds["aba"].valid and kinds["account"].value == "1234567890"
    assert kinds["amount"].value == "USD 1,250,000.00" and kinds["coords"].valid and kinds["tail"].value == "N908JE"
    assert I.find("48°51'24\"N 2°21'03\"E")[0].value == "48.856667,2.350833"
    assert I.masked(I.Hit("iban", "GB82WEST12345698765432", 0, 0, True)) == "…5432"


def test_documents_of_both_collections():
    assert docids.parse("/x/ABCD00565614.pdf").key == "ABCD:ABCD00565614"
    assert docids.parse("REL-OGR-00012345.pdf") == docids.DocId("REL", "REL-OGR-00012345")
    assert docids.parse("whatever.pdf").collection == "OTHER"
    assert docids.parse("ABCD01234567_dup_123.pdf").key == "ABCD:ABCD01234567"     # the download's suffix, the same number
    assert docids.cite(docids.parse("ABCD00000001.pdf"), 2) == "ABCD00000001 p. 2"     # no official link guessed


def test_the_inventory_reads_pages_passages_and_identifiers_and_resumes(pdfs, tmp_path):
    data = tmp_path / "data"
    out = inventory.run(pdfs, data, workers=2, say=lambda *_: None)
    assert out == {"read": 3, "failed": 0, "moved": 0, "conflicts": 0, "seconds": out["seconds"]}
    corpus, findings = store.connect(data, "corpus.db", readonly=True), store.connect(data, "findings.db", readonly=True)
    d = dict(corpus.execute("SELECT pages, kind, status FROM documents WHERE doc = 'ABCD:ABCD00000001'").fetchone())
    assert d == {"pages": 2, "kind": "text", "status": "text"}
    assert "Teterboro" in search.page(corpus, "ABCD:ABCD00000001", 2)["text"]
    same = search.same_identifier(findings, "iban", "GB82WEST12345698765432")
    assert {(r["doc"], r["page"], r["valid"]) for r in same} == {("ABCD:ABCD00000001", 1, 1), ("ABCD:ABCD00000002", 1, 1)}
    assert inventory.run(pdfs, data, workers=2, say=lambda *_: None)["read"] == 0     # nothing new: nothing read again
    hits = search.search(corpus, "pallets Teterboro")
    assert hits and hits[0]["doc"] == "ABCD:ABCD00000001" and hits[0]["page"] == 2 and "«" in hits[0]["snippet"]


def test_a_pdf_pdftotext_cannot_read_fails_aloud_and_is_tried_again(pdfs, tmp_path):
    """Audit E4 (B19): a broken xref gave rc 0 and no text: 0 pages, «text», never tried again, «0 errors»."""
    bad = pdfs / "ABCD00000003.pdf"
    bad.write_bytes(b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\nxref garbage\n%%EOF\n")
    data = tmp_path / "data"
    out = inventory.run(pdfs, data, workers=1, say=lambda *_: None)
    assert out["failed"] == 1
    corpus = store.connect(data, "corpus.db", readonly=True)
    row = corpus.execute("SELECT status, error FROM documents WHERE doc = 'ABCD:ABCD00000003'").fetchone()
    assert row["status"] == "failed" and "pdftotext read no page" in row["error"]
    assert inventory.run(pdfs, data, workers=1, say=lambda *_: None)["read"] == 1      # tried again, the rest not


def test_a_search_cannot_smuggle_fts_syntax():
    # operators become plain quoted words, a phrase stays a phrase, «*» and one-letter words go
    assert search.fts_query('wuhan OR "bill of lading" NEAR(x) *') == '"bill of lading" "wuhan" "OR" "NEAR"'
    assert search.fts_query('" ; DROP') == '"DROP"' and search.fts_query("") == ""


def test_a_case_file_keeps_its_diary_and_table_and_goes_whole(tmp_path):
    store.create(tmp_path)
    con = store.connect(tmp_path, "cases.db")
    c = cases.create(con, "  Voli e pallet  ")
    assert c["title"] == "Voli e pallet" and c["steps"] == 0
    cases.step(con, c["id"], "search", {"q": "pallet Wuhan"}, ["ABCD:ABCD00000001"])
    assert cases.done_before(con, c["id"], "search", {"q": "pallet Wuhan"})                 # never redone
    with pytest.raises(ValueError):
        cases.step(con, c["id"], "search", {}, ["../../etc/passwd"])
    cases.set_table(con, c["id"], goal="trovare la destinazione", open_points=["chi firma la bolla"])
    assert cases.table(con, c["id"])["open_points"] == ["chi firma la bolla"]
    assert "Fonti: ABCD00000001" in cases.markdown(con, c["id"])                    # the sources written short (10 Nov)
    assert [x["id"] for x in cases.listing(con)] == [c["id"]]
    cases.delete(con, c["id"])
    assert cases.listing(con) == []


def test_an_image_collection_is_read_by_ocr(tmp_path):
    """10 Nov: the REL-OGR collection is images; an image's text comes from Tesseract, its pages marked «ocr»."""
    import subprocess
    from conftest import make_pdf
    from evidentia import inventory, store
    src = tmp_path / "ogr"
    src.mkdir()
    pdf = make_pdf(tmp_path / "x.pdf", ["FLIGHT MANIFEST DEPARTURE TETERBORO ARRIVAL PALM BEACH"])
    subprocess.run(["pdftoppm", "-png", "-r", "200", "-singlefile", str(pdf), str(src / "REL-OGR-00000042")], check=True)
    out = inventory.run(src, tmp_path / "data", 1, exts=inventory.IMAGES, say=lambda *_: None)
    if out["failed"]:                                 # C762: what the CI runner's Tesseract said, in the failure itself
        why = store.connect(tmp_path / "data", "corpus.db").execute("SELECT error FROM documents").fetchall()
        raise AssertionError(f"OCR of an image failed: {why}")
    assert out["read"] == 1
    db = store.connect(tmp_path / "data", "corpus.db")
    doc, kind = db.execute("SELECT doc, kind FROM documents").fetchone()
    text, source = db.execute("SELECT text, source FROM pages").fetchone()
    assert doc == "REL:REL-OGR-00000042" and kind == "image" and source == "ocr"
    assert "MANIFEST" in text and "TETERBORO" in text
    assert inventory.run(src, tmp_path / "data", 1, exts=inventory.IMAGES, say=lambda *_: None)["read"] == 0   # resumed


def test_the_same_folder_elsewhere_is_not_read_again(tmp_path):
    """Owner, 10 Nov: «se per errore gli ri do in pasto la medesima cartella in percorso diverso lui non riparte da capo».
    A document is known by its identity and size, not its path: moved, only its path changes; passages (and so the
    vectors made from them) stay; a file named like a known one with other bytes is a conflict, never written over."""
    import shutil
    from conftest import make_pdf
    a = tmp_path / "disk_a"
    a.mkdir()
    for n in (1, 2, 3):
        make_pdf(a / f"ABCD0000000{n}.pdf", [f"Flight log number {n} from Teterboro to Palm Beach, passengers listed"])
    data = tmp_path / "data"
    assert inventory.run(a, data, 1, say=lambda *_: None)["read"] == 3
    db = store.connect(data, "corpus.db")
    before = db.execute("SELECT id, doc FROM passages ORDER BY id").fetchall()
    b = tmp_path / "disk_b" / "moved"
    shutil.copytree(a, b)
    shutil.rmtree(a)
    out = inventory.run(b, data, 1, say=lambda *_: None)
    assert out["read"] == 0 and out["moved"] == 3 and out["conflicts"] == 0
    db = store.connect(data, "corpus.db")
    assert db.execute("SELECT id, doc FROM passages ORDER BY id").fetchall() == before
    assert {r[0] for r in db.execute("SELECT path FROM documents")} == {str(b / f"ABCD0000000{n}.pdf") for n in (1, 2, 3)}
    make_pdf(b / "ABCD00000002.pdf", ["A different document that happens to carry the same name, much longer text"])
    out = inventory.run(b, data, 1, say=lambda *_: None)
    assert out["read"] == 0 and out["conflicts"] == 1
    assert "Flight log number 2" in store.connect(data, "corpus.db").execute(
        "SELECT text FROM pages WHERE doc = 'ABCD:ABCD00000002'").fetchone()[0]


def test_no_folder_of_this_machine_is_in_the_repo():
    """Audit E8 (B23): the NAS user's name and the disk's UUID were in the schema and two scripts."""
    from evidentia import config
    root = Path(__file__).resolve().parents[1]
    for f in [root / "config" / "settings_schema.json", *(root / "script").glob("*.py"), *(root / "evidentia").glob("*.py")]:
        text = f.read_text(encoding="utf-8")
        assert "/run/media/" not in text and not re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", text), f
    cfg = config.Config({})
    with pytest.raises(config.ConfigError):
        cfg.path("EVD_SOURCES_DIR")                       # not set: said, never the project's own folder
