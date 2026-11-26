# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Each user's own archive (R15; owner, 27 Nov: «file a livello di cartella utente… ogni utente avrà una cartella
nuova evidentia»; «ognuno possa collegare il percorso che vuole»).

A request says whose it is (the header X-Evidentia-User, set by Aurora's side: its proxy, its chat, its worker, its
plugin — the socket answers Aurora's account only); the archive is chosen for that request:
  the owner (EVD_OWNER)   EVD_DATA_DIR, the archive as it was before (nothing moved);
  another user            <EVD_ARCHIVE_DIR>/<user>/data, made the first time (EVD_ARCHIVE_DIR root's, group evidentia);
  no user said            the owner's (a client of before: the owner's tools on this machine).
A user's name is letters, digits, _ and - only: never a path. Each archive is whole: its corpus, findings, case
files, audit trails, vectors — nothing of one is seen from another."""
from __future__ import annotations

import contextvars
import re
from pathlib import Path

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
USER: contextvars.ContextVar[str] = contextvars.ContextVar("evidentia_user", default="")


def owner(cfg) -> str:
    try:
        return str(cfg["EVD_OWNER"]).strip()
    except KeyError:
        return ""


def folder(cfg, user: str | None = None, make: bool = True) -> Path:
    """The data folder of `user` (the request's when None)."""
    u = (USER.get() if user is None else user) or ""
    if not u or u == owner(cfg):
        return cfg.path("EVD_DATA_DIR")
    if not NAME.match(u):
        raise ValueError("a user's name: lowercase letters, digits, _ and -")
    try:
        root = Path(str(cfg["EVD_ARCHIVE_DIR"]).strip() or "/var/lib/evidentia")
    except KeyError:
        root = Path("/var/lib/evidentia")
    d = root / u / "data"
    if make and not d.is_dir():
        if not root.is_dir():
            raise ValueError(f"no archives' folder ({root}): install Evidentia again")
        (root / u).mkdir(mode=0o2770, exist_ok=True)
        d.mkdir(mode=0o2770, exist_ok=True)
    return d


def who() -> str:
    return USER.get()
