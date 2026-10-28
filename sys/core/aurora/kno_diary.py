# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Her diary for the diary plugin (N64): the dreams and thoughts the REM writes, copied into one file sealed with the
user's «diary» key — the plugin, caged, gets that key alone (plg_host.SEAL_KEYS), never the memory's, so it reads her
inner life that may be told and nothing of the conversations. The last KEEP entries."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import sys_config, sys_seal, sys_users_layout as L

PURPOSE = "diary"
KINDS = ("dream", "thought")
KEEP = 400


def _file(cfg: sys_config.Config, user: str | None) -> Path:
    return L.place(cfg, "state", user) / "diary.sealed"


def read(cfg: sys_config.Config, user: str | None = None) -> list[dict]:
    f = _file(cfg, user)
    return json.loads(sys_seal.read(cfg, f, user, PURPOSE)) if f.exists() else []


def add(cfg: sys_config.Config, items: list[dict], user: str | None = None) -> int:
    """Entries {at, type, text, image}, only dreams and thoughts; one already there (same at and type) not again."""
    rows = read(cfg, user)
    seen = {(r["at"], r["type"]) for r in rows}
    new = [{"at": str(i["at"]), "type": i["type"], "text": str(i["text"]), "image": i.get("image")}
           for i in items if i.get("type") in KINDS and (str(i["at"]), i["type"]) not in seen]
    if new:
        rows = sorted(rows + new, key=lambda r: r["at"])[-KEEP:]
        sys_seal.write(cfg, _file(cfg, user), json.dumps(rows, ensure_ascii=False).encode(), user, PURPOSE)
    return len(new)


def since(cfg: sys_config.Config, kinds: tuple[str, ...], when: datetime, user: str | None = None) -> list[dict]:
    iso = when.isoformat()
    return [r for r in read(cfg, user) if r["type"] in kinds and r["at"] >= iso]
