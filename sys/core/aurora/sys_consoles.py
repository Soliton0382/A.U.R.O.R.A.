# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The devices' own management pages, one click away (owner, 2026-10-28: «una pagina dove posso aggiungere tutte le
pagine di gestione web dei miei device… il firewall, il nas… cliccandoci su posso accedere alla pagina senza che debba
ricordarmi ogni volta i loro indirizzi»). Each user's own list, in their state folder: a name, the address (http or
https only: the page opens it in a new tab), an icon, a group and a note.
"""
from __future__ import annotations

import json
import re
import secrets
from urllib.parse import urlparse

from . import sys_config

MAX = 200
FIELDS = {"name": 60, "url": 500, "icon": 8, "group": 40, "note": 200}


def _file(cfg: sys_config.Config):
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    return d / "consoles.json"


def load(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, items: list[dict]) -> None:
    f = _file(cfg)
    f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    f.chmod(0o600)


def check(item: dict) -> dict:
    """The fields kept, trimmed; the address must be http(s) with a host (never javascript: or a file)."""
    out = {k: str(item.get(k) or "").strip()[:n] for k, n in FIELDS.items()}
    if not out["name"]:
        raise ValueError("name: required")
    if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", out["url"], re.I) and "://" not in out["url"]:
        raise ValueError("url: an http or https address")                  # javascript:, data:, mailto:…
    if "://" not in out["url"]:
        out["url"] = "https://" + out["url"]                               # «10.0.0.9:5443» typed: https
    u = urlparse(out["url"])
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("url: an http or https address")
    return out


def put(cfg: sys_config.Config, item: dict, cid: str | None = None) -> dict:
    """Add (no id) or change one; returns it with its id."""
    items = load(cfg)
    clean = check(item)
    if cid:
        for i, x in enumerate(items):
            if x["id"] == cid:
                items[i] = {"id": cid, **clean}
                _save(cfg, items)
                return items[i]
        raise KeyError(cid)
    if len(items) >= MAX:
        raise ValueError(f"at most {MAX}")
    new = {"id": secrets.token_hex(4), **clean}
    _save(cfg, items + [new])
    return new


def delete(cfg: sys_config.Config, cid: str) -> bool:
    items = load(cfg)
    kept = [x for x in items if x["id"] != cid]
    if len(kept) != len(items):
        _save(cfg, kept)
    return len(kept) != len(items)
