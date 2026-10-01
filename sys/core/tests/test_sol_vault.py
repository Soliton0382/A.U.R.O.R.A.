# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import sqlite3

import pytest

from aurora import sol_schema as S
from aurora import sol_vault
from aurora.sol_reader import VaultReader
from aurora.sol_writer import VaultWriter

LONG = "Solitary waves in shallow water were first described by John Scott Russell in 1834. " * 5


def paper(i, domain="physics", text=None):
    return S.Soliton.new(text or f"{LONG} Variant {i}.", domain, "knowledge", "en", f"arxiv:{i}",
                         title=f"Paper {i}", chunk_index=0, chunk_count=1)


def turn(text, t):
    return S.Soliton.new(text, "conversation", "conversation", "it", "session:1",
                         created_at=f"2026-09-30T10:{t:02d}:00.000+00:00")


def test_write_and_read_back(cfg):
    w, r = VaultWriter(cfg), VaultReader(cfg)
    sols = [paper(i) for i in range(5)] + [paper(9, domain="law_it")]
    rep = w.add_many(sols)
    assert len(rep.written) == 6 and not rep.rejected and not rep.duplicates
    assert r.get(sols[0].sid) == sols[0]
    assert set(r.get_many([s.sid for s in sols])) == {s.sid for s in sols}
    assert r.count() == {"law_it": 1, "physics": 5}
    vault = cfg.path("AURORA_VAULT_DIR")
    assert (vault / "knowledge" / "physics" / "0001.db").exists()
    assert (vault / "knowledge" / "registry.db").exists()


def test_duplicates_are_skipped_across_calls_and_sources(cfg):
    w = VaultWriter(cfg)
    first = paper(1)
    again = S.Soliton.new(first.text, "physics", "knowledge", "en", "other:source", title="same text")
    assert first.sid == again.sid
    w.add(first)
    rep = w.add_many([again, again])
    assert rep.written == [] and len(rep.duplicates) == 2
    assert VaultReader(cfg).count() == {"physics": 1}


def test_invalid_solitons_are_rejected_and_nothing_is_written(cfg):
    bad = S.Soliton.new("too short", "physics", "knowledge", "en", "x:1", chunk_index=2, chunk_count=3)
    rep = VaultWriter(cfg).add(bad)
    assert bad.sid in rep.rejected and rep.written == []
    assert VaultReader(cfg).count() == {}


def test_memory_lives_apart_from_knowledge(cfg):
    w = VaultWriter(cfg)
    w.add_many([paper(1), turn("ciao", 1)])
    vault = cfg.path("AURORA_VAULT_DIR")
    assert (vault / "memory" / "conversation" / "0001.db").exists()
    assert not (vault / "knowledge" / "conversation").exists()


def test_iter_domain_resumes_after_a_position(cfg):
    w, r = VaultWriter(cfg), VaultReader(cfg)
    w.add_many([paper(i) for i in range(10)])
    rows = list(r.iter_domain("physics"))
    assert len(rows) == 10
    key, row, _ = rows[3]
    rest = list(r.iter_domain("physics", after=(key, row)))
    assert [x[2].sid for x in rest] == [x[2].sid for x in rows[4:]]


def test_shard_rollover(cfg):
    w, r = VaultWriter(cfg), VaultReader(cfg)
    w.max_bytes = 1                     # every write finds the current shard full
    for i in range(3):
        w.add(paper(i))
    shards = w.layout.shards("knowledge", "physics")
    assert [p.name for p in shards] == ["0001.db", "0002.db", "0003.db"]
    assert r.count() == {"physics": 3}
    assert len(list(r.iter_domain("physics"))) == 3


def test_recent_turns_newest_last(cfg):
    w, r = VaultWriter(cfg), VaultReader(cfg)
    w.add_many([turn(f"messaggio {t}", t) for t in (5, 1, 9, 3)])
    assert [s.text for s in r.recent(3)] == ["messaggio 3", "messaggio 5", "messaggio 9"]
    assert r.recent(0) == []


def test_consolidation_moves_stm_to_ltm_and_keeps_identity(cfg):
    w, r = VaultWriter(cfg), VaultReader(cfg)
    a, b = turn("uno", 1), turn("due", 2)
    w.add_many([a, b])
    assert w.consolidate([a.sid]) == 1
    assert w.consolidate([a.sid]) == 0
    got = r.get(a.sid)
    assert got.consolidated and got.consolidated_at and got.sid == a.sid
    assert not r.get(b.sid).consolidated


def test_check_and_repair_after_a_crash_between_shard_and_registry(cfg):
    w, r = VaultWriter(cfg), VaultReader(cfg)
    w.add(paper(1))
    orphan = paper(2)
    shard = w.layout.shards("knowledge", "physics")[0]
    con = sqlite3.connect(shard)
    row = orphan.to_row()
    con.execute(f"INSERT INTO solitons({','.join(sol_vault.COLUMNS)}) VALUES ({','.join('?' * len(sol_vault.COLUMNS))})",
                [row[c] for c in sol_vault.COLUMNS])
    con.commit()
    con.close()
    assert sol_vault.check(w.layout)["knowledge"]["unregistered"] == [orphan.sid]
    assert r.get(orphan.sid) is None
    sol_vault.repair(w.layout)
    report = sol_vault.check(w.layout)["knowledge"]
    assert report["unregistered"] == [] and report["rows"] == report["registered"] == 2
    assert VaultReader(cfg).get(orphan.sid) == orphan


def test_reset_memory_needs_confirmation_and_spares_knowledge(cfg):
    w = VaultWriter(cfg)
    w.add_many([paper(1), turn("ciao", 1)])
    with pytest.raises(PermissionError):
        w.reset_memory()
    assert w.reset_memory(confirm=True) >= 2
    r = VaultReader(cfg)
    assert r.count() == {"physics": 1}
    assert r.recent(5) == []
