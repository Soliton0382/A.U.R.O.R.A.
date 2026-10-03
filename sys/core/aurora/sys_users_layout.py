# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Where every personal datum of a user lives, and the three operations on it (docs/MULTIUSER.md, U2).

One layout for both modes: in each personal AREA the data of a user is under `<area>/users/<uid>/`; single-user is
the same layout with the admin alone. So switching modes moves nothing:
  - migrate:  once, today's data (the area's root) goes under the admin; `rollback` puts it back while nobody else
              has data (the way out if the upgrade must be undone);
  - purge:    a user and all that is theirs, in every area, their lines in the traces, their devices; multi → single
              is the purge of every user but the admin.
Each operation first returns its plan (what moves or goes, with sizes) and, done, checks itself: a purge leaves 0
files and 0 trace lines with the user's id. Shared data (the knowledge vault and its index, models, plugins,
settings) is never touched. Run with the services stopped and after a backup (script/sys_users_migrate.py).
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import sys_config

USERS = "users"


@dataclass(frozen=True)
class Area:
    name: str
    setting: str                    # the folder setting
    sub: str = ""                   # a part of that folder ("memory" of the vault)
    files: tuple[str, ...] = ()     # only these entries move (the status folder holds shared files too)
    shared: tuple[str, ...] = ()    # entries that stay for everyone (the papers of the library: 25 GB, not personal)


AREAS = (
    Area("memory", "AURORA_VAULT_DIR", "memory"),
    Area("memory_index", "AURORA_INDEX_DIR", "memory"),
    Area("uploads", "AURORA_UPLOADS_DIR"),
    Area("documents", "AURORA_DOCUMENTS_DIR", shared=("papers",)),
    Area("projects", "AURORA_PROJECTS_DIR"),
    Area("notes", "AURORA_NOTES_DIR"),
    Area("pictures", "AURORA_IMAGE_DIR"),
    Area("expenses", "AURORA_EXPENSES_DIR"),
    Area("state", "AURORA_STATUS_DIR", "", ("routines.json", "approvals.json", "react.json", "push/subscriptions.json",
                                            "push/prefs.json")),
)


def root(cfg: sys_config.Config, area: Area) -> Path:
    p = cfg.path(area.setting)
    return p / area.sub if area.sub else p


def home(cfg: sys_config.Config, area: Area, uid: str) -> Path:
    if not uid or not uid.isalnum():
        raise ValueError("bad user id")
    return root(cfg, area) / USERS / uid


def _entries(cfg: sys_config.Config, area: Area) -> list[Path]:
    """What belongs to the single owner of today's layout in an area (its root, minus users/)."""
    r = root(cfg, area)
    if area.files:
        return [r / f for f in area.files if (r / f).exists()]
    return sorted(p for p in r.iterdir() if p.name != USERS and p.name not in area.shared) if r.is_dir() else []


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _count(p: Path) -> int:
    return 1 if p.is_file() else sum(1 for f in p.rglob("*") if f.is_file())


# ---- migration (once, today's layout → the admin's folder) and its rollback -------------------------------------
def migration_plan(cfg: sys_config.Config, admin: str) -> list[dict]:
    plan = []
    for a in AREAS:
        for src in _entries(cfg, a):
            dst = home(cfg, a, admin) / src.relative_to(root(cfg, a))
            plan.append({"area": a.name, "from": str(src), "to": str(dst), "files": _count(src), "bytes": _size(src)})
    return plan


def migrate(cfg: sys_config.Config, admin: str) -> dict:
    plan = migration_plan(cfg, admin)
    if not plan:                                                # done already, or nothing to move: nothing happens
        return {"moved": 0, "files": {}}
    before = {a.name: sum(_count(p) for p in _entries(cfg, a)) + (_count(home(cfg, a, admin)) if home(cfg, a, admin).exists()
                                                                 else 0) for a in AREAS}
    for step in plan:
        if Path(step["to"]).exists():
            raise FileExistsError(f"{step['to']} exists: the migration ran already")
    for step in plan:
        Path(step["to"]).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.replace(step["from"], step["to"])                    # same file system: a rename, nothing copied
    after = {a.name: _count(home(cfg, a, admin)) if home(cfg, a, admin).exists() else 0 for a in AREAS}
    if before != after:
        raise RuntimeError(f"migration check failed: before {before}, after {after}")
    return {"moved": len(plan), "files": before}


def rollback(cfg: sys_config.Config, admin: str) -> dict:
    """Back to today's layout: only while the admin is the only user with data."""
    others = [p for a in AREAS if (root(cfg, a) / USERS).is_dir() for p in (root(cfg, a) / USERS).iterdir() if p.name != admin]
    if others:
        raise RuntimeError(f"other users have data ({len(others)} folders): purge them first")
    moved = 0
    for a in AREAS:
        h = home(cfg, a, admin)
        if not h.exists():
            continue
        items = [h / f for f in a.files if (h / f).exists()] if a.files else list(h.iterdir())
        for src in items:
            dst = root(cfg, a) / src.relative_to(h)
            if dst.exists():
                raise FileExistsError(f"{dst} exists")
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            moved += 1
        shutil.rmtree(h)
        users = root(cfg, a) / USERS
        while users.is_dir() and not any(users.iterdir()):
            users.rmdir()
    return {"moved": moved}


# ---- purge of a user ----------------------------------------------------------------------------------------------
def _trace_files(cfg: sys_config.Config) -> list[Path]:
    d = cfg.path("AURORA_LOG_DIR") / "trace"
    return sorted(d.glob("*.jsonl")) + sorted(d.glob("*.jsonl.gz")) if d.is_dir() else []


def _user_lines(path: Path, uid: str) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    n = 0
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if f'"user": "{uid}"' in line or f'"user":"{uid}"' in line:
                n += 1
    return n


def purge_plan(cfg: sys_config.Config, uid: str) -> list[dict]:
    plan = [{"what": a.name, "path": str(home(cfg, a, uid)), "files": _count(home(cfg, a, uid)),
             "bytes": _size(home(cfg, a, uid))} for a in AREAS if home(cfg, a, uid).exists()]
    plan += [{"what": "trace", "path": str(f), "lines": n} for f in _trace_files(cfg) if (n := _user_lines(f, uid))]
    return plan


def _strip_trace(path: Path, uid: str) -> None:
    opener = gzip.open if path.suffix == ".gz" else open
    tmp = path.with_name(path.name + ".purge")
    with opener(path, "rt", encoding="utf-8", errors="replace") as src, opener(tmp, "wt", encoding="utf-8") as dst:
        for line in src:
            try:
                if json.loads(line).get("user") == uid:
                    continue
            except ValueError:
                pass
            dst.write(line)
    os.replace(tmp, path)


def purge(cfg: sys_config.Config, uid: str, admin: str) -> dict:
    """Everything of a user, then the check. The admin cannot be purged."""
    if uid == admin:
        raise ValueError("the admin cannot be purged")
    plan = purge_plan(cfg, uid)
    for step in plan:
        if step["what"] == "trace":
            _strip_trace(Path(step["path"]), uid)
        else:
            shutil.rmtree(step["path"])
    from .sys_devices import Devices
    from .sys_users import Users
    devices = Devices(cfg)
    gone = [d["id"] for d in devices.list() if d.get("user") == uid]
    for d in gone:                                           # their browsers are logged out at once
        devices.revoke(d)
    Users(cfg).remove(uid)
    left = purge_plan(cfg, uid) + [d for d in devices.list() if d.get("user") == uid]
    if left or Users(cfg).get(uid):
        raise RuntimeError(f"purge check failed: {left}")
    return {"removed": plan, "devices": len(gone)}
