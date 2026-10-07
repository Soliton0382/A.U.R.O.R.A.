# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Deleting a plugin, and taking it back (owner, 2026-10-08: «non va bene che non posso eliminare dei plugin, mettiamo
subito l'opzione di eliminazione» — after a wrong click on an approval the same night).

delete() moves the plugin's folder out of AURORA_PLUGINS_DIR into <STATUS>/plugins/trash/<name>-<time>: the plugin
is gone for Aurora (no tools, no routines, no page) and comes back whole with restore(). Its settings stay in the
.env (a restored plugin finds them). Never deleted: the plugins Aurora needs to repair herself (KEEP).
The admin's alone (api/agents).
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from . import sys_config, sys_log

KEEP = {"self"}                                       # her repairs go through it: deleting it would leave her unable to fix


class TrashError(Exception):
    pass


def _trash(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "plugins" / "trash"


def delete(cfg: sys_config.Config, name: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", name):
        raise TrashError("nome di plugin non valido")
    if name in KEEP:
        raise TrashError(f"«{name}» non si elimina: Aurora lo usa per ripararsi")
    src = cfg.path("AURORA_PLUGINS_DIR") / name
    if not (src / "plugin.json").is_file():
        raise TrashError(f"nessun plugin «{name}»")
    dest = _trash(cfg) / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    (dest / ".deleted.json").write_text(json.dumps({"name": name, "at": time.time()}), encoding="utf-8")
    sys_log.get_logger("plugins").info("audit: plugin %s deleted (in the trash: %s)", name, dest.name)
    return {"name": name, "trash": dest.name}


def trashed(cfg: sys_config.Config) -> list[dict]:
    out = []
    d = _trash(cfg)
    for f in sorted(d.glob("*/.deleted.json"), reverse=True) if d.is_dir() else []:
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        out.append({"id": f.parent.name, "name": info.get("name", ""), "at": info.get("at")})
    return out


def restore(cfg: sys_config.Config, item: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}-\d{8}-\d{6}", item):
        raise TrashError("elemento del cestino non valido")
    src = _trash(cfg) / item
    try:
        name = json.loads((src / ".deleted.json").read_text(encoding="utf-8"))["name"]
    except (OSError, ValueError, KeyError):
        raise TrashError(f"nel cestino non c'è «{item}»") from None
    dest = cfg.path("AURORA_PLUGINS_DIR") / name
    if dest.exists():
        raise TrashError(f"esiste già un plugin «{name}»: eliminalo prima, o rinominalo")
    (src / ".deleted.json").unlink()
    shutil.move(str(src), str(dest))
    sys_log.get_logger("plugins").info("audit: plugin %s restored from the trash", name)
    return {"name": name}
