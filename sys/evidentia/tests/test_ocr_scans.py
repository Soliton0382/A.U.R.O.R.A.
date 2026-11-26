# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C751: the scanned pages without text are found, read, written as the inventory writes a page, and never read twice."""
from evidentia import ocr_scans, store


def _corpus(tmp_path):
    store.create(tmp_path)
    c = store.connect(tmp_path, "corpus.db")
    c.execute("INSERT INTO documents(doc, collection, number, path, pages, kind, status) VALUES ('A','X',1,'/a.pdf',2,'scan','text')")
    c.execute("INSERT INTO documents(doc, collection, number, path, pages, kind, status) VALUES ('B','X',2,'/b.pdf',1,'text','text')")
    c.executemany("INSERT INTO pages(doc, page, text, chars, source) VALUES (?,?,?,?, 'pdf')",
                  [("A", 1, "", 0), ("A", 2, "a page that has its own words already printed", 46), ("B", 1, "", 0)])
    c.commit()
    return c


def test_only_scanned_pages_without_text_and_each_once(tmp_path, monkeypatch):
    c = _corpus(tmp_path)
    import pickle
    assert [(d, p) for d, p, _ in ocr_scans.todo(c)] == [("A", 1)]
    pickle.dumps(ocr_scans.todo(c))                      # the jobs go to worker processes (a Row cannot)
    words = "Wire transfer to account GB82WEST12345698765432 on the 3rd of May, signed by the bank's officer"
    monkeypatch.setattr(ocr_scans, "read_page", lambda job: {"doc": job[0], "page": job[1], "text": words})
    monkeypatch.setattr(ocr_scans, "ProcessPoolExecutor", _Serial)
    out = ocr_scans.run(tmp_path, 1)
    assert out == {**out, "pages": 1, "with_text": 1, "failed": 0}
    c = store.connect(tmp_path, "corpus.db")
    assert tuple(c.execute("SELECT source, chars FROM pages WHERE doc='A' AND page=1").fetchone()) == ("ocr-page", len(words))
    assert c.execute("SELECT COUNT(*) FROM passages_fts WHERE passages_fts MATCH 'transfer'").fetchone()[0] == 1
    f = store.connect(tmp_path, "findings.db")
    assert tuple(f.execute("SELECT value FROM identifiers WHERE kind='iban' AND doc='A' AND page=1").fetchone()) == ("GB82WEST12345698765432",)
    assert ocr_scans.todo(c) == []                       # read once: a second run has nothing to do


def test_a_failed_page_stays_to_be_read_again(tmp_path, monkeypatch):
    _corpus(tmp_path)
    monkeypatch.setattr(ocr_scans, "read_page", lambda job: {"doc": job[0], "page": job[1], "error": "tesseract rc 1"})
    monkeypatch.setattr(ocr_scans, "ProcessPoolExecutor", _Serial)
    assert ocr_scans.run(tmp_path, 1)["failed"] == 1
    assert len(ocr_scans.todo(store.connect(tmp_path, "corpus.db"))) == 1


class _Serial:
    def __init__(self, max_workers=1):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def map(self, fn, items, chunksize=1):
        return map(fn, items)
