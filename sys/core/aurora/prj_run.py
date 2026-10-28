# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Run a command in one of the user's local projects — Aurora's tests, her program — in a cage of its own
(owner, 2026-10-04: Aurora writes the code, runs the tests, reads the results and tries again until it works).

The code is Aurora's own and not reviewed, so the cage is strict, and not the projects plugin's (that one has the
network and the GitHub token for the push; a cage cannot be opened inside another one here):
  - no network at all, an empty environment (no token, no key), a fresh /tmp;
  - the home folders, /mnt and /media hidden: the owner's files, the NAS and Aurora's .env are not there;
  - only the project's folder writable; Aurora's Python environment (.venv) readable, to run pytest; the project's own
    environment first when Aurora installed libraries for it (<project>/.venv, projects.project_install);
  - at most AURORA_PROJECT_RUN_S seconds, the output's last 8,000 characters.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import sys_config

NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
# git run here on a project's own .git (not trusted, C420): no fsmonitor command, no hook
GIT_SAFE = ["-c", "core.fsmonitor=", "-c", f"core.hooksPath={os.devnull}"]
KEEP = 8000


def project_dir(cfg: sys_config.Config, name: str) -> Path:
    if not NAME.fullmatch(name or ""):
        raise ValueError("project names: lowercase letters, digits, . _ - (max 64)")
    p = cfg.path("AURORA_PROJECTS_DIR") / name
    if not p.is_dir():
        raise ValueError(f"no project {name}: create it first (projects.project_create)")
    return p


def cage(cfg: sys_config.Config, project: Path, command: str) -> list[str]:
    venv = Path(sys.prefix)                         # the Python environment running Aurora (its .venv)
    args = ["bwrap", "--die-with-parent", "--new-session", "--unshare-all", "--ro-bind", "/", "/",
            "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
    # /run hidden whole (C420, 28 Oct: the host's sockets were there — docker answered «200 OK» from inside, root at one
    # call; libvirt, the system D-Bus with the polkit rule, the firewall helper's socket): no network here, no DNS needed
    for hidden in ("/home", "/root", "/mnt", "/media", "/srv", "/run"):
        if Path(hidden).is_dir():
            args += ["--tmpfs", hidden]
    root = venv.parent                               # Aurora's folder (its .venv is in it): hidden wherever it lives,
    if (root / "sys" / "core").is_dir():             # outside /home too (C444: .env, the keys, Caddy's socket were there)
        args += ["--tmpfs", str(root)]
    if venv.is_dir():
        args += ["--ro-bind", str(venv), str(venv)]
    own = project / ".venv" / "bin"                  # the libraries Aurora installed for it (projects.project_install)
    first = f"{own}:" if (own / "python").exists() else ""
    args += ["--bind", str(project), str(project)]
    for ro in (".git", ".venv"):                     # C420: a hook or core.fsmonitor in .git, a python in .venv ran
        if (project / ro).is_dir():                  # later outside the cage (git status, pip --python): read only
            args += ["--ro-bind", str(project / ro), str(project / ro)]
    args += ["--clearenv",
             "--setenv", "PATH", f"{first}{venv / 'bin'}:/usr/local/bin:/usr/bin:/bin", "--setenv", "HOME", "/tmp",
             "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
             "--chdir", str(project), "--", "bash", "-c", command]
    return args


SKIP = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
MAX_FILES = 20000


def snapshot(project: Path) -> dict[str, tuple[int, int]]:
    """Each file of the project (path → mtime, size), without the folders a command fills by itself (C384)."""
    out: dict[str, tuple[int, int]] = {}
    stack = [project]
    while stack and len(out) < MAX_FILES:
        try:
            entries = list(stack.pop().iterdir())
        except OSError:
            continue
        for e in entries:
            if e.name in SKIP or e.is_symlink():
                continue
            if e.is_dir():
                stack.append(e)
            elif e.is_file():
                try:
                    st = e.stat()
                except OSError:
                    continue
                out[e.relative_to(project).as_posix()] = (st.st_mtime_ns, st.st_size)
    return out


def changed(before: dict, after: dict) -> list[str]:
    """The files a command wrote: new ones and those whose time or size changed (a removed file is not «written»)."""
    return sorted(k for k, v in after.items() if before.get(k) != v)


def run(cfg: sys_config.Config, name: str, command: str) -> dict:
    """{"exit", "seconds", "output", "changed"}: the command's result in the cage and the files it wrote (C384: the
    run's summary counted only the write tool's files); ValueError for a bad name or command."""
    if not shutil.which("bwrap"):
        raise RuntimeError("bubblewrap (bwrap) is not installed: no cage, nothing is run")
    command = str(command or "").strip()
    if not command or len(command) > 2000:
        raise ValueError("a command of 1 to 2000 characters")
    project = project_dir(cfg, name)
    limit = int(cfg["AURORA_PROJECT_RUN_S"])
    before = snapshot(project)
    t0 = time.time()
    try:
        r = subprocess.run(cage(cfg, project, command), capture_output=True, text=True, timeout=limit)
        code, out = r.returncode, (r.stdout + ("\n" + r.stderr if r.stderr else ""))
    except subprocess.TimeoutExpired as e:
        code = -1
        out = f"{(e.stdout or b'').decode(errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or '')}" \
              f"\nSTOPPED after {limit} s (AURORA_PROJECT_RUN_S)"
    out = out.strip()
    return {"exit": code, "seconds": round(time.time() - t0, 1),
            "output": out if len(out) <= KEEP else "…" + out[-KEEP:], "changed": changed(before, snapshot(project))}
