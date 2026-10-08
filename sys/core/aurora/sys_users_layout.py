# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Where every personal datum of a user lives, and the three operations on it (docs/MULTIUSER.md, U2).

The owner's layout (2026-10-03): each user has a folder `usr/<name>/` with the same tree as today's `usr/` (uploads,
documents, projects, notes, images, expenses...), so a path only changes by the user's name; Aurora's own personal
data under `sys/` (the memory and its index, the routines, approvals and notifications) goes under
`<area>/users/<name>/`. Single-user is the same layout with the admin alone, so switching modes moves nothing:
  - migrate:  once, today's tree goes under the admin (`usr/*` → `usr/<admin>/*`); `rollback` puts it back while no
              other user has data (the way out if the upgrade must be undone);
  - purge:    a user and all that is theirs, their lines in the traces, their devices, their record; multi → single is
              the purge of every user but the admin.
Each operation first returns its plan (what moves or goes, with sizes) and, done, checks itself.
The owner's `usr/documents/papers` (his documents and patents) is never moved or deleted: the migration leaves it,
the rollback and the purge stop if they find it in a user's folder (C112). Shared data (the knowledge vault and its
index, models, plugins, settings) is never touched. Run with the services stopped, after a backup
(script/sys_users_migrate.py).
"""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import sys_config

USERS = "users"
STATE = "users_layout.json"         # in AURORA_STATUS_DIR (shared): {"layout": 1, "admin": name} once migrated
UNTOUCHED = ("documents/papers",)   # inside usr/ (and inside usr/<name>/): never moved, never deleted
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")


@dataclass(frozen=True)
class Area:
    """A personal area under sys/: its user folders are `<root>/users/<name>/`."""
    name: str
    setting: str
    sub: str = ""
    files: tuple[str, ...] = ()     # only these entries move (the status folder holds shared files too)


SYS_AREAS = (
    Area("memory", "AURORA_VAULT_DIR", "memory"),
    Area("memory_index", "AURORA_INDEX_DIR", "memory"),
    Area("state", "AURORA_STATUS_DIR", "", ("routines.json", "approvals.json", "react.json", "plugins_ready.json",
                                            "push/subscriptions.json", "push/prefs.json")),
)
BY_NAME = {a.name: a for a in SYS_AREAS}
# the folders of usr/ the modules know by their setting; place() turns usr/x into usr/<name>/x
USR_SETTINGS = {"uploads": "AURORA_UPLOADS_DIR", "documents": "AURORA_DOCUMENTS_DIR", "projects": "AURORA_PROJECTS_DIR",
                "notes": "AURORA_NOTES_DIR", "pictures": "AURORA_IMAGE_DIR", "expenses": "AURORA_EXPENSES_DIR",
                "bugreports": "AURORA_BUGREPORT_DIR", "music": "AURORA_MUSIC_DIR",
                "health": "AURORA_HEALTH_DIR", "calendar": "AURORA_CALENDAR_DIR"}


def usr(cfg: sys_config.Config) -> Path:
    return cfg.root / "usr"


def check_name(cfg: sys_config.Config, name: str) -> str:
    """A user's folder name: letters, digits, . _ - ; never a folder of today's usr/ tree (uploads, documents...)."""
    if not name or not NAME.fullmatch(name) or name.endswith("."):
        raise ValueError("bad user name")
    if any(Path(cfg.values.get(k) or "").name.lower() == name.lower() for k in USR_SETTINGS.values()) or name == USERS:
        raise ValueError(f"{name} is the name of a folder of usr/")
    return name


def migrated(cfg: sys_config.Config) -> dict | None:
    try:
        d = json.loads((cfg.path("AURORA_STATUS_DIR") / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if d.get("layout") == 1 else None


def root(cfg: sys_config.Config, area: Area) -> Path:
    p = cfg.path(area.setting)
    return p / area.sub if area.sub else p


def home(cfg: sys_config.Config, area: Area, name: str) -> Path:
    return root(cfg, area) / USERS / check_name(cfg, name)


def usr_home(cfg: sys_config.Config, name: str) -> Path:
    return usr(cfg) / check_name(cfg, name)


def make_home(cfg: sys_config.Config, name: str) -> Path:
    """A new user's usr/<name>/ with the same tree as everyone's (the folders the settings name), mode 700."""
    cfg = cfg.base or cfg
    home = usr_home(cfg, name)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    for key in USR_SETTINGS.values():
        p = cfg.path(key)
        if p == usr(cfg) or usr(cfg) in p.parents:
            (home / p.relative_to(usr(cfg))).mkdir(parents=True, exist_ok=True, mode=0o700)
    return home


def place(cfg: sys_config.Config, area: str, name: str | None) -> Path:
    """Where `area`'s data of user `name` is now: today's folder until the migration, the user's folder after it
    (no user given: the admin's). Every module asks here (U3)."""
    m = migrated(cfg)
    name = name or (m or {}).get("admin")
    cfg = cfg.base or cfg                                    # the machine's paths, never a user's view of them
    if area in USR_SETTINGS:
        p = cfg.path(USR_SETTINGS[area])
        if not (name and m):
            return p
        try:
            return usr_home(cfg, name) / p.relative_to(usr(cfg))
        except ValueError:                                   # a folder the owner put outside usr/
            return p / USERS / check_name(cfg, name)
    a = BY_NAME[area]
    return home(cfg, a, name) if name and m else root(cfg, a)


def _size(p: Path) -> int:
    return p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _count(p: Path) -> int:
    return 1 if p.is_file() else sum(1 for f in p.rglob("*") if f.is_file())


def _registered(cfg: sys_config.Config) -> set[str]:
    from .sys_users import Users
    return {u["name"] for u in Users(cfg).list()} if (cfg.path("AURORA_STATUS_DIR") / "users.db").exists() else set()


# ---- what moves ---------------------------------------------------------------------------------------------------
def _usr_entries(cfg: sys_config.Config, users: set[str]) -> list[Path]:
    """Today's usr/ tree, entry by entry, without the users' folders and without the untouchable papers: a folder
    holding them moves its other entries one by one (documents/* but papers)."""
    out = []

    def walk(d: Path, rel: str) -> None:
        for p in sorted(d.iterdir()):
            r = f"{rel}{p.name}"
            if not rel and p.name in users:
                continue
            if r in UNTOUCHED:
                continue
            if p.is_dir() and any(u.startswith(r + "/") for u in UNTOUCHED):
                walk(p, r + "/")
            else:
                out.append(p)
    if usr(cfg).is_dir():
        walk(usr(cfg), "")
    return out


def _sys_entries(cfg: sys_config.Config, area: Area) -> list[Path]:
    r = root(cfg, area)
    if area.files:
        return [r / f for f in area.files if (r / f).exists()]
    return sorted(p for p in r.iterdir() if p.name != USERS) if r.is_dir() else []


def _untouched_in(cfg: sys_config.Config, name: str) -> list[str]:
    return [str(usr_home(cfg, name) / u) for u in UNTOUCHED if (usr_home(cfg, name) / u).exists()]


# ---- migration (once, today's tree → the admin's folder) and its rollback ----------------------------------------
def migration_plan(cfg: sys_config.Config, admin: str) -> list[dict]:
    plan = []
    users = _registered(cfg) | {admin}
    for src in _usr_entries(cfg, users):
        plan.append({"area": "usr", "from": str(src), "to": str(usr_home(cfg, admin) / src.relative_to(usr(cfg))),
                     "files": _count(src), "bytes": _size(src)})
    for a in SYS_AREAS:
        for src in _sys_entries(cfg, a):
            plan.append({"area": a.name, "from": str(src), "to": str(home(cfg, a, admin) / src.relative_to(root(cfg, a))),
                         "files": _count(src), "bytes": _size(src)})
    return plan


def _mark(cfg: sys_config.Config, state: dict | None) -> None:
    f = cfg.path("AURORA_STATUS_DIR") / STATE
    if state is None:
        f.unlink(missing_ok=True)
    else:
        f.write_text(json.dumps(state), encoding="utf-8")


def migrate(cfg: sys_config.Config, admin: str) -> dict:
    plan = migration_plan(cfg, admin)
    state = {"layout": 1, "admin": admin, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if not plan:                                                # done already, or nothing to move: nothing happens
        if not migrated(cfg):                                   # a new installation: its personal settings still go
            from . import sys_user_config                      # to the admin's own .env (C210)
            settings = sys_user_config.split(cfg, admin)
            _mark(cfg, state)
            return {"moved": 0, "files": 0, "settings": settings}
        return {"moved": 0, "files": 0}
    for step in plan:
        if Path(step["to"]).exists():
            raise FileExistsError(f"{step['to']} exists")
    files = sum(s["files"] for s in plan)
    for step in plan:
        Path(step["to"]).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.replace(step["from"], step["to"])                    # same file system: a rename, nothing copied
    moved = sum(_count(Path(s["to"])) for s in plan)
    if moved != files or any(Path(s["from"]).exists() for s in plan):
        raise RuntimeError(f"migration check failed: {files} files planned, {moved} found")
    from . import sys_user_config                              # the personal settings into the admin's own .env
    settings = sys_user_config.split(cfg, admin)
    _mark(cfg, state)
    return {"moved": len(plan), "files": files, "settings": settings}


def _prune(path: Path, stop: Path) -> None:
    """Remove empty folders from `path` up to (not including) `stop`."""
    while path != stop and stop in path.parents and path.is_dir() and not any(path.iterdir()):
        path.rmdir()
        path = path.parent


def rollback(cfg: sys_config.Config, admin: str) -> dict:
    """Back to today's tree: only while the admin is the only user with data, and without the owner's papers inside."""
    kept = _untouched_in(cfg, admin)
    if kept:                                                    # it would move them and delete the folder
        raise RuntimeError(f"the owner's papers are in the admin's folder ({kept[0]}): move them back yourself first")
    others = [n for n in _registered(cfg) - {admin}
              if usr_home(cfg, n).exists() or any(home(cfg, a, n).exists() for a in SYS_AREAS)]
    if others:
        raise RuntimeError(f"other users have data ({', '.join(sorted(others))}): purge them first")
    from . import sys_user_config                              # first: the admin's .env must not land in usr/
    sys_user_config.merge(cfg, admin)
    moved = 0
    pairs = [(usr_home(cfg, admin), usr(cfg), None)] + [(home(cfg, a, admin), root(cfg, a), a) for a in SYS_AREAS]
    for h, base, area in pairs:
        if not h.exists():
            continue
        items = ([h / f for f in area.files if (h / f).exists()] if area and area.files else
                 [p for p in h.rglob("*") if p.is_file() or (p.is_dir() and not any(p.iterdir()))])
        for src in items:
            dst = base / src.relative_to(h)
            if dst.exists() and not dst.is_dir():
                raise FileExistsError(f"{dst} exists")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                dst.mkdir(exist_ok=True)
                src.rmdir()
            else:
                os.replace(src, dst)
            moved += 1
        for d in sorted((p for p in h.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            _prune(d, h.parent)
        _prune(h, base if area is None else base)
        if area is not None:
            _prune(base / USERS, base)
    _mark(cfg, None)
    return {"moved": moved}


# ---- purge of a user ----------------------------------------------------------------------------------------------
def _trace_files(cfg: sys_config.Config) -> list[Path]:
    d = cfg.path("AURORA_LOG_DIR") / "trace"
    return sorted(d.glob("*.jsonl")) + sorted(d.glob("*.jsonl.gz")) if d.is_dir() else []


def _user_lines(path: Path, name: str) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        return sum(1 for line in f if f'"user": "{name}"' in line or f'"user":"{name}"' in line)


def purge_plan(cfg: sys_config.Config, name: str) -> list[dict]:
    folders = [("usr", usr_home(cfg, name))] + [(a.name, home(cfg, a, name)) for a in SYS_AREAS]
    plan = [{"what": w, "path": str(p), "files": _count(p), "bytes": _size(p)} for w, p in folders if p.exists()]
    plan += [{"what": "trace", "path": str(f), "lines": n} for f in _trace_files(cfg) if (n := _user_lines(f, name))]
    return plan


def _strip_trace(path: Path, name: str) -> None:
    opener = gzip.open if path.suffix == ".gz" else open
    tmp = path.with_name(path.name + ".purge")
    with opener(path, "rt", encoding="utf-8", errors="replace") as src, opener(tmp, "wt", encoding="utf-8") as dst:
        for line in src:
            try:
                if json.loads(line).get("user") == name:
                    continue
            except ValueError:
                pass
            dst.write(line)
    os.replace(tmp, path)


def purge(cfg: sys_config.Config, name: str, admin: str) -> dict:
    """Everything of a user, then the check. The admin cannot be purged; the owner's papers are never deleted."""
    if name == admin:
        raise ValueError("the admin cannot be purged")
    kept = _untouched_in(cfg, name)
    if kept:
        raise RuntimeError(f"papers in this user's folder ({kept[0]}): never deleted by Aurora, move them first")
    plan = purge_plan(cfg, name)
    for step in plan:
        if step["what"] == "trace":
            _strip_trace(Path(step["path"]), name)
        else:
            shutil.rmtree(step["path"])
    for a in SYS_AREAS:
        _prune(root(cfg, a) / USERS, root(cfg, a))
    from .sys_devices import Devices
    from .sys_users import Users
    devices = Devices(cfg)
    gone = [d["id"] for d in devices.list() if d.get("user") == name]
    for d in gone:                                           # their browsers are logged out at once
        devices.revoke(d)
    users = Users(cfg)
    rec = next((u for u in users.list() if u["name"] == name), None)
    if rec:
        users.remove(rec["id"])
    left = purge_plan(cfg, name) + [d for d in devices.list() if d.get("user") == name]
    if left or any(u["name"] == name for u in users.list()):
        raise RuntimeError(f"purge check failed: {left}")
    return {"removed": plan, "devices": len(gone)}
