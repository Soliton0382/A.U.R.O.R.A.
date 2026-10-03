# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Reads solitons from the vault.

- by sid (one or many; many are grouped by shard, one query per shard);
- by domain, in storage order from a given position: this is how the index
  reads what it has not indexed yet;
- the most recent memory turns by time: the window that keeps short follow-ups
  in context (AURORA_MEMORY_RECENT_TURNS).

Connections are read-only and kept per thread and per file. A thread made for one job calls `release()` when it
ends: the connections of a finished thread sit in reference cycles until the garbage collector passes, and the API
reached its 1024 open files after a few dozen questions (C103).
"""
from __future__ import annotations

import sqlite3
import threading
import weakref
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator

from . import sol_vault, sys_config
from .sol_schema import Soliton

_readers: "weakref.WeakSet[VaultReader]" = weakref.WeakSet()


def release() -> None:
    """Close this thread's connections of every reader (end of a job thread)."""
    for r in list(_readers):
        r.close()


_SELECT = f"SELECT rowid, {', '.join(sol_vault.COLUMNS)} FROM solitons"


class VaultReader:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.layout = sol_vault.Layout.from_config(self.cfg)
        self._local = threading.local()
        _readers.add(self)

    def _con(self, path: Path) -> sqlite3.Connection | None:
        cache = self._local.__dict__.setdefault("cons", {})
        if path not in cache:
            if not path.exists():
                return None
            cache[path] = sol_vault.connect(path, readonly=True)
        return cache[path]

    def close(self) -> None:
        for con in getattr(self._local, "cons", {}).values():
            con.close()
        self._local.cons = {}

    # ---- by sid ------------------------------------------------------------------
    def locate(self, sids: Iterable[str]) -> dict[str, tuple[str, str, int]]:
        """sid -> (section, shard key, row) for the sids present in the vault."""
        wanted = list(dict.fromkeys(sids))
        found = {}
        for section in sol_vault.SECTIONS:
            reg = self._con(self.layout.registry(section))
            if reg is None:
                continue
            rest = [s for s in wanted if s not in found]
            for i in range(0, len(rest), 500):
                part = rest[i:i + 500]
                q = f"SELECT sid, shard, row FROM registry WHERE sid IN ({','.join('?' * len(part))})"
                for r in reg.execute(q, part):
                    found[r["sid"]] = (section, r["shard"], r["row"])
        return found

    def get_many(self, sids: Iterable[str]) -> dict[str, Soliton]:
        by_shard: dict[tuple[str, str], list[int]] = defaultdict(list)
        for sid, (section, key, row) in self.locate(sids).items():
            by_shard[(section, key)].append(row)
        out = {}
        for (section, key), rows in by_shard.items():
            con = self._con(self.layout.shard_path(section, key))
            if con is None:
                continue
            for i in range(0, len(rows), 500):
                part = rows[i:i + 500]
                for r in con.execute(f"{_SELECT} WHERE rowid IN ({','.join('?' * len(part))})", part):
                    out[r["sid"]] = Soliton.from_row(dict(r))
        return out

    def get(self, sid: str) -> Soliton | None:
        return self.get_many([sid]).get(sid)

    # ---- by domain ---------------------------------------------------------------
    def iter_domain(self, domain: str, after: tuple[str, int] | None = None,
                    batch: int = 1000) -> Iterator[tuple[str, int, Soliton]]:
        """(shard key, row, soliton) in storage order, strictly after the (shard key, row) position."""
        section = self.layout.section_of(domain)
        for shard in self.layout.shards(section, domain):
            key = self.layout.shard_key(shard)
            if after and key < after[0]:
                continue
            last = after[1] if after and key == after[0] else 0
            con = self._con(shard)
            while True:
                rows = con.execute(f"{_SELECT} WHERE rowid > ? ORDER BY rowid LIMIT ?", (last, batch)).fetchall()
                if not rows:
                    break
                for r in rows:
                    yield key, r["rowid"], Soliton.from_row(dict(r))
                last = rows[-1]["rowid"]

    def count(self, domain: str | None = None) -> dict[str, int]:
        out = {}
        for section in sol_vault.SECTIONS:
            for d in self.layout.domains(section):
                if domain and d != domain:
                    continue
                out[d] = sum(self._con(s).execute("SELECT count(*) FROM solitons").fetchone()[0]
                             for s in self.layout.shards(section, d))
        return out

    # ---- by source ---------------------------------------------------------------
    def by_source(self, domain: str, source_id: str, limit: int = 120) -> list[Soliton]:
        """The passages of one source (a paper, a law), in their order: the sources in focus of a follow-up."""
        if domain not in self.layout.taxonomy:
            return []
        out: list[Soliton] = []
        for shard in self.layout.shards(self.layout.section_of(domain), domain):
            con = self._con(shard)
            out += [Soliton.from_row(dict(r)) for r in con.execute(
                f"{_SELECT} WHERE source_id = ? ORDER BY chunk_index LIMIT ?", (source_id, limit - len(out)))]
            if len(out) >= limit:
                break
        return out

    # ---- memory ------------------------------------------------------------------
    def recent(self, n: int, domain: str = "conversation") -> list[Soliton]:
        """The n most recent memory solitons of a domain, newest last."""
        if n <= 0:
            return []
        rows = []
        for shard in reversed(self.layout.shards("memory", domain)):   # newest shards first
            con = self._con(shard)
            rows += [dict(r) for r in con.execute(f"{_SELECT} ORDER BY created_at DESC LIMIT ?", (n,))]
            if len(rows) >= n:
                break
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [Soliton.from_row(r) for r in reversed(rows[:n])]
