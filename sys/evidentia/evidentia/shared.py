# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Case files shared between users, as projects are (owner, 27 Nov: «tra utenti si possono intraprendere
collaborazioni su fascicoli, come succede per i progetti»).

A case file stays in the archive of who made it; its maker names members. A member sees it in their list (marked
whose it is) and works on it — its diary, its searches, its leads, its trail — against the maker's archive: the
documents of a shared case are the maker's, shared with it. Only the maker changes the members, renames or deletes it.
Every step a member takes is written in the case's own trail with the member's name (audit.py).

The registry: <EVD_ARCHIVE_DIR>/_shared.json, {case id: {"owner": the maker («» the archive's owner), "members": [...]}},
written by Evidentia's account only, under a lock."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path

from . import archive

FILE = "_shared.json"
ACTOR = archive.contextvars.ContextVar("evidentia_actor", default="")   # who asked, when the archive is another's


def _root(cfg) -> Path:
    try:
        return Path(str(cfg["EVD_ARCHIVE_DIR"]).strip() or "/var/lib/evidentia")
    except KeyError:
        return Path("/var/lib/evidentia")


def load(cfg) -> dict:
    try:
        d = json.loads((_root(cfg) / FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


@contextlib.contextmanager
def _locked(cfg):
    root = _root(cfg)
    with open(root / (FILE + ".lock"), "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        yield root


def set_members(cfg, cid: str, maker: str, members: list[str]) -> dict:
    """The maker's case shared with these users (none: not shared any more)."""
    names = sorted({m for m in members if archive.NAME.match(str(m)) and m != maker})
    with _locked(cfg) as root:
        d = load(cfg)
        if names:
            d[cid] = {"owner": maker, "members": names}
        else:
            d.pop(cid, None)
        tmp = root / (FILE + ".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o660)
        tmp.replace(root / FILE)
    return d.get(cid) or {"owner": maker, "members": []}


def whose(cfg, cid: str, who: str) -> str | None:
    """The maker of a case `who` may open as a member, else None (their own, or not shared with them)."""
    s = load(cfg).get(cid)
    if s and who and who in (s.get("members") or []) and s.get("owner", "") != who:
        return s.get("owner", "")
    return None


def shared_with(cfg, who: str) -> list[tuple[str, str]]:
    """(case id, maker) of the cases shared with `who`."""
    return [(cid, s.get("owner", "")) for cid, s in load(cfg).items() if who and who in (s.get("members") or [])]


def members(cfg, cid: str) -> list[str]:
    return list((load(cfg).get(cid) or {}).get("members") or [])
