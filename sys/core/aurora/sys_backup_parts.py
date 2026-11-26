# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A full backup, a selective restore (owner, 3 Nov: «uno magari non vuole ripristinare interamente il backup, ma partire
con aurora "vergine" e caricare solo la sua configurazione»). Every night copies everything; what goes back is asked.

Each file of a snapshot belongs to exactly one part, read from its path:
  config   the settings (.env, each user's), users and keys, routines, models, devices, certificates: Aurora's choices
  memory   each user's memory with its index, the shadow, the people, the lessons
  vault    the knowledge vault with its index
  files    usr/: documents, uploads, pictures, projects, notes
  plugins  the plugins Aurora built (the built-in ones stay the code's)
  history  what happened: incidents, usage, harvest, what a new start does without

A shard and its index go together, so the memory is one part: short and long term (consolidated or not) are rows of the
same shards under one registry, and no file can tell them apart. Status files not named here are config: a new setting
comes back rather than being lost.
"""
from __future__ import annotations

from pathlib import Path

from . import sys_config

PARTS = ("config", "memory", "vault", "files", "plugins", "history")
MEMORY_STATUS = {"people.sealed", "synapses.db", "deductions.db", "mood_samples.json", "train.json"}
MEMORY_USER = {"shadow.db"}
HISTORY_STATUS = {"autonomy_ledger.jsonl", "autopilot.json", "fresh_start.txt", "forge", "geo", "harvest", "incidents.json",
                  "incident_verdicts.json", "incidents_quiet.json", "linkcheck.json", "llm_previous.json", "migrate",
                  "preview", "realign", "rem_daily.txt", "soak.jsonl", "story", "traces_from_incidents.json", "update", "usage", "vault_audit.json",
                  "welcomed.json"}


_BASES: dict = {}


def _base(cfg: sys_config.Config, key: str) -> str:
    """_rel once per installation and folder (C755: resolved for each of a snapshot's 82,000 files, the parts of ten
    copies took about four minutes, 22.5 s each — the 💾 page stayed on «Leggo i backup…»)."""
    k = (id(cfg), key)                               # the object kept beside it: its id is never reused meanwhile
    hit = _BASES.get(k)
    if hit is None or hit[0] is not cfg:
        hit = _BASES[k] = (cfg, _rel(cfg, key))
    return hit[1]


def _rel(cfg: sys_config.Config, key: str) -> str:
    p, root = cfg.path(key).resolve(), cfg.root.resolve()
    return str(p.relative_to(root)) if root in p.parents else "\0"       # a folder outside the root: «external/…»


def _under(rel: str, base: str) -> bool:
    return rel == base or rel.startswith(base + "/")


def part_of(cfg: sys_config.Config, rel: str) -> str:
    """The part of a file of the snapshot, from its path relative to Aurora's root."""
    index, vault = _base(cfg, "AURORA_INDEX_DIR"), _base(cfg, "AURORA_VAULT_DIR")
    if rel.startswith("external/"):
        return "files"
    if _under(rel, f"{index}/memory") or _under(rel, f"{vault}/memory"):
        return "memory"
    if _under(rel, index) or _under(rel, vault):
        return "vault"
    if _under(rel, _base(cfg, "AURORA_PLUGINS_DIR")):
        return "plugins"
    status = _base(cfg, "AURORA_STATUS_DIR")
    if _under(rel, status):
        tail = rel[len(status) + 1:].split("/")
        if tail[0] in MEMORY_STATUS or tail[0].startswith("lessons") or (tail[0] == "users" and tail[-1] in MEMORY_USER):
            return "memory"
        return "history" if tail[0] in HISTORY_STATUS else "config"
    if rel.startswith("usr/"):
        return "config" if rel.rsplit("/", 1)[-1] == ".env" else "files"
    return "config"


def user_of(cfg: sys_config.Config, rel: str) -> str | None:
    """The user a file of the snapshot belongs to, or None for the machine's own (owner, 27 Nov: «una ulteriore
    tipologia di selezione a livello di utente… se serve ripristinare solo un utente e i suoi dati, è più veloce»):
    usr/<name>/…, <status>/users/<name>/…, the memory's <index|vault>/memory/users/<name>/…"""
    parts = Path(rel).parts
    if len(parts) > 2 and parts[0] == "usr":
        return parts[1]
    for key, sub in (("AURORA_STATUS_DIR", ("users",)), ("AURORA_INDEX_DIR", ("memory", "users")),
                     ("AURORA_VAULT_DIR", ("memory", "users"))):
        base = Path(_base(cfg, key)).parts + sub
        if len(parts) > len(base) + 1 and parts[:len(base)] == base:
            return parts[len(base)]
    return None


def sizes(cfg: sys_config.Config, files: list) -> dict[str, dict]:
    """{part: {"files", "bytes"}} of a snapshot's file list, every part named."""
    out = {p: {"files": 0, "bytes": 0} for p in PARTS}
    for f in files:
        s = out[part_of(cfg, f[0])]
        s["files"] += 1
        s["bytes"] += f[1]
    return out


def chosen(text: str) -> tuple[str, ...]:
    """«config,memory» as parts, in their order; an unknown name stops here, before anything is touched."""
    names = {x.strip() for x in str(text).split(",") if x.strip()}
    bad = names - set(PARTS)
    if bad or not names:
        raise ValueError(f"unknown parts: {', '.join(sorted(bad)) or '(none)'}; they are: {', '.join(PARTS)}")
    return tuple(p for p in PARTS if p in names)
