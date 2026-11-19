# SPDX-License-Identifier: Apache-2.0
"""N141: a routine's new report sends the previous one to the trash, and nothing else."""
import logging

from aurora import doc_pdf, sys_routines, sys_trash, sys_uploads

LOG = logging.getLogger("test")


def _doc(cfg, tmp_path, name):
    d = tmp_path / "documents"
    d.mkdir(exist_ok=True)
    cfg.values.update(AURORA_DOCUMENTS_DIR=str(d), AURORA_TRASH_ENABLED=True, AURORA_TRASH_DAYS=30)
    f = d / name
    f.write_bytes(b"%PDF-1.4")
    return f


def _entry(name, mime="application/pdf"):
    return {"name": name, "url": f"/v1/aurora/documents/{name}", "mime": mime}


def test_the_previous_report_goes_to_the_trash_and_its_link_with_it(cfg, tmp_path, monkeypatch):
    old = _doc(cfg, tmp_path, "old.pdf")
    new = _doc(cfg, tmp_path, "new.pdf")
    monkeypatch.setattr(doc_pdf, "made_by_aurora", lambda p: True)
    sys_uploads.link(cfg, "run1", "old.pdf", "/v1/aurora/documents/old.pdf", "application/pdf")
    assert sys_routines.retire_reports(cfg, {"id": "r", "last_files": [_entry("old.pdf")]}, "new.pdf", LOG) == 1
    assert not old.exists() and new.exists()
    assert [i["name"] for i in sys_trash.items(cfg)] == ["old.pdf"]
    assert not [i for i in sys_uploads._index(cfg) if i.get("link") == "/v1/aurora/documents/old.pdf"]


def test_the_new_report_a_foreign_pdf_and_other_files_stay(cfg, tmp_path, monkeypatch):
    new = _doc(cfg, tmp_path, "new.pdf")
    mine = _doc(cfg, tmp_path, "mine.pdf")
    text = _doc(cfg, tmp_path, "note.txt")
    monkeypatch.setattr(doc_pdf, "made_by_aurora", lambda p: p.name != "mine.pdf")
    files = [_entry("new.pdf"), _entry("mine.pdf"), _entry("note.txt", "text/plain")]
    assert sys_routines.retire_reports(cfg, {"id": "r", "last_files": files}, "new.pdf", LOG) == 0
    assert new.exists() and mine.exists() and text.exists() and sys_trash.items(cfg) == []


def test_a_path_in_the_url_is_refused(cfg, tmp_path, monkeypatch):
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"%PDF-1.4")
    _doc(cfg, tmp_path, "new.pdf")
    monkeypatch.setattr(doc_pdf, "made_by_aurora", lambda p: True)
    bad = {"name": "x", "url": "/v1/aurora/documents/../secret.pdf", "mime": "application/pdf"}
    assert sys_routines.retire_reports(cfg, {"id": "r", "last_files": [bad]}, "new.pdf", LOG) == 0
    assert outside.exists()
