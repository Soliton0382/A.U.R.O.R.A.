# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The shadow of a plugin's work (owner, 2026-10-05: "the same operation with the same results: the ready meal instead
of doing it again"). Each plugin has its own small cache, so plugins never get in each other's way.

Only what a plugin declares in its manifest, "cache": {"tool": seconds, "*": seconds}, and only for tools whose
effect is "read": nothing that writes, sends or publishes is ever served from here. The key is the tool and its
arguments exactly (an operation is either the same or not: no nearness here, unlike kno_shadow), per user (a token of
one user is not another's). A result is served while younger than its seconds; errors are never kept.
Each plugin's cache: <user state>/plugin_shadow/<plugin>.db, at most MAX_ROWS results; each result sealed with the
user's key, bound to its plugin and key (N64: a tool's results can quote a chat). The key is keyed too: an HMAC of
the tool and its arguments with the user's key, so a guessed argument cannot be confirmed from the file (until
29 Oct a plain hash, in the table «results»: dropped at the first open, it was only a cache).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
import time
from contextlib import closing

from . import sys_config, sys_seal

MAX_ROWS = 500
_lock = threading.Lock()


def ttl(manifest: dict, tool: str, effect: str) -> int:
    """Seconds a result of this tool may be served again; 0 = never."""
    if effect != "read":
        return 0
    c = manifest.get("cache") or {}
    return int(c.get(tool, c.get("*", 0)) or 0)


def _db(cfg: sys_config.Config, plugin: str) -> sqlite3.Connection:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user) / "plugin_shadow"
    d.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(d / f"{plugin}.db", timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS shadow (key TEXT PRIMARY KEY, tool TEXT, text TEXT, at REAL, used INTEGER DEFAULT 0)")
    if con.execute("SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'results'").fetchone():
        con.execute("DROP TABLE results")                # the plain-hash keys of before: gone with their pages
        con.commit()
        con.execute("VACUUM")
    return con


def key(cfg: sys_config.Config, tool: str, args: dict) -> str:
    secret = hashlib.sha256(sys_seal._key(cfg, cfg.user, "state") + b"plugin-shadow").digest()
    return hmac.new(secret, json.dumps([tool, args], sort_keys=True, ensure_ascii=False, default=str).encode(),
                    hashlib.sha256).hexdigest()


def get(cfg: sys_config.Config, plugin: str, tool: str, args: dict, seconds: int) -> str | None:
    if seconds <= 0:
        return None
    k = key(cfg, tool, args)
    with _lock, closing(_db(cfg, plugin)) as con, con:
        row = con.execute("SELECT text, at FROM shadow WHERE key = ?", (k,)).fetchone()
        if row is None or time.time() - row[1] > seconds:
            return None
        con.execute("UPDATE shadow SET used = used + 1 WHERE key = ?", (k,))
    try:
        return sys_seal.open_text(cfg, row[0], f"{plugin}:{k}", cfg.user)
    except ValueError:                                 # not this user's, or changed: done again
        return None


def put(cfg: sys_config.Config, plugin: str, tool: str, args: dict, text: str) -> None:
    k = key(cfg, tool, args)
    sealed = sys_seal.seal_text(cfg, text, f"{plugin}:{k}", cfg.user)
    with _lock, closing(_db(cfg, plugin)) as con, con:
        con.execute("INSERT OR REPLACE INTO shadow (key, tool, text, at) VALUES (?, ?, ?, ?)",
                    (k, tool, sealed, time.time()))
        n = con.execute("SELECT count(*) FROM shadow").fetchone()[0]
        if n > MAX_ROWS:                               # the oldest go first
            con.execute("DELETE FROM shadow WHERE key IN (SELECT key FROM shadow ORDER BY at LIMIT ?)", (n - MAX_ROWS,))


def stats(cfg: sys_config.Config) -> dict:
    """Per plugin: results kept and times served from the cache."""
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user) / "plugin_shadow"
    out = {}
    for f in sorted(d.glob("*.db")) if d.exists() else []:
        with closing(_db(cfg, f.stem)) as con:
            n, used = con.execute("SELECT count(*), coalesce(sum(used), 0) FROM shadow").fetchone()
        out[f.stem] = {"results": n, "served": used}
    return out
