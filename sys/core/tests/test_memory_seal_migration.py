# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N64: the memory of before sealed at the start (kno_memory_seal) — rows, vectors, diary, the chats' documents moved."""
from __future__ import annotations

import sqlite3

from aurora import kno_diary, kno_memory_seal, sol_vault
from aurora import sol_schema as S
from aurora.sol_index import Indexer
from aurora.sol_reader import VaultReader
from aurora.sol_writer import VaultWriter
from test_sol_index import FakeEncoder

OLD = "Un ricordo di prima, in chiaro: il nonno inventato si chiamava Ottavino Brumaio."


def _plain_rows(cfg):
    """Rows as written before N64: inserted without the writer's seal."""
    w = VaultWriter(cfg)
    turn = S.Soliton.new(OLD, "conversation", "conversation", "it", "run:o1", extra={"role": "user"})
    dream = S.Soliton.new("Ho sognato Ottavino Brumaio su una barca di vetro.", "reflection", "reflection", "it",
                          "dream:1", consolidated=True, extra={"type": "dream"})
    for s in (turn, dream):
        shard = w._current_shard("memory", s.domain)
        with sol_vault.db(shard, ddl=sol_vault.SHARD_DDL) as con:
            row = s.to_row()
            con.execute(f"INSERT INTO solitons({','.join(sol_vault.COLUMNS)}) VALUES ({','.join('?' * len(sol_vault.COLUMNS))})",
                        [row[c] for c in sol_vault.COLUMNS])
    return w


def _bytes(folder):
    return b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())


def test_the_memory_of_before_is_sealed_once_and_reads_the_same(cfg):
    _plain_rows(cfg)
    enc = FakeEncoder()
    Indexer(enc, cfg).update("conversation")
    mem = VaultReader(cfg).layout.base("memory")
    assert b"Ottavino" in _bytes(mem)
    out = kno_memory_seal.run(cfg, enc)
    assert out["sealed"] == 2 and out["diary"] == 1
    assert b"Ottavino" not in _bytes(mem)                       # VACUUM: no old page left either
    assert OLD in {s.text for _, _, s in VaultReader(cfg).iter_domain("conversation")}
    assert kno_diary.read(cfg)[0]["type"] == "dream"
    assert kno_memory_seal.run(cfg, enc) == {"sealed": 0, "reindexed": 0, "diary": 0, "moved": 0}   # once


def test_a_chat_s_document_leaves_the_shared_knowledge_for_its_user_s_memory(cfg):
    w = VaultWriter(cfg)
    text = "Documento allegato inventato: la combinazione della cassaforte è LAMPONEGRIGIO42. " * 4
    doc = S.Soliton.new(text, "general", "knowledge", "it", "doc:abc", "nota", extra={"file": "nota.txt", "origin": "chat"})
    w.add_many([doc])
    enc = FakeEncoder()
    Indexer(enc, cfg).update("general")
    assert kno_memory_seal.move_chat_documents(cfg, enc) == 1
    r = VaultReader(cfg)
    assert not r.by_source("general", "doc:abc")
    moved = r.by_source("attachment", "attachment:doc:abc")
    assert moved and "LAMPONEGRIGIO42" in moved[0].text
    for shard in r.layout.shards("knowledge", "general"):
        with sqlite3.connect(shard) as con:
            assert not con.execute("SELECT count(*) FROM solitons").fetchone()[0]
        assert b"LAMPONEGRIGIO42" not in shard.read_bytes()
    assert b"LAMPONEGRIGIO42" not in _bytes(r.layout.base("memory"))
