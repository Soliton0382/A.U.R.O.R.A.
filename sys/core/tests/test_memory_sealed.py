# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N64: a user's memory (STM and LTM) never in plaintext on disk — its rows and its vectors — and read back the same."""
from __future__ import annotations

import sqlite3

import numpy as np

from aurora import sol_schema as S
from aurora import sol_vault
from aurora.sol_index import Indexer, IndexSet
from aurora.sol_reader import VaultReader
from aurora.sol_writer import VaultWriter
from test_sol_index import FakeEncoder

SECRET = "La mia gatta immaginaria si chiama Briciolarda e il codice del cancello è QUARZOVELLUTO19."


def _turns():
    return [S.Soliton.new(SECRET, "conversation", "conversation", "it", "run:x1", extra={"role": "user", "run_id": "x1"}),
            S.Soliton.new("Ricevuto: la gatta Briciolarda, il cancello QUARZOVELLUTO19.", "conversation", "conversation",
                          "it", "run:x1", extra={"role": "assistant", "run_id": "x1"}),
            S.Soliton.new("Ho sognato una gatta di nome Briciolarda che apriva un cancello di quarzo.", "reflection",
                          "reflection", "it", "rem:dream", consolidated=True, extra={"type": "dream"})]


def _disk(folder) -> bytes:
    return b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())


def test_the_memory_on_disk_holds_no_word_of_the_chat_and_reads_back(cfg):
    w = VaultWriter(cfg)
    assert len(w.add_many(_turns()).written) == 3
    r = VaultReader(cfg)
    mem = r.layout.base("memory")
    raw = _disk(mem)
    for word in (b"Briciolarda", b"QUARZOVELLUTO19", b"assistant", b'"role"'):
        assert word not in raw                                       # text, title and extra sealed (the source id,
                                                                     # a kind and an id, stays plain for the queries)
    turns = r.recent(5)
    assert {t.text for t in turns} >= {SECRET} and all(t.extra.get("run_id") == "x1" for t in turns)
    assert [d.text[:12] for d in r.of_type("reflection", "dream", 5)] == ["Ho sognato u"]
    assert r.of_type("reflection", "dream", 5, text="quarzo") and not r.of_type("reflection", "dream", 5, text="nulla")


def test_a_row_of_before_still_reads_and_the_plain_columns_still_query(cfg):
    w = VaultWriter(cfg)
    w.add_many(_turns()[:1])
    shard = VaultReader(cfg).layout.shards("memory", "conversation")[0]
    with sqlite3.connect(shard) as con:                              # a row written before N64, in plaintext
        old = S.Soliton.new("Una riga di prima, in chiaro.", "conversation", "conversation", "it", "run:old",
                            extra={"role": "user"})
        row = old.to_row()
        con.execute(f"INSERT INTO solitons(rowid,{','.join(sol_vault.COLUMNS)}) VALUES "
                    f"(99,{','.join('?' * len(sol_vault.COLUMNS))})", [row[c] for c in sol_vault.COLUMNS])
        assert con.execute("SELECT count(*) FROM solitons WHERE consolidated=0").fetchone()[0] == 2
    texts = {s.text for s in VaultReader(cfg).iter_domain_all("conversation")} if hasattr(VaultReader, "iter_domain_all") \
        else {s.text for _, _, s in VaultReader(cfg).iter_domain("conversation")}
    assert "Una riga di prima, in chiaro." in texts and SECRET in texts


def test_the_memory_vectors_are_sealed_and_still_found(cfg):
    VaultWriter(cfg).add_many(_turns())
    enc = FakeEncoder()
    ix = Indexer(enc, cfg)
    ix.update("conversation")
    f = ix.files("conversation")
    m = f.read_manifest()
    assert m.get("sealed") and m["count"] == 2
    plain = np.ascontiguousarray(enc.encode_documents([SECRET]), dtype=np.float16).tobytes()
    assert plain not in f.vectors.read_bytes() and not f.hnsw.exists()
    hits = IndexSet(cfg).search(enc.encode_queries([SECRET]), 1, sections={"memory"})
    assert hits[0] and hits[0][0][2] == "memory" and hits[0][0][1] > 0.99
