# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""U2: the migration to the per-user layout, its rollback, the purge of a user (a fake installation in tmp)."""
import gzip
import json
from pathlib import Path

import pytest

from aurora import sys_users_layout as L
from aurora.sys_devices import Devices
from aurora.sys_users import Users


def tree(cfg) -> dict:
    """Every file of every personal area and the shared ones, with its bytes."""
    out = {}
    for key in ("AURORA_VAULT_DIR", "AURORA_UPLOADS_DIR", "AURORA_DOCUMENTS_DIR", "AURORA_STATUS_DIR"):
        base = cfg.path(key)
        for f in sorted(base.rglob("*")) if base.exists() else []:
            if f.is_file() and "users.db" not in f.name and "devices" not in f.name:
                out[str(f.relative_to(cfg.root))] = f.read_bytes()
    return out


def today_layout(cfg):
    mem = cfg.path("AURORA_VAULT_DIR") / "memory" / "conversation"
    mem.mkdir(parents=True)
    (mem / "0001.db").write_bytes(b"turns")
    (cfg.path("AURORA_VAULT_DIR") / "memory" / "registry.db").write_bytes(b"reg")
    know = cfg.path("AURORA_VAULT_DIR") / "knowledge" / "physics"
    know.mkdir(parents=True)
    (know / "0001.db").write_bytes(b"shared knowledge")
    up = cfg.path("AURORA_UPLOADS_DIR") / "2026-10"
    up.mkdir(parents=True)
    (up / "a-photo.png").write_bytes(b"png")
    cfg.path("AURORA_DOCUMENTS_DIR").mkdir(parents=True, exist_ok=True)
    (cfg.path("AURORA_DOCUMENTS_DIR") / "report.pdf").write_bytes(b"pdf")
    (cfg.path("AURORA_DOCUMENTS_DIR") / "papers").mkdir()
    (cfg.path("AURORA_DOCUMENTS_DIR") / "papers" / "arxiv-1.pdf").write_bytes(b"the library")      # shared
    st = cfg.path("AURORA_STATUS_DIR")
    (st / "push").mkdir(parents=True, exist_ok=True)
    (st / "routines.json").write_text("[]")
    (st / "push" / "subscriptions.json").write_text("[]")
    (st / "plugins.json").write_text("{}")                     # shared: never moves


def test_migrate_then_rollback_gives_back_the_same_files(cfg):
    today_layout(cfg)
    before = tree(cfg)
    plan = L.migration_plan(cfg, "admin1")
    assert {s["area"] for s in plan} == {"memory", "uploads", "documents", "state"}
    assert not any("knowledge" in s["from"] or "plugins.json" in s["from"] or "papers" in s["from"] for s in plan)
    L.migrate(cfg, "admin1")
    assert (cfg.path("AURORA_VAULT_DIR") / "memory" / "users" / "admin1" / "conversation" / "0001.db").read_bytes() == b"turns"
    assert (cfg.path("AURORA_STATUS_DIR") / "users" / "admin1" / "push" / "subscriptions.json").exists()
    assert (cfg.path("AURORA_STATUS_DIR") / "plugins.json").exists()
    assert (cfg.path("AURORA_VAULT_DIR") / "knowledge" / "physics" / "0001.db").exists()
    assert L.migrate(cfg, "admin1") == {"moved": 0, "files": {}}      # a second run moves nothing
    L.rollback(cfg, "admin1")
    assert tree(cfg) == before                                  # byte for byte, and no users/ folder left
    assert not any(p.name == "users" for p in cfg.root.rglob("users") if p.is_dir())


def test_purge_leaves_nothing_of_the_user(cfg):
    today_layout(cfg)
    users = Users(cfg)
    admin = users.add("owner", "admin", "a long password")["id"]
    guest = users.add("guest", "user")["id"]
    L.migrate(cfg, admin)
    for a in L.AREAS[:3]:
        h = L.home(cfg, a, guest)
        h.mkdir(parents=True)
        (h / "mine.txt").write_text("guest data")
    trace = cfg.path("AURORA_LOG_DIR") / "trace"
    trace.mkdir(parents=True, exist_ok=True)
    (trace / "api.jsonl").write_text(json.dumps({"event": "a", "user": guest}) + "\n" + json.dumps({"event": "b", "user": admin}) + "\n")
    with gzip.open(trace / "api.1.jsonl.gz", "wt") as f:
        f.write(json.dumps({"event": "c", "user": guest}) + "\n")
    devices = Devices(cfg)
    _, dev = devices.register("guest phone", "ua")
    items = json.loads(devices.file.read_text())
    items[0]["user"] = guest
    devices.file.write_text(json.dumps(items))
    plan = L.purge_plan(cfg, guest)
    assert {s["what"] for s in plan} == {"memory", "memory_index", "uploads", "trace"}
    out = L.purge(cfg, guest, admin)
    assert out["devices"] == 1 and users.get(guest) is None
    assert L.purge_plan(cfg, guest) == []
    assert (trace / "api.jsonl").read_text().count(admin) == 1 and guest not in (trace / "api.jsonl").read_text()
    assert L.home(cfg, L.AREAS[0], admin).exists()              # the admin's data untouched
    with pytest.raises(ValueError):
        L.purge(cfg, admin, admin)


def test_bad_ids_never_reach_the_file_system(cfg):
    for bad in ("", "../x", "a/b", "."):
        with pytest.raises(ValueError):
            L.home(cfg, L.AREAS[0], bad)
