# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Each user's settings (docs/MULTIUSER.md, U3; the owner's design of 2026-10-03).

Plugins are shared by everyone; what is personal is per user: the settings marked `"scope": "user"` in the schema
(the person's accounts and tokens, their place, their name) live in `usr/<name>/.env` (mode 600), and the folders of
usr/ become `usr/<name>/...`. `for_user` gives the configuration a user's work runs with: the system's values, their
own settings over them, their folders. Before the migration everything is in the one .env as today, so for_user
returns the same values; the migration moves the personal settings into the admin's .env (`split`), the rollback
puts them back (`merge`). Switching single ↔ multi changes nothing for the admin: their settings stay in their folder.
"""
from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

from . import sys_config, sys_users_layout as L

ENV = ".env"
_cache: dict[str, tuple[float, sys_config.Config]] = {}
_lock = threading.Lock()


def user_keys(cfg: sys_config.Config) -> list[str]:
    return sorted(k for k, s in cfg.specs.items() if s.get("scope") == "user")


def env_path(cfg: sys_config.Config, name: str) -> Path:
    return L.usr_home(cfg, name) / ENV


def _own(cfg: sys_config.Config, name: str) -> dict[str, str]:
    f = env_path(cfg, name)
    return sys_config.parse_env(f.read_text(encoding="utf-8"), str(f)) if f.is_file() else {}


def for_user(cfg: sys_config.Config, name: str | None) -> sys_config.Config:
    """The configuration of `name`'s work, computed from the machine's (cfg.base when cfg is already a view). No
    user, or before the migration: the configuration given, unchanged."""
    if not name or not L.migrated(cfg):
        return cfg
    cfg = cfg.base or cfg
    f = env_path(cfg, name)
    stamp = f.stat().st_mtime if f.is_file() else 0.0
    with _lock:
        hit = _cache.get(name)
        if hit and hit[0] == stamp and hit[1].env_file == cfg.env_file:
            return hit[1]
    values, raw = dict(cfg.values), dict(cfg.raw)
    own = _own(cfg, name)
    for k in user_keys(cfg):
        text = own.get(k, cfg.specs[k]["recommended"])
        try:
            values[k] = sys_config.convert(cfg.specs[k], text)
        except ValueError:
            text = cfg.specs[k]["recommended"]
            values[k] = sys_config.convert(cfg.specs[k], text)
        raw[k] = text
    usr = L.usr(cfg)
    for k, spec in cfg.specs.items():                      # usr/x → usr/<name>/x (the same tree for each user)
        if spec["type"] == "path" and k != "AURORA_ROOT":
            p = (cfg.root / str(values[k])).resolve()
            if (p == usr or usr in p.parents) and not str(p.relative_to(usr)).startswith(tuple(L.UNTOUCHED)):
                # with «/» on every system: a .env written on Windows read the same (C223)
                values[k] = raw[k] = (L.usr_home(cfg, name) / p.relative_to(usr)).relative_to(cfg.root).as_posix()
    user_cfg = replace(cfg, values=values, raw=raw, base=cfg, user=name)
    with _lock:
        _cache[name] = (stamp, user_cfg)
    return user_cfg


def write(cfg: sys_config.Config, name: str, changes: dict[str, str]) -> None:
    """Set a user's own settings (only keys of scope user)."""
    bad = [k for k in changes if cfg.specs.get(k, {}).get("scope") != "user"]
    if bad:
        raise ValueError(f"not a user's setting: {', '.join(bad)}")
    sys_config.write_env(env_path(cfg, name), {k: str(v) for k, v in changes.items()})


# ---- migration: the personal settings out of the system's .env into the admin's, and back -----------------------
def split(cfg: sys_config.Config, admin: str) -> int:
    """The personal settings now in the system's .env go to the admin's own .env, and leave the system's."""
    raw = sys_config.parse_env(cfg.env_file.read_text(encoding="utf-8"), str(cfg.env_file))
    mine = {k: raw[k] for k in user_keys(cfg) if k in raw}
    if not mine:
        return 0
    sys_config.write_env(env_path(cfg, admin), mine)
    back = _own(cfg, admin)
    if any(back.get(k) != v for k, v in mine.items()):
        raise RuntimeError("the admin's .env does not hold what was copied: the system's .env is left as it was")
    sys_config.write_env(cfg.env_file, {}, drop=set(mine))
    return len(mine)


def adopt(cfg: sys_config.Config, admin: str) -> list[str]:
    """Settings that became a user's (a new `"scope": "user"` in the schema) and still sit in the system's .env: to the
    admin's own .env, checked, then out of the system's. On the per-user layout only; nothing else moves."""
    if not L.migrated(cfg):
        return []
    cfg = cfg.base or cfg
    raw = sys_config.parse_env(cfg.env_file.read_text(encoding="utf-8"), str(cfg.env_file))
    moving = {k: raw[k] for k in user_keys(cfg) if k in raw}
    if not moving:
        return []
    own = _own(cfg, admin)
    sys_config.write_env(env_path(cfg, admin), {k: v for k, v in moving.items() if k not in own})
    back = _own(cfg, admin)
    if any(k not in back for k in moving):
        raise RuntimeError("the admin's .env does not hold the settings: the system's .env is left as it was")
    sys_config.write_env(cfg.env_file, {}, drop=set(moving))
    with _lock:
        _cache.pop(admin, None)
    return sorted(moving)


def merge(cfg: sys_config.Config, admin: str) -> int:
    """Back: the admin's own settings into the system's .env, and the admin's .env removed."""
    f = env_path(cfg, admin)
    own = {k: v for k, v in _own(cfg, admin).items() if k in set(user_keys(cfg))}
    if own:
        sys_config.write_env(cfg.env_file, own)
    f.unlink(missing_ok=True)
    with _lock:
        _cache.pop(admin, None)
    return len(own)
