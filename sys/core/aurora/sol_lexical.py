# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The knowledge searched by its words too (BM25, SQLite FTS5): the hybrid search.

The vector search misses passages a question names by their words — a numerical technique, a tool, a boundary
condition (M198: 11 of 93 sources in the vault and not among the 30 found). BM25 alone puts the right source in its
first 30 for 3 of those 11, and in its first 10 for 72 of the 93 (M200): the two miss different questions. Its
candidates join the vector ones and the re-ranker judges them all; nothing is chosen by the words alone.

    <AURORA_INDEX_DIR>/knowledge/lexical.db   p (fts5, contentless: the text stays in the vault), rows (rowid → sid),
                                              pos (domain → the vault position indexed, as the vectors' manifest)

Derived from the vault like the vectors: brought up to date with them (Indexer.update), rows dropped with them
(Indexer.drop), built again from the vault when missing. Knowledge only: the memory is a user's and small."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path

from . import sys_config, sys_log

BATCH = 2000
# English and Italian words that say nothing of a passage: a question's «what», «which», «qual», «della»
STOP = frozenset(
    "a an the of to in on for by with and or is are was were be been what which who whom how why when where that this "
    "these those does do did can could would should must it its as at from into than then there their such not no "
    "il lo la le gli i un una uno di del della dei degli delle da dal dalla in nel nella con su per tra fra e o che "
    "chi cosa come quale quali qual quando dove perché è sono era essere al alla ai agli alle si non più".split())
_lock = threading.Lock()


def path(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_INDEX_DIR") / "knowledge" / "lexical.db"


def _con(cfg: sys_config.Config, write: bool = False) -> sqlite3.Connection | None:
    p = path(cfg)
    if not write and not p.exists():
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    if write:
        con.executescript(
            "CREATE VIRTUAL TABLE IF NOT EXISTS p USING fts5(title, text, content='', contentless_delete=1, "
            "tokenize='porter unicode61 remove_diacritics 2');"
            "CREATE TABLE IF NOT EXISTS rows (rowid INTEGER PRIMARY KEY, sid TEXT NOT NULL UNIQUE, domain TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS pos (domain TEXT PRIMARY KEY, position TEXT)")
    return con


def update(cfg: sys_config.Config, reader, domain: str) -> int:
    """The passages of `domain` not in the words' index yet, from where it stopped. Returns how many were added."""
    if reader.layout.section_of(domain) != "knowledge":
        return 0
    with _lock:
        con = _con(cfg, write=True)
        try:
            row = con.execute("SELECT position FROM pos WHERE domain = ?", (domain,)).fetchone()
            after = tuple(json.loads(row[0])) if row and row[0] else None
            added, batch = 0, []

            def flush():
                nonlocal added
                for _, _, s in batch:
                    cur = con.execute("INSERT OR IGNORE INTO rows (sid, domain) VALUES (?, ?)", (s.sid, domain))
                    if cur.rowcount:
                        con.execute("INSERT INTO p (rowid, title, text) VALUES (?, ?, ?)", (cur.lastrowid, s.title, s.text))
                        added += 1
                con.execute("INSERT OR REPLACE INTO pos VALUES (?, ?)", (domain, json.dumps(list(batch[-1][:2]))))
                con.commit()
                batch.clear()

            for item in reader.iter_domain(domain, after=after):
                batch.append(item)
                if len(batch) >= BATCH:
                    flush()
            if batch:
                flush()
            return added
        finally:
            con.close()


def drop(cfg: sys_config.Config, sids) -> int:
    """The rows of `sids` removed (a document deleted from the vault). Returns how many."""
    sids = list(sids)
    if not sids or not path(cfg).exists():
        return 0
    with _lock:
        con = _con(cfg, write=True)
        try:
            n = 0
            for i in range(0, len(sids), 500):
                part = sids[i:i + 500]
                ids = [r[0] for r in con.execute(f"SELECT rowid FROM rows WHERE sid IN ({','.join('?' * len(part))})", part)]
                con.executemany("DELETE FROM p WHERE rowid = ?", [(x,) for x in ids])
                con.executemany("DELETE FROM rows WHERE rowid = ?", [(x,) for x in ids])
                n += len(ids)
            con.commit()
            return n
        finally:
            con.close()


def reset(cfg: sys_config.Config, domain: str) -> None:
    """A domain indexed again from its start (the vectors rebuilt)."""
    if not path(cfg).exists():
        return
    with _lock:
        con = _con(cfg, write=True)
        try:
            ids = [r[0] for r in con.execute("SELECT rowid FROM rows WHERE domain = ?", (domain,))]
            con.executemany("DELETE FROM p WHERE rowid = ?", [(x,) for x in ids])
            con.execute("DELETE FROM rows WHERE domain = ?", (domain,))
            con.execute("DELETE FROM pos WHERE domain = ?", (domain,))
            con.commit()
        finally:
            con.close()


def query(text: str) -> str:
    """A question as an FTS5 query: its meaningful words, any of them (BM25 weighs the rare ones)."""
    words = [w for w in re.findall(r"\w+", text.lower()) if len(w) > 2 and w not in STOP and not w.isdigit()]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words))


def search(cfg: sys_config.Config, texts: list[str], k: int) -> list[str]:
    """The sids of the best `k` passages by their words, for each text (a question and its translation), merged in
    order. Empty when the index is not built yet."""
    con = _con(cfg)
    if con is None or k <= 0:
        return []
    out: dict[str, None] = {}
    try:
        for t in texts:
            q = query(t)
            if not q:
                continue
            try:
                rows = con.execute("SELECT r.sid FROM (SELECT rowid, bm25(p, 2.0, 1.0) AS s FROM p WHERE p MATCH ? "
                                   "ORDER BY s LIMIT ?) x JOIN rows r ON r.rowid = x.rowid ORDER BY x.s", (q, k)).fetchall()
            except sqlite3.Error as e:                      # never a cost to the answer: the vector search stands
                sys_log.get_logger("search").warning("lexical search failed: %s", e)
                continue
            out.update(dict.fromkeys(r[0] for r in rows))
    finally:
        con.close()
    return list(out)
