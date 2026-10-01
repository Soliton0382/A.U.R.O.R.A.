# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Writes solitons to the vault: validation, deduplication, shard rollover, consolidation.

Every soliton is validated against its schema before it is written; invalid
ones are refused with the reason, never stored half-right. A soliton whose sid
is already in the vault is skipped. Each call logs its counts and emits a trace
event, so what enters the vault is always visible.
"""
from __future__ import annotations

import shutil
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import sol_schema, sol_vault, sys_config, sys_log
from .sol_schema import Soliton

MIB = 1024 * 1024


def _next_rowid(con: sqlite3.Connection) -> int:
    """One past the highest rowid ever used in this shard, deleted rows included."""
    top = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM solitons").fetchone()[0]
    high = con.execute("SELECT value FROM shard_meta WHERE key='rowid_high'").fetchone()
    return max(top, high[0] if high else 0) + 1


@dataclass
class WriteReport:
    written: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    rejected: dict[str, list[str]] = field(default_factory=dict)   # sid -> problems


class VaultWriter:
    def __init__(self, cfg: sys_config.Config | None = None, component: str = "vault"):
        self.cfg = cfg or sys_config.get()
        self.layout = sol_vault.Layout.from_config(self.cfg)
        self.max_bytes = self.cfg["AURORA_VAULT_SHARD_MAX_MB"] * MIB
        self.min_chars = self.cfg["AURORA_CHUNK_MIN_CHARS"]
        self.component = component
        self.log = sys_log.get_logger(component)

    # ---- helpers -------------------------------------------------------------
    def _current_shard(self, section: str, domain: str) -> Path:
        shards = self.layout.shards(section, domain)
        if shards and shards[-1].stat().st_size < self.max_bytes:
            return shards[-1]
        number = int(shards[-1].stem) + 1 if shards else 1
        new = self.layout.root / section / domain / f"{number:04d}.db"
        if shards:
            self.log.info("shard rollover: %s reached %d MB, opening %s", shards[-1].name,
                          shards[-1].stat().st_size // MIB, new.name)
        return new

    # ---- writing ---------------------------------------------------------------
    def add(self, sol: Soliton) -> WriteReport:
        return self.add_many([sol])

    def add_many(self, solitons: Iterable[Soliton], run_id: str | None = None) -> WriteReport:
        report = WriteReport()
        groups: dict[tuple[str, str], list[Soliton]] = defaultdict(list)
        seen = set()
        for s in solitons:
            problems = sol_schema.validate(s, self.layout.taxonomy, self.min_chars)
            if problems:
                report.rejected[s.sid] = problems
                continue
            if s.sid in seen:
                report.duplicates.append(s.sid)
                continue
            seen.add(s.sid)
            groups[(self.layout.section_of(s.domain), s.domain)].append(s)

        for (section, domain), batch in groups.items():
            with sol_vault.db(self.layout.registry(section), ddl=sol_vault.REGISTRY_DDL) as reg:
                # Take the registry's write lock before reading it: in WAL mode a reader that later
                # writes after another writer committed fails at once (SQLITE_BUSY_SNAPSHOT, no
                # wait). Writers of a section queue here, then check, insert and register in turn.
                reg.execute("BEGIN IMMEDIATE")
                known = set()
                sids = [s.sid for s in batch]
                for i in range(0, len(sids), 500):
                    part = sids[i:i + 500]
                    q = f"SELECT sid FROM registry WHERE sid IN ({','.join('?' * len(part))})"
                    known.update(r["sid"] for r in reg.execute(q, part))
                fresh = [s for s in batch if s.sid not in known]
                report.duplicates += [s.sid for s in batch if s.sid in known]
                if not fresh:
                    continue
                shard = self._current_shard(section, domain)
                key = self.layout.shard_key(shard)
                placed = []
                with sol_vault.db(shard, ddl=sol_vault.SHARD_DDL) as con:
                    nxt = _next_rowid(con)
                    for s in fresh:
                        row = s.to_row()
                        try:
                            cur = con.execute(
                                f"INSERT INTO solitons(rowid,{','.join(sol_vault.COLUMNS)}) "
                                f"VALUES (?,{','.join('?' * len(sol_vault.COLUMNS))})",
                                [nxt] + [row[c] for c in sol_vault.COLUMNS])
                            nxt += 1
                        except sqlite3.IntegrityError:           # already in this shard
                            report.duplicates.append(s.sid)
                            continue
                        placed.append((s.sid, key, cur.lastrowid))
                raced = []
                for sid, k, rowid in placed:
                    cur = reg.execute("INSERT OR IGNORE INTO registry(sid, shard, row) VALUES (?,?,?)", (sid, k, rowid))
                    if cur.rowcount == 0:                          # another writer registered it first
                        raced.append((sid, rowid))
                    else:
                        report.written.append(sid)
                if raced:
                    with sol_vault.db(shard, ddl=sol_vault.SHARD_DDL) as con:
                        # same rule as remove_source: a deleted rowid is never given to another soliton
                        con.execute("INSERT INTO shard_meta(key, value) VALUES ('rowid_high', ?) "
                                    "ON CONFLICT(key) DO UPDATE SET value=max(value, excluded.value)",
                                    (_next_rowid(con) - 1,))
                        con.executemany("DELETE FROM solitons WHERE rowid=?", [(r,) for _, r in raced])
                    report.duplicates += [sid for sid, _ in raced]
            self.log.info("write %s/%s: %d written to %s", section, domain, len(placed) - len(raced), key)

        for sid, problems in report.rejected.items():
            # the short tail of a long document is dropped by design (AURORA_CHUNK_MIN_CHARS): not a problem
            by_design = all(p.startswith("fragment of a multi-chunk document") for p in problems)
            (self.log.info if by_design else self.log.warning)("rejected %s: %s", sid, "; ".join(problems))
        sys_log.trace(self.component, "vault.write",
                      {"written": len(report.written), "duplicates": len(report.duplicates),
                       "rejected": len(report.rejected)}, run_id=run_id)
        return report

    # ---- memory ----------------------------------------------------------------
    def consolidate(self, sids: Iterable[str], when: str | None = None, run_id: str | None = None) -> int:
        """Mark memory solitons as consolidated (STM -> LTM). Returns how many changed."""
        when = when or sol_schema.now_iso()
        by_shard: dict[str, list[int]] = defaultdict(list)
        reg_path = self.layout.registry("memory")
        if not reg_path.exists():
            return 0
        with sol_vault.db(reg_path, readonly=True) as reg:
            for sid in sids:
                r = reg.execute("SELECT shard, row FROM registry WHERE sid=?", (sid,)).fetchone()
                if r:
                    by_shard[r["shard"]].append(r["row"])
        changed = 0
        for key, rows in by_shard.items():
            with sol_vault.db(self.layout.shard_path("memory", key)) as con:
                cur = con.executemany("UPDATE solitons SET consolidated=1, consolidated_at=? "
                                      "WHERE rowid=? AND consolidated=0", [(when, r) for r in rows])
                changed += cur.rowcount
        self.log.info("consolidate: %d memory solitons moved from STM to LTM", changed)
        sys_log.trace(self.component, "vault.consolidate", {"changed": changed}, run_id=run_id)
        return changed

    def remove_source(self, domain: str, source_id: str) -> list[str]:
        """Delete every soliton of `source_id` in `domain` (shards and registry). Returns their sids.

        The index still holds their vectors: call Indexer.drop(domain, sids) right after."""
        section = self.layout.section_of(domain)
        removed: list[str] = []
        for shard in self.layout.shards(section, domain):
            with sol_vault.db(shard, ddl=sol_vault.SHARD_DDL) as con:
                sids = [r["sid"] for r in con.execute("SELECT sid FROM solitons WHERE source_id=?", (source_id,))]
                if sids:
                    con.execute("INSERT INTO shard_meta(key, value) VALUES ('rowid_high', ?) "
                                "ON CONFLICT(key) DO UPDATE SET value=max(value, excluded.value)",
                                (_next_rowid(con) - 1,))
                    con.execute("DELETE FROM solitons WHERE source_id=?", (source_id,))
                    removed += sids
        if removed:
            with sol_vault.db(self.layout.registry(section), ddl=sol_vault.REGISTRY_DDL) as reg:
                reg.executemany("DELETE FROM registry WHERE sid=?", [(x,) for x in removed])
        self.log.info("audit: removed source %s from %s: %d solitons", source_id, domain, len(removed))
        sys_log.trace(self.component, "vault.remove_source", {"domain": domain, "source_id": source_id,
                                                              "solitons": len(removed)})
        return removed

    def reset_memory(self, confirm: bool = False) -> int:
        """Delete every memory shard, its registry and its index. Knowledge is not touched."""
        if not confirm:
            raise PermissionError("reset_memory needs confirm=True")
        files = 0
        # the index goes too: stale vectors would point to conversations that no longer exist
        for target in (self.layout.root / "memory", self.cfg.path("AURORA_INDEX_DIR") / "memory"):
            if target.exists():
                files += sum(1 for p in target.rglob("*") if p.is_file())
                shutil.rmtree(target)
        self.log.info("audit: memory reset: %d files removed (vault and index)", files)
        sys_log.trace(self.component, "vault.reset_memory", {"files": files})
        return files
