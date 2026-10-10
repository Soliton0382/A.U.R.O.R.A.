# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A terminal in a project's cage (roadmap 75; owner, 10 Oct: «anteprime interattive di quello che costruisci» — the
owner's projects are command-line Python programs, so their preview is running them).

The same cage as prj_run (no network at all, an empty environment, a fresh /tmp, the home folders hidden, only the
project's folder writable, Aurora's .venv readable — the project's own .venv first on the PATH when it has one), with
a pseudo-terminal: a program that asks for input (input(), a menu) works. No WebSocket library in Aurora: the output
goes to the page as Server-Sent Events, what the user types comes back as POSTs.
Limits: AURORA_PROJECT_TERM_MAX sessions a user, closed after AURORA_PROJECT_TERM_IDLE_MIN minutes without input and
after AURORA_PROJECT_TERM_MAX_MIN minutes in all; the last 256 KB of output kept for a page that reconnects.
Linux only (bubblewrap and a pty): elsewhere it says so and nothing runs.
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import threading
import time
from collections import deque

from . import sys_config

KEEP = 256 * 1024
_sessions: dict[str, dict] = {}
_lock = threading.Lock()
_reaper: list[threading.Thread] = []


class TermError(Exception):
    pass


def _cage(cfg: sys_config.Config, project) -> list[str]:
    from . import prj_run
    args = prj_run.cage(cfg, project, "x")[:-4]               # the cage without its «-- bash -c command»
    own = project / ".venv" / "bin"
    if own.is_dir():                                           # the project's own environment first
        i = args.index("PATH") + 1
        args[i] = f"{own}:{args[i]}"
    return args + ["--setenv", "TERM", "dumb", "--setenv", "PS1", r"\W $ ", "--", "bash", "--norc", "-i"]


def start(cfg: sys_config.Config, name: str, user: str | None) -> dict:
    """A new terminal in the project's cage: {"id"}."""
    import pty
    from . import prj_run
    if not shutil.which("bwrap"):
        raise TermError("bubblewrap (bwrap) is not installed: no cage, no terminal")
    project = prj_run.project_dir(cfg, name)
    reap()
    with _lock:
        mine = [s for s in _sessions.values() if s["user"] == user and s["proc"].poll() is None]
        if len(mine) >= int(cfg["AURORA_PROJECT_TERM_MAX"]):
            raise TermError(f"already {len(mine)} terminals open: close one first")
    ours, theirs = pty.openpty()
    proc = subprocess.Popen(_cage(cfg, project), stdin=theirs, stdout=theirs, stderr=theirs, close_fds=True,
                            start_new_session=True)
    os.close(theirs)
    sid = secrets.token_urlsafe(12)
    s = {"id": sid, "name": name, "user": user, "proc": proc, "fd": ours, "out": deque(), "size": 0, "seq": 0,
         "cond": threading.Condition(), "started": time.time(), "last": time.time(), "cfg": cfg}
    with _lock:
        _sessions[sid] = s
    threading.Thread(target=_read, args=(s,), daemon=True, name=f"term-{sid[:6]}").start()
    if not _reaper:                                            # one watcher closes what nobody looks at any more
        _reaper.append(threading.Thread(target=_watch, daemon=True, name="term-reaper"))
        _reaper[0].start()
    return {"id": sid}


def _watch(every_s: int = 60) -> None:
    while True:
        time.sleep(every_s)
        try:
            reap()
        except Exception:  # noqa: BLE001 — the watcher never dies
            continue


def _read(s: dict) -> None:
    while True:
        try:
            data = os.read(s["fd"], 4096)
        except OSError:                                        # the program ended: the pty is closed
            data = b""
        with s["cond"]:
            if data:
                s["seq"] += 1
                s["out"].append((s["seq"], data))
                s["size"] += len(data)
                while s["size"] > KEEP and len(s["out"]) > 1:
                    s["size"] -= len(s["out"].popleft()[1])
            else:
                s["ended"] = True
            s["cond"].notify_all()
        if not data:
            return


def get(sid: str, user: str | None) -> dict:
    s = _sessions.get(sid)
    if s is None or s["user"] != user:
        raise KeyError(sid)
    return s


def chunks(sid: str, user: str | None, after: int, wait_s: float = 15) -> tuple[list[tuple[int, str]], bool]:
    """The output after `after` (waiting up to wait_s for some), and whether the terminal has ended."""
    s = get(sid, user)
    with s["cond"]:
        if not any(n > after for n, _ in s["out"]) and not s.get("ended"):
            s["cond"].wait(wait_s)
        return [(n, d.decode("utf-8", "replace")) for n, d in s["out"] if n > after], bool(s.get("ended"))


def write(sid: str, user: str | None, data: str) -> None:
    s = get(sid, user)
    if s.get("ended"):
        raise TermError("the terminal has ended")
    s["last"] = time.time()
    os.write(s["fd"], data.encode("utf-8")[:8192])


def stop(sid: str, user: str | None) -> None:
    _kill(get(sid, user))


def _kill(s: dict) -> None:
    import signal
    try:
        os.killpg(s["proc"].pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        s["proc"].wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    with _lock:
        _sessions.pop(s["id"], None)
    try:
        os.close(s["fd"])
    except OSError:
        pass


def reap(now: float | None = None) -> int:
    """Closed: the terminals idle or too old (and the ended ones)."""
    now = now or time.time()
    gone = 0
    for s in list(_sessions.values()):
        cfg = s["cfg"]
        idle = now - s["last"] > int(cfg["AURORA_PROJECT_TERM_IDLE_MIN"]) * 60
        old = now - s["started"] > int(cfg["AURORA_PROJECT_TERM_MAX_MIN"]) * 60
        if idle or old or (s.get("ended") and now - s["last"] > 60):
            _kill(s)
            gone += 1
    return gone
