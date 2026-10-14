# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Services of one's own, OpenAI-compatible (owner, 15 Oct: «la parte custom non permette di inserire parametri… ollama
oppure altri modelli api come kimi… con la possibilità di dargli un nome e il tasto più per aggiungere diversi custom;
i custom si possono rimuovere, i default no»).

Each service has a name, an address and, if it asks one, a key (an account of mdl_accounts, shared or a user's). The
admin adds them; they join mdl_router.PROVIDERS as «svc_<slug>», so every step of the Models page can use them, and
they go out masked like every cloud call. The built-in providers are never removed. Every process sees a change at its
next call (the file's mtime: aurora-rem, the sentinel)."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from . import sys_config

PREFIX = "svc_"
# suggestions, each address editable: the form fills them in, the «try» button proves them
PRESETS = [
    {"name": "Ollama", "base": "http://localhost:11434/v1", "key": False},
    {"name": "LM Studio", "base": "http://localhost:1234/v1", "key": False},
    {"name": "Kimi (Moonshot)", "base": "https://api.moonshot.ai/v1", "key": True},
    {"name": "DeepSeek", "base": "https://api.deepseek.com/v1", "key": True},
    {"name": "Groq", "base": "https://api.groq.com/openai/v1", "key": True},
]
_lock = threading.Lock()
_seen = {"mtime": None, "file": None}


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "cloud_services.json"


def load(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, rows: list[dict]) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(rows, h, ensure_ascii=False, indent=1)
    os.replace(tmp, f)
    refresh(cfg, force=True)


def spec(row: dict) -> dict:
    return {"label": row["name"], "kind": "openai", "key": None, "base": row["base"], "key_optional": True,
            "custom": True}


def refresh(cfg: sys_config.Config | None = None, force: bool = False) -> None:
    """The services in mdl_router.PROVIDERS as the file says now (one stat a call; reread when it changed)."""
    from .mdl_router import PROVIDERS
    try:
        cfg = cfg or sys_config.get()
        f = _file(cfg)
        mtime = f.stat().st_mtime if f.exists() else 0
    except Exception:                                      # noqa: BLE001 — no configuration yet: the built-in ones
        return
    if not force and _seen["file"] == f and _seen["mtime"] == mtime:
        return
    with _lock:
        for k in [k for k in PROVIDERS if k.startswith(PREFIX)]:
            del PROVIDERS[k]
        for row in load(cfg):
            PROVIDERS[row["id"]] = spec(row)
        _seen.update(file=f, mtime=mtime)


def clean_base(base: str) -> str:
    u = urlparse((base or "").strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("an address like https://api.example.com/v1 or http://localhost:11434/v1")
    return (base or "").strip().rstrip("/")


def add(cfg: sys_config.Config, name: str, base: str) -> dict:
    name = re.sub(r"\s+", " ", (name or "").strip())[:40]
    if not name:
        raise ValueError("a name for the service")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:24] or "service"
    rows = load(cfg)
    ids = {r["id"] for r in rows}
    sid, n = PREFIX + slug, 2
    while sid in ids:
        sid, n = f"{PREFIX}{slug}_{n}", n + 1
    row = {"id": sid, "name": name, "base": clean_base(base), "created": time.time()}
    _save(cfg, rows + [row])
    return row


def remove(cfg: sys_config.Config, sid: str) -> None:
    """A service of one's own gone, with its accounts; a built-in provider is never removed."""
    if not sid.startswith(PREFIX):
        raise ValueError("a built-in provider is not removed")
    rows = load(cfg)
    if sid not in {r["id"] for r in rows}:
        raise KeyError(sid)
    from . import mdl_accounts
    for a in [a for a in mdl_accounts.load(cfg)["accounts"] if a["provider"] == sid]:
        mdl_accounts.remove(cfg, a["id"])
    _save(cfg, [r for r in rows if r["id"] != sid])
