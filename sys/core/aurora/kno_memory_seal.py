# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The memory of before sealed (N64, 29 Oct 2026): run by Aurora at her start, once, again after a stop halfway —
each step finds only what is left to do.

For every user:
 1. their memory rows still in plaintext sealed in place (text, title, extra: sol_vault.seal_row), then each changed
    shard emptied of its old pages (VACUUM, the WAL truncated): the plaintext does not stay in the file's free pages;
 2. their memory's vectors indexed again, sealed (a manifest without «sealed» is rebuilt);
 3. their dreams and thoughts copied into their diary (kno_diary, for the diary plugin).
Then, once: the documents attached to a chat that went to the shared knowledge (C453: extra.origin «chat») moved to
the memory of the user who attached them — the trace's import event names them while it is kept, the admin otherwise —
and taken out of the knowledge with their vectors, words, synapses and deductions; the shards they were in emptied of
their old pages too.
What this cannot reach: the backups made before (sealed by the backup's own key) and the traces of before, until
their days pass (sys_log)."""
from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

from . import kno_diary, sol_vault, sys_config, sys_log
from . import sys_users_layout as L
from .sol_schema import Soliton

def log():
    return sys_log.get_logger("memory_seal")


def _users(cfg: sys_config.Config) -> list[str | None]:
    base = cfg.base or cfg
    return sorted(L._registered(base)) if L.migrated(base) else [None]


def _empty_old_pages(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("VACUUM")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def seal_rows(cfg: sys_config.Config, user: str | None) -> int:
    layout, n = sol_vault.Layout.from_config(cfg, user), 0
    for dom in layout.domains("memory"):
        for shard in layout.shards("memory", dom):
            con = sqlite3.connect(shard, timeout=120, isolation_level=None)
            try:
                con.execute("BEGIN IMMEDIATE")
                rows = con.execute("SELECT rowid, sid, text, title, extra FROM solitons WHERE typeof(text) = 'text' "
                                   "OR typeof(title) = 'text' OR typeof(extra) = 'text'").fetchall()
                for rowid, sid, text, title, extra in rows:
                    plain = sol_vault.open_row(cfg, user, {"sid": sid, "text": text, "title": title, "extra": extra})
                    s = sol_vault.seal_row(cfg, user, plain)
                    con.execute("UPDATE solitons SET text=?, title=?, extra=? WHERE rowid=?",
                                (s["text"], s["title"], s["extra"], rowid))
                con.execute("COMMIT")
                if rows:
                    _empty_old_pages(con)
                    n += len(rows)
            finally:
                con.close()
    return n


def reindex(cfg: sys_config.Config, user: str | None, encoder) -> int:
    from .sol_index import Indexer
    ix, done = Indexer(encoder, cfg, user=user), 0
    for dom in ix.reader.layout.domains("memory"):
        m = ix.files(dom).read_manifest()
        if m is not None and not m.get("sealed"):
            ix.rebuild(dom)
            done += 1
    return done


def fill_diary(cfg: sys_config.Config, user: str | None) -> int:
    from .sol_reader import VaultReader
    r = VaultReader(cfg, user=user)
    if not r.layout.shards("memory", "reflection"):
        return 0
    items = [{"at": s.created_at, "type": kind, "text": s.text, "image": s.extra.get("image")}
             for kind in kno_diary.KINDS for s in r.of_type("reflection", kind, kno_diary.KEEP)]
    return kno_diary.add(cfg, items, user)


def _importer_of(cfg: sys_config.Config) -> dict[str, str]:
    """source_id -> the user who imported it, from the traces still kept (the ingest's «import» events)."""
    out: dict[str, str] = {}
    folder = cfg.path("AURORA_LOG_DIR") / "trace"
    for f in sorted(folder.glob("ingest*.jsonl*")) if folder.is_dir() else []:
        try:
            with (gzip.open(f, "rt", errors="replace") if f.suffix == ".gz" else open(f, errors="replace")) as h:
                for line in h:
                    if '"import"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    src = (e.get("payload") or {}).get("source_id")
                    if e.get("event") == "import" and src and e.get("user"):
                        out[src] = e["user"]
        except OSError:
            continue
    return out


def move_chat_documents(cfg: sys_config.Config, encoder) -> int:
    """C453: the chats' documents out of the shared knowledge, into their users' memory."""
    from . import kno_deduce, kno_synapse
    from .sol_index import Indexer
    from .sol_reader import VaultReader
    from .sol_writer import VaultWriter
    base = cfg.base or cfg
    admin = (L.migrated(base) or {}).get("admin")
    reader = VaultReader(cfg)
    found: dict[tuple[str, str], list[Soliton]] = {}
    for dom in reader.layout.domains("knowledge"):
        for shard in reader.layout.shards("knowledge", dom):
            con = sqlite3.connect(f"file:{shard}?mode=ro", uri=True, timeout=60)
            try:
                srcs = [r[0] for r in con.execute(
                    "SELECT DISTINCT source_id FROM solitons WHERE extra LIKE '%\"origin\": \"chat\"%'")]
            finally:
                con.close()
            for src in srcs:
                found[(dom, src)] = reader.by_source(dom, src, limit=10_000)
    if not found:
        return 0
    owners, moved = _importer_of(cfg), 0
    writer, kix = VaultWriter(cfg), Indexer(encoder, cfg)
    for (dom, src), sols in found.items():
        user = owners.get(src) or admin
        if user not in _users(cfg):
            user = admin
        mine = [Soliton.new(s.text, "attachment", "attachment", s.lang, f"attachment:{src}", title=s.title,
                            chunk_index=s.chunk_index, chunk_count=s.chunk_count, consolidated=True,
                            extra={"file": s.extra.get("file", ""), "moved_from": "knowledge"}) for s in sols]
        VaultWriter(cfg, user=user).add_many(mine)
        Indexer(encoder, cfg, user=user).update("attachment")
        sids = writer.remove_source(dom, src)
        kix.drop(dom, sids)
        kno_synapse.forget(cfg, sids)
        kno_deduce.forget(cfg, sids)
        moved += 1
        log().info("audit: a chat's document %s moved from the knowledge (%s) to %s's memory (%d passages)",
                 src, dom, user or "the admin", len(sids))
    for dom in {d for d, _ in found}:                    # the plaintext of the moved passages out of the files' pages
        for shard in reader.layout.shards("knowledge", dom):
            con = sqlite3.connect(shard, timeout=120, isolation_level=None)
            try:
                _empty_old_pages(con)
            finally:
                con.close()
    try:
        from . import sol_lexical
        con = sol_lexical._con(cfg, write=True)
        if con is not None:
            con.execute("INSERT INTO p(p) VALUES ('optimize')")   # the deleted words merged out of the segments
            con.commit()
            con.close()
    except Exception as e:                               # noqa: BLE001 — the words' index is rebuilt when missing
        log().warning("lexical index not optimised: %s", e)
    return moved


def run(cfg: sys_config.Config, encoder) -> dict:
    out = {"sealed": 0, "reindexed": 0, "diary": 0, "moved": 0}
    for user in _users(cfg):
        out["sealed"] += seal_rows(cfg, user)
        out["reindexed"] += reindex(cfg, user, encoder)
        out["diary"] += fill_diary(cfg, user)
    out["moved"] = move_chat_documents(cfg, encoder)
    if any(out.values()):
        log().info("audit: memory sealed: %s", out)
    return out
