# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The line (aurora-app F2, owner 25 Oct: «chiamate dentro Aurora senza passare da terzi»): what Web Push brings to a
browser, brought to Aurora's Android app by a request the app keeps open (GET /v1/aurora/line), with no push service
in between. The same notifications the owner chose for push (sys_push.message), plus what only the app can take later
(a call that rings). Each user's last events are kept in their state folder (line/events.jsonl, 0600), so a phone that
was offline gets what it missed (up to TTL) when it comes back; the id it got last is its acknowledgement."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import sys_config

KEEP, TTL = 200, 12 * 3600                            # events kept per user; older than TTL are not delivered (as push)
WAIT_MAX = 55                                          # seconds a request is held: under the usual 60 s idle timeouts

_lock = threading.Lock()
version = 0                       # grows at every event: a waiting request looks only at this, not at the file


def _file(cfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user) / "line"
    d.mkdir(parents=True, exist_ok=True)
    return d / "events.jsonl"


def post(msg: dict, cfg: sys_config.Config) -> dict:
    """One event on the line of the current user: {"id", "at", **msg}; ids grow (nanoseconds, as text)."""
    global version
    f = _file(cfg)
    with _lock:
        old = f.read_text(encoding="utf-8").splitlines()[-(KEEP - 1):] if f.exists() else []
        last = int(json.loads(old[-1])["id"]) if old else 0
        ev = {"id": str(max(time.time_ns(), last + 1)), "at": round(time.time(), 1), **msg}
        fd = os.open(f.with_suffix(".tmp"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write("\n".join(old + [json.dumps(ev, ensure_ascii=False)]) + "\n")
        os.replace(f.with_suffix(".tmp"), f)
        version += 1
    return ev


def since(after: str | int | None, cfg: sys_config.Config) -> list[dict]:
    """The events after the one the phone got last (all the recent ones when it says none), oldest first."""
    try:
        after_id = int(after or 0)
    except (TypeError, ValueError):
        after_id = 0
    f, now, out = _file(cfg), time.time(), []
    for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if int(ev["id"]) > after_id and now - ev.get("at", 0) <= TTL:
            out.append(ev)
    return out


def last(cfg: sys_config.Config) -> str:
    """The newest id: a phone that connects for the first time starts from here, not from the old news."""
    f = _file(cfg)
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    try:
        return json.loads(lines[-1])["id"] if lines else "0"
    except (ValueError, KeyError):
        return "0"

