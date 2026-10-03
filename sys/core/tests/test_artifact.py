# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Artifacts: only Aurora's own HTML pages run, sandboxed, with no network, through a short-lived token."""
import pytest

from aurora import doc_artifact, sys_uploads


def test_a_fragment_becomes_a_page_kept_with_the_turn(cfg):
    f = doc_artifact.create(cfg, "run1", "Grafico del seno", "<svg width='10'></svg><script>1</script>")
    assert f["mime"] == "text/html" and f["name"].startswith("grafico-del-seno-") and f["name"].endswith(".html")
    tok = doc_artifact.open_token(cfg, f["url"])
    page = doc_artifact.page(tok).decode()
    assert page.startswith("<!doctype html>") and "<title>Grafico del seno</title>" in page and "<svg" in page
    assert [i["run_id"] for i in sys_uploads.all_uploads(cfg)] == ["run1"]


def test_not_html_or_too_large_is_refused(cfg):
    with pytest.raises(ValueError):
        doc_artifact.create(cfg, "r", "x", "just words")
    with pytest.raises(ValueError):
        doc_artifact.create(cfg, "r", "x", "<p>" + "a" * doc_artifact.MAX_BYTES + "</p>")


def test_only_aurora_s_own_pages_run(cfg):
    mine = sys_uploads.public(sys_uploads.save(cfg, "r", "x.html", "text/html", b"<p>owner</p>", role="user"))
    with pytest.raises(FileNotFoundError):
        doc_artifact.open_token(cfg, mine["url"])                     # an HTML the owner uploaded never runs
    pic = sys_uploads.public(sys_uploads.save(cfg, "r", "a.png", "image/png", b"x", role="assistant"))
    for url in (pic["url"], "/etc/passwd", "/v1/aurora/uploads/../../x", ""):
        with pytest.raises(FileNotFoundError):
            doc_artifact.open_token(cfg, url)


def test_the_token_expires_and_the_sandbox_has_no_network(cfg, monkeypatch):
    f = doc_artifact.create(cfg, "r", "t", "<p>x</p>")
    tok = doc_artifact.open_token(cfg, f["url"])
    assert tok.startswith(doc_artifact.PREFIX)
    now = __import__("time").time()
    monkeypatch.setattr(doc_artifact.time, "time", lambda: now + doc_artifact.TTL_S + 1)
    with pytest.raises(PermissionError):
        doc_artifact.page(tok)
    with pytest.raises(PermissionError):
        doc_artifact.page("art-unknown")
    assert "connect-src 'none'" in doc_artifact.CSP and "sandbox allow-scripts;" in doc_artifact.CSP
    assert "allow-same-origin" not in doc_artifact.CSP
