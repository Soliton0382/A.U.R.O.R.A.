# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The trash (owner, 2026-10-04): a file deleted from the Files page goes to the user's trash, and is removed for good
after AURORA_TRASH_DAYS; with AURORA_TRASH_ENABLED off it is removed at once.

Each user's trash is usr/<name>/trash (before the per-user layout: <AURORA_STATUS_DIR>/trash): private, in the
backup, gone with the user. Every item is a folder <id>/ holding the file and meta.json (name, where it came from,
when). Emptied by the daily purge of aurora-rem (POST /v1/aurora/uploads/purge) and from the Files page.
"""
from __future__ import annotations

import json
import secrets
import shutil
import time
from pathlib import Path

from . import sys_config, sys_users_layout as L

DAY = 86400


def folder(cfg: sys_config.Config, user: str | None = None) -> Path:
    base = cfg.base or cfg
    m = L.migrated(base)
    name = user or getattr(cfg, "user", None) or (m or {}).get("admin")
    return L.usr_home(base, name) / "trash" if m and name else base.path("AURORA_STATUS_DIR") / "trash"


def discard(cfg: sys_config.Config, path: Path, kind: str, name: str | None = None, record: dict | None = None) -> str | None:
    """Move `path` to the trash (or remove it, trash off); returns the trash id, None when removed at once.
    `record`: what its owner module needs to take it back (an upload's index line)."""
    if not cfg["AURORA_TRASH_ENABLED"]:
        path.unlink(missing_ok=True)
        return None
    tid = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    d = folder(cfg) / tid
    d.mkdir(parents=True, mode=0o700)
    shutil.move(str(path), d / path.name)
    (d / "meta.json").write_text(json.dumps({"name": name or path.name, "file": path.name, "kind": kind,
                                             "from": str(path), "at": time.time(), "record": record}),
                                 encoding="utf-8")
    return tid


def items(cfg: sys_config.Config) -> list[dict]:
    out = []
    root = folder(cfg)
    for d in sorted(root.iterdir(), reverse=True) if root.is_dir() else []:
        try:
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        f = d / m["file"]
        out.append({"id": d.name, "name": m["name"], "kind": m["kind"], "at": m["at"],
                    "bytes": f.stat().st_size if f.is_file() else 0,
                    "expires": m["at"] + int(cfg["AURORA_TRASH_DAYS"]) * DAY})
    return out


def _item(cfg: sys_config.Config, tid: str) -> Path | None:
    d = folder(cfg) / tid
    return d if tid and "/" not in tid and not tid.startswith(".") and (d / "meta.json").is_file() else None


def restore(cfg: sys_config.Config, tid: str) -> tuple[Path, dict] | None:
    """The file back where it was (a name already taken there gets a suffix), with its meta; None for an unknown id."""
    d = _item(cfg, tid)
    if d is None:
        return None
    m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    to = Path(m["from"])
    n = 1
    while to.exists():
        to = to.with_name(f"{Path(m['from']).stem}-{n}{to.suffix}")
        n += 1
    to.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(d / m["file"]), to)
    shutil.rmtree(d)
    return to, m


def remove(cfg: sys_config.Config, tid: str) -> bool:
    d = _item(cfg, tid)
    if d is None:
        return False
    shutil.rmtree(d)
    return True


def expire(cfg: sys_config.Config, now: float | None = None) -> int:
    """Remove what is older than AURORA_TRASH_DAYS from every user's trash; returns how many."""
    base = cfg.base or cfg
    now = now or time.time()
    keep = int(base["AURORA_TRASH_DAYS"]) * DAY
    roots = [base.path("AURORA_STATUS_DIR") / "trash"]
    if L.migrated(base) and L.usr(base).is_dir():
        roots += [h / "trash" for h in L.usr(base).iterdir() if h.is_dir()]
    gone = 0
    for root in roots:
        for d in root.iterdir() if root.is_dir() else []:
            try:
                at = json.loads((d / "meta.json").read_text(encoding="utf-8"))["at"]
            except (OSError, ValueError, KeyError):
                continue
            if now - at >= keep:
                shutil.rmtree(d)
                gone += 1
    return gone
