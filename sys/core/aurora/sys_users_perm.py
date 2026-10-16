# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What the users may manage by themselves, the admin's choice per user (owner, 16 Oct: «alcune cose le controlla solo
l'admin mentre altre può decidere se farle gestire agli utenti o meno»).

Three kinds of thing:
  ADMIN     the machine's: only the admin, never delegated (security and firewalls, models, harvester, updates, the
            machine's settings, users, HTTPS, status) — the pages of api/modules' adminOnly;
  AREAS     a user's own, the admin decides per user: their routines (make, change, run), their personal settings
            (the settings of scope «user»), their autonomy (sys_autonomy's may_choose, kept there);
  always    a user's own data: their chat, memory (forget included), calendar, notes, files — never taken away.
Kept in <STATUS>/users/permissions.json: {"areas": {user: {area: bool}}}; absent means the area's default.
And each user's daily ceiling on the cloud (owner, 17 Oct: a friend on the owner's subscription, «così almeno evito di
rimanere a secco»): {"cloud": {user: tokens a day}}, every cloud provider counted, the subscription too; 0 = none.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from . import sys_config

AREAS = {"routines": True, "settings": True, "autonomy": False}
# who the person is and how she talks to them: always their own, even when the admin keeps their settings (owner,
# 16 Oct: the personality «modificabile a livello utente», also on the first run)
PERSONAL = ("AURORA_OWNER_NAME", "AURORA_PERSONALITY", "AURORA_CLOUD_MASK_MINE", "AURORA_SOCIAL_PRIVATE_WORDS")
ADMIN = ("security", "firewalls", "models", "harvester", "updates", "settings_machine", "users", "https", "status")
_lock = threading.Lock()


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "users" / "permissions.json"


def load(cfg: sys_config.Config) -> dict:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"areas": {}}


def may(cfg: sys_config.Config, user: str | None, area: str, admin: str | None = None) -> bool:
    """True for the admin (and before multi-user), else the admin's choice for this user, else the area's default."""
    if area not in AREAS:
        raise KeyError(area)
    if not user or user == admin:
        return True
    if area == "autonomy":
        from . import sys_autonomy
        return bool(sys_autonomy.policy(cfg).get("may_choose", {}).get(user, AREAS[area]))
    return bool(load(cfg).get("areas", {}).get(user, {}).get(area, AREAS[area]))


def set_(cfg: sys_config.Config, user: str, area: str, allowed: bool) -> dict:
    if area not in AREAS:
        raise KeyError(area)
    if area == "autonomy":
        from . import sys_autonomy
        sys_autonomy.set_may_choose(cfg, user, allowed)
        return load(cfg)
    with _lock:
        p = load(cfg)
        p.setdefault("areas", {}).setdefault(user, {})[area] = bool(allowed)
        f = _file(cfg)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(p, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    return p


def cloud_cap(cfg: sys_config.Config, user: str | None) -> int:
    """A user's tokens a day on the cloud, the admin's choice (0: no ceiling; the admin is never given one)."""
    return int(load(cfg).get("cloud", {}).get(user or "", 0)) if user else 0


def set_cloud(cfg: sys_config.Config, user: str, tokens: int) -> dict:
    if not 0 <= int(tokens) <= 100_000_000:
        raise ValueError("tokens a day: 0-100,000,000 (0 = no ceiling)")
    with _lock:
        p = load(cfg)
        p.setdefault("cloud", {})[user] = int(tokens)
        f = _file(cfg)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(p, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    return p


def table(cfg: sys_config.Config, users: list[str], admin: str | None) -> dict:
    """For the Users page: every user's areas and cloud ceiling, the fixed admin-only list."""
    return {"areas": list(AREAS), "admin_only": list(ADMIN),
            "users": {u: {a: may(cfg, u, a, admin) for a in AREAS} for u in users if u != admin},
            "cloud": {u: cloud_cap(cfg, u) for u in users if u != admin}}
