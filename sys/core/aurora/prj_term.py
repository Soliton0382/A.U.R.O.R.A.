# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A terminal in a project's cage (roadmap 75; owner, 10 Oct: «anteprime interattive di quello che costruisci» — the
owner's projects are command-line Python programs, so their preview is running them).

The same cage as prj_run (no network at all, an empty environment, a fresh /tmp, the home folders hidden, only the
project's folder writable, Aurora's .venv readable — the project's own .venv first on the PATH when project_install
made it and none of its programs stands for a system one, git the system's and bash by its path: C692), with
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


_cage_ok: dict[str, str] = {}


def cage_works() -> str:
    """'' when a bubblewrap cage can start here, else why not. Some systems forbid the user namespaces it needs —
    GitHub's runners: «bwrap: loopback: failed rtm_newaddr: operation not permitted» (the Install workflow failed on
    it from 0.2.5 to 0.2.8, C264). Asked once a process."""
    if "why" not in _cage_ok:
        try:
            r = subprocess.run(["bwrap", "--unshare-all", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                                "--", "true"], capture_output=True, text=True, timeout=20)
            _cage_ok["why"] = "" if r.returncode == 0 else (r.stderr.strip() or f"exit {r.returncode}")[-200:]
        except (OSError, subprocess.SubprocessError) as e:
            _cage_ok["why"] = str(e)[:200]
    return _cage_ok["why"]


SYSTEM_DIRS = ("/usr/bin", "/bin", "/usr/local/bin", "/usr/sbin", "/sbin")
GIT, BASH = "/usr/bin/git", "/bin/bash"


def shadows(project) -> list[str]:
    """C692: the programs of .venv/bin that stand for a system program (git, bash, any name in /usr/bin…), the
    environment's own python links (to Aurora's interpreter) and activate scripts left out."""
    import sys
    from pathlib import Path
    own = Path(project) / ".venv" / "bin"
    exe = Path(sys.executable).resolve()
    out = []
    try:
        entries = sorted(own.iterdir()) if own.is_dir() and not own.is_symlink() else []
    except OSError:
        return ["?"]                                           # not readable: not trusted
    for e in entries:
        n = e.name
        if n.lower().startswith("activate"):
            continue
        try:
            if e.is_symlink() and e.resolve() == exe:
                continue
        except OSError:
            pass
        if n.lower().startswith(("git", "python", "pip")) or n in ("bash", "sh", "env") or \
                any(os.path.lexists(os.path.join(d, n)) for d in SYSTEM_DIRS):
            out.append(n)
    return out


def open_on(project) -> int:
    """How many terminals are open on this project's folder now (C701: a long run does not start meanwhile)."""
    from pathlib import Path
    try:
        want = Path(project).resolve()
    except OSError:
        return 0
    n = 0
    for s in list(_sessions.values()):
        try:
            if s["proc"].poll() is None and Path(s["path"]).resolve() == want:
                n += 1
        except (KeyError, OSError):
            continue
    return n


def _refuse_during_longrun(cfg: sys_config.Config, project) -> None:
    """C701: a long run's end sets aside a .git it did not find (C658: its caged command may have made it) — a
    repository the user made here meanwhile was moved away. Which of the two made it cannot be told apart (the run
    writes the same folder; any mark of «the user's» it could forge), so the two never overlap: no terminal while a
    long run of the project goes, no long run while a terminal is open (prj_longrun.start). Said, never silent."""
    from pathlib import Path
    from . import prj_longrun
    if prj_longrun.busy(cfg, Path(project).name):
        raise TermError("a long run of this project is going: the terminal opens when it ends or is stopped (its "
                        "end sets aside a .git it did not find — a repository made here meanwhile would be moved "
                        "away, C701)")
    from . import prj_run                                      # C709: nor while an agent's command runs on it
    if prj_run.going(project):
        raise TermError("a command of Aurora's agent is running on this project: open the terminal again in a moment "
                        "(its end sets aside a .git it did not find, C709)")


def _cage(cfg: sys_config.Config, project) -> list[str]:
    from . import prj_run
    _refuse_during_longrun(cfg, project)
    # C675: the user's own git works here (commit) while Aurora runs no git on projects (C674); .git read only otherwise
    args = prj_run.cage(cfg, project, "x", git_writable=True)[:-4]   # without «-- bash -c»
    own = f"{project / '.venv' / 'bin'}:"
    i = args.index("PATH") + 1
    path = args[i][len(own):] if args[i].startswith(own) else args[i]
    # C692: the project's own environment first only when project_install made it (prj_run.trusted_venv) and none of
    # its programs stands for a system one; git a function calling the system's, bash by its path
    if prj_run.trusted_venv(project) and not shadows(project):
        path = own + path
    args[i] = path
    return args + ["--setenv", "TERM", "dumb", "--setenv", "PS1", r"\W $ ",
                   "--setenv", "BASH_FUNC_git%%", f'() {{ {GIT} "$@"\n}}', "--", BASH, "--norc", "-i"]


def start(cfg: sys_config.Config, name: str, user: str | None) -> dict:
    """A new terminal in the project's cage: {"id"}."""
    import pty
    from . import prj_run
    if not shutil.which("bwrap"):
        raise TermError("bubblewrap (bwrap) is not installed: no cage, no terminal")
    if why := cage_works():
        raise TermError(f"the cage cannot start on this system ({why}): no terminal without it")
    project = prj_run.project_dir(cfg, name)
    try:                                                       # C674: how to commit and publish from here
        from . import prj_gitguide
        prj_gitguide.ensure(project)
    except (OSError, ValueError):                              # a link by that name: no guide, the terminal still opens
        pass
    reap()
    with _lock:
        mine = [s for s in _sessions.values() if s["user"] == user and s["proc"].poll() is None]
        if len(mine) >= int(cfg["AURORA_PROJECT_TERM_MAX"]):
            raise TermError(f"already {len(mine)} terminals open: close one first")
    from . import prj_longrun
    with prj_longrun._lock:                                    # C701: the check and the session together, against
        args = _cage(cfg, project)                             # a long run starting meanwhile (its start looks here)
        ours, theirs = pty.openpty()
        try:
            proc = subprocess.Popen(args, stdin=theirs, stdout=theirs, stderr=theirs, close_fds=True,
                                    start_new_session=True)
        except BaseException:
            os.close(ours)
            raise
        finally:
            os.close(theirs)
        sid = secrets.token_urlsafe(12)
        s = {"id": sid, "name": name, "user": user, "proc": proc, "fd": ours, "out": deque(), "size": 0, "seq": 0,
             "cond": threading.Condition(), "started": time.time(), "last": time.time(), "cfg": cfg,
             "path": str(project)}
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
