# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Layout of the vault on disk, connections, and integrity check.

    <AURORA_VAULT_DIR>/knowledge/registry.db            sid -> shard, row
    <AURORA_VAULT_DIR>/knowledge/<domain>/0001.db       SQLite shard (WAL)
    <AURORA_VAULT_DIR>/memory/registry.db
    <AURORA_VAULT_DIR>/memory/<domain>/0001.db          conversations and reflections

Knowledge and memory never share a file: resetting the memory removes the
memory folder and nothing else. A domain gets a new shard when the current one
reaches AURORA_VAULT_SHARD_MAX_MB.

A soliton is written to its shard first and to the registry second (SQLite has
no atomic transaction across two WAL files). A crash in between leaves a row
the registry does not know: `check` finds it and `repair` registers it.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import sol_schema, sys_config

SECTIONS = ("knowledge", "memory")

SHARD_DDL = """
CREATE TABLE IF NOT EXISTS solitons (
    rowid INTEGER PRIMARY KEY,
    sid TEXT NOT NULL UNIQUE,
    text TEXT NOT NULL,
    domain TEXT NOT NULL,
    kind TEXT NOT NULL,
    lang TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    consolidated INTEGER NOT NULL,
    consolidated_at TEXT,
    created_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    extra TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS solitons_source ON solitons(source_id, chunk_index);
CREATE INDEX IF NOT EXISTS solitons_created ON solitons(created_at);
-- Highest rowid ever used: a deleted tail row must never give its rowid to a new soliton,
-- because the index remembers "indexed up to (shard, rowid)".
CREATE TABLE IF NOT EXISTS shard_meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""
REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS registry (
    sid TEXT PRIMARY KEY,
    shard TEXT NOT NULL,
    row INTEGER NOT NULL
) WITHOUT ROWID;
"""
COLUMNS = ("sid", "text", "domain", "kind", "lang", "source_id", "title", "chunk_index", "chunk_count",
           "consolidated", "consolidated_at", "created_at", "schema_version", "extra")


def _wal(con: sqlite3.Connection) -> None:
    """WAL is stored in the file: set it once. Two processes creating the same new file both ask for
    it, and SQLite answers "locked" at once instead of waiting: retry for a moment."""
    for attempt in range(100):
        try:
            if con.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                con.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) or attempt == 99:
                raise
            time.sleep(0.05)


def connect(path: Path, readonly: bool = False, ddl: str | None = None) -> sqlite3.Connection:
    # busy_timeout first: every statement after it, WAL switch and DDL included, waits for a
    # concurrent writer instead of failing with "database is locked" (found by test_concurrency).
    if readonly:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False, timeout=10)
        con.execute("PRAGMA busy_timeout=10000")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path, check_same_thread=False, timeout=10)
        con.execute("PRAGMA busy_timeout=10000")
        _wal(con)
        con.execute("PRAGMA synchronous=NORMAL")
        if ddl:
            con.executescript(ddl)
    con.row_factory = sqlite3.Row
    return con


@contextmanager
def db(path: Path, readonly: bool = False, ddl: str | None = None):
    """Connection that commits on success, rolls back on error, and is always closed."""
    con = connect(path, readonly=readonly, ddl=ddl)
    try:
        yield con
        if not readonly:
            con.commit()
    except BaseException:
        if not readonly:
            con.rollback()
        raise
    finally:
        con.close()


@dataclass
class Layout:
    root: Path
    taxonomy: dict[str, dict]
    memory: Path | None = None          # a user's memory folder (multi-user, U3); None: <root>/memory

    @classmethod
    def from_config(cls, cfg: sys_config.Config, user: str | None = None) -> "Layout":
        from . import sys_users_layout
        mem = sys_users_layout.place(cfg, "memory", user)        # no user after the migration: the admin's
        return cls(cfg.path("AURORA_VAULT_DIR"), sol_schema.load_taxonomy(), mem)

    def base(self, section: str) -> Path:
        return self.memory if section == "memory" and self.memory is not None else self.root / section

    def section_of(self, domain: str) -> str:
        return "memory" if self.taxonomy[domain].get("memory") else "knowledge"

    def registry(self, section: str) -> Path:
        return self.base(section) / "registry.db"

    def shards(self, section: str, domain: str) -> list[Path]:
        return sorted((self.base(section) / domain).glob("[0-9][0-9][0-9][0-9].db"))

    def domains(self, section: str) -> list[str]:
        base = self.base(section)                      # only real domains: users/ is not one (U3)
        return sorted(p.name for p in base.iterdir() if p.is_dir() and p.name in self.taxonomy) if base.is_dir() else []

    def shard_key(self, path: Path) -> str:
        """Shard as stored in the registry: '<domain>/<nnnn>.db', relative to its section."""
        return f"{path.parent.name}/{path.name}"

    def shard_path(self, section: str, key: str) -> Path:
        return self.base(section) / key


def check(layout: Layout) -> dict:
    """Compare shards and registries: rows without registry entry, entries without row."""
    report = {}
    for section in SECTIONS:
        reg_path = layout.registry(section)
        registered = {}
        if reg_path.exists():
            with db(reg_path, readonly=True) as reg:
                registered = {r["sid"]: (r["shard"], r["row"]) for r in reg.execute("SELECT sid, shard, row FROM registry")}
        in_shards = {}
        for domain in layout.domains(section):
            for shard in layout.shards(section, domain):
                with db(shard, readonly=True) as con:
                    for r in con.execute("SELECT rowid, sid FROM solitons"):
                        in_shards[r["sid"]] = (layout.shard_key(shard), r["rowid"])
        report[section] = {
            "rows": len(in_shards), "registered": len(registered),
            "unregistered": sorted(set(in_shards) - set(registered)),
            "dangling": sorted(set(registered) - set(in_shards)),
            "misplaced": sorted(s for s in set(in_shards) & set(registered) if in_shards[s] != registered[s]),
        }
    return report


def repair(layout: Layout) -> dict:
    """Register unregistered rows, drop dangling entries, fix misplaced ones."""
    report = check(layout)
    for section in SECTIONS:
        r = report[section]
        if not (r["unregistered"] or r["dangling"] or r["misplaced"]):
            continue
        locate = {}
        for domain in layout.domains(section):
            for shard in layout.shards(section, domain):
                with db(shard, readonly=True) as con:
                    for row in con.execute("SELECT rowid, sid FROM solitons"):
                        locate[row["sid"]] = (layout.shard_key(shard), row["rowid"])
        with db(layout.registry(section), ddl=REGISTRY_DDL) as reg:
            reg.executemany("DELETE FROM registry WHERE sid=?", [(s,) for s in r["dangling"]])
            reg.executemany("INSERT OR REPLACE INTO registry(sid, shard, row) VALUES (?,?,?)",
                            [(s, *locate[s]) for s in r["unregistered"] + r["misplaced"]])
    return report
