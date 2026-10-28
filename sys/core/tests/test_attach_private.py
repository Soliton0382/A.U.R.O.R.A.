# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C453: a document attached to a chat is its user's — in their sealed memory, never the shared knowledge; in an
anonymous chat kept nowhere."""
from __future__ import annotations

from types import SimpleNamespace

from aurora import sys_context
from aurora.kno_attach import AttachmentHandler
from aurora.sol_index import Indexer
from aurora.sol_reader import VaultReader
from aurora.sol_writer import VaultWriter
from test_sol_index import FakeEncoder

NOTE = ("Nota inventata per il test: il codice del magazzino è TRIFOGLIOPALUDE77, la chiave sta sotto il vaso blu. "
        * 3).encode()


def _pipeline(cfg):
    return SimpleNamespace(writer=VaultWriter(cfg), indexer=Indexer(FakeEncoder(), cfg), reader=VaultReader(cfg),
                           llm=None, _for=lambda role: None)


def _disk(folder) -> bytes:
    return b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file()) if folder.exists() else b""


def test_an_attached_document_goes_to_its_user_s_sealed_memory_not_the_knowledge(cfg):
    p = _pipeline(cfg)
    out = AttachmentHandler(p, cfg).prepare([("nota.txt", NOTE, "text/plain")], "tienila a mente", lambda *a: None, "r1")
    assert out[0].kind == "document" and out[0].domain == "attachment" and "TRIFOGLIOPALUDE77" in out[0].solitons[0].text
    assert not p.reader.layout.shards("knowledge", "general") and not any(
        p.reader.layout.shards("knowledge", d) for d in p.reader.layout.domains("knowledge"))
    mine = p.reader.layout.shards("memory", "attachment")
    assert mine and b"TRIFOGLIOPALUDE77" not in _disk(p.reader.layout.base("memory"))
    assert "TRIFOGLIOPALUDE77" in p.reader.get(out[0].solitons[0].sid).text


def test_an_anonymous_chat_s_document_is_kept_nowhere(cfg):
    p = _pipeline(cfg)
    with sys_context.anonymous():
        out = AttachmentHandler(p, cfg).prepare([("nota.txt", NOTE, "text/plain")], "q", lambda *a: None, "r2")
    assert out[0].solitons and not p.reader.layout.shards("memory", "attachment")
    assert b"TRIFOGLIOPALUDE77" not in _disk(cfg.path("AURORA_VAULT_DIR"))
