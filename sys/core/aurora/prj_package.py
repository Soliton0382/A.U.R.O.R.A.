# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📦 A project packaged for publishing with one button (N148; owner, 20 Nov: «un pulsante che esegue tutto fino al
bundle in automatico… molto meglio che i comandi da terminale»).

The steps of the guide (prj_gitguide) run for the user, in the project's cage (prj_run.cage: no network, only the
project's folder writable, its .git too — C675 — while Aurora runs no git on projects, C674): a repository made if
there is none, the author set if the user gives one (or none is set yet), every change committed with the user's
message, and the whole history written to aurora.bundle — data only, no configuration, no hooks — which the page
offers to download. The push is the user's, from their own computer, after reviewing it. Aurora's GitHub token is
never involved, and nothing runs on the host but bubblewrap.
"""
from __future__ import annotations

import os
import stat
import subprocess
import threading
from pathlib import Path

from . import prj_gitguide, prj_run, prj_safeio, sys_config

BUNDLE = prj_gitguide.BUNDLE
TIMEOUT_S = 180
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class PackageError(Exception):
    pass


# The script run in the cage. Values come through the environment (never into the command line): AUR_MSG, AUR_NAME,
# AUR_EMAIL (the user's, may be empty), AUR_DEF_NAME, AUR_DEF_EMAIL (used only when the repository has no author yet).
# The bundle is written under a temporary name and renamed: a download never sees half a file. The bundle files are
# never committed, whatever .gitignore says.
# C692: the system's git and bash by absolute path, and a PATH without the project's .venv (a wheel's «git» there ran
# as the user's commit): nothing the agent installed runs in the user's own publishing.
GIT, BASH, MV, WC = "/usr/bin/git", "/bin/bash", "/bin/mv", "/usr/bin/wc"
USER_PATH = "/usr/bin:/bin"
_PREPARE = r"""set -e
G=/usr/bin/git
[ -d .git ] || $G init -q -b main
[ -z "$AUR_NAME" ] || $G config user.name "$AUR_NAME"
[ -z "$AUR_EMAIL" ] || $G config user.email "$AUR_EMAIL"
$G config user.name >/dev/null || $G config user.name "$AUR_DEF_NAME"
$G config user.email >/dev/null || $G config user.email "$AUR_DEF_EMAIL"
$G add -A
$G rm --cached -q --ignore-unmatch -- aurora.bundle aurora.bundle.part
if $G diff --cached --quiet; then echo "@@nochange"; else $G commit -q -m "$AUR_MSG"; echo "@@commit"; fi
$G rev-parse -q --verify HEAD >/dev/null || { echo "@@empty"; exit 3; }
[ -n "$AUR_BUNDLE" ] || exit 0
$G bundle create -q aurora.bundle.part --branches
/bin/mv -f aurora.bundle.part aurora.bundle
"""

_STATUS = r"""[ -d .git ] || { echo "@@norepo"; exit 0; }
G=/usr/bin/git
echo "@@name $($G config user.name || true)"
echo "@@email $($G config user.email || true)"
$G log --branches -8 --format='@@log %h %cs %s' 2>/dev/null || true
echo "@@dirty $($G status --porcelain -- . ':(exclude)aurora.bundle' ':(exclude)aurora.bundle.part' 2>/dev/null | /usr/bin/wc -l)"
"""


def user_cage(args: list[str]) -> list[str]:
    """A cage of prj_run made the user's (C692): PATH without the project's .venv (nor Aurora's), bash by its path."""
    args = list(args)
    i = args.index("PATH") + 1
    args[i] = USER_PATH
    if len(args) >= 4 and args[-4] == "--" and args[-3] == "bash":
        args[-3] = BASH
    return args


def _run(cfg: sys_config.Config, project: Path, script: str, env: dict[str, str], writable: bool) -> tuple[int, str]:
    args = user_cage(prj_run.cage(cfg, project, script, readonly=not writable, git_writable=writable))
    extra: list[str] = []
    for k, v in env.items():
        extra += ["--setenv", k, v]
    args = args[:-4] + extra + args[-4:]                  # before «-- bash -c script»
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise PackageError(f"git took more than {TIMEOUT_S} s: stopped") from None
    return r.returncode, (r.stdout + ("\n" + r.stderr if r.stderr else ""))


def _bundle_info(project: Path) -> dict | None:
    """Size and modification time of the project's aurora.bundle, opened without following a link; None if absent."""
    try:
        fd = prj_safeio.open_in(project, BUNDLE, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except (OSError, ValueError):
        return None
    try:
        st = os.fstat(fd)
        return {"size": st.st_size, "mtime": int(st.st_mtime)} if stat.S_ISREG(st.st_mode) else None
    finally:
        os.close(fd)


def status(cfg: sys_config.Config, name: str) -> dict:
    """What the page shows: the author git will sign with, the last commits, uncommitted changes, the bundle."""
    project = prj_run.project_dir(cfg, name)
    out = {"repo": False, "name": "", "email": "", "commits": [], "dirty": 0, "bundle": _bundle_info(project),
           "enabled": True}
    code, text = _run(cfg, project, _STATUS, {}, writable=False)
    for line in text.splitlines():
        if line.startswith("@@name "):
            out["repo"], out["name"] = True, line[7:].strip()
        elif line.startswith("@@email "):
            out["email"] = line[8:].strip()
        elif line.startswith("@@log "):
            out["commits"].append(line[6:].strip())
        elif line.startswith("@@dirty "):
            out["dirty"] = int(line[8:].strip() or 0)
    return out


def _key(project) -> str:
    """C713: one key for a project's folder, however it is named (prj_longrun.start and prj_run use it resolved)."""
    try:
        return str(Path(project).resolve())
    except OSError:
        return str(project)


def making(project) -> bool:
    """C709: whether a package (or «Salva») of this project is being made now: its lock held."""
    with _guard:
        lock = _locks.get(_key(project))
    return bool(lock and lock.locked())


def prepare(cfg: sys_config.Config, name: str, user: str | None, message: str, author: str = "",
            email: str = "", bundle: bool = True) -> dict:
    """Commit the project's changes and write aurora.bundle (`bundle`; without it the page's «Salva»), in its cage. ValueError for bad input; PackageError when
    git fails (its own words)."""
    message = str(message or "").strip()
    if not 1 <= len(message) <= 500:
        raise ValueError("a commit message of 1 to 500 characters")
    author, email = str(author or "").strip(), str(email or "").strip()
    for v in (author, email):
        if len(v) > 200 or any(c in v for c in "\n\r\0<>"):
            raise ValueError("author and email: one line, at most 200 characters, no < >")
    if email and "@" not in email:
        raise ValueError("the email needs an @")
    project = prj_run.project_dir(cfg, name)
    who = user or "aurora-user"
    with _guard:
        lock = _locks.setdefault(_key(project), threading.Lock())
    if not lock.acquire(blocking=False):
        raise PackageError("a package of this project is being made: wait for it")
    try:
        from . import prj_longrun                         # C692: a run's finish could set the new .git aside
        with prj_longrun._lock:                           # C709: checked where run_in_project checks «making»
            if prj_longrun.busy(cfg, name):
                raise PackageError("a long run of this project is going: the package is made once it has ended "
                                   "(stop it, or wait for it, then press the button again)")
            if prj_run.going(project):
                raise PackageError("a command of Aurora's agent is running on this project: press the button again "
                                   "in a moment (its end sets aside a .git it did not find, C709)")
        try:
            prj_gitguide.ensure(project)                  # the guide, and the bundle kept out of .gitignore'd commits
        except (OSError, ValueError):
            pass
        code, text = _run(cfg, project, _PREPARE, {"AUR_MSG": message, "AUR_NAME": author, "AUR_EMAIL": email,
                                                   "AUR_DEF_NAME": who, "AUR_DEF_EMAIL": f"{who}@users.aurora.invalid",
                                                   "AUR_BUNDLE": "1" if bundle else ""},
                          writable=True)
    finally:
        lock.release()
    if "@@empty" in text:
        raise PackageError("the project has no file to commit yet")
    if code != 0:
        raise PackageError("git: " + "\n".join(l for l in text.splitlines() if not l.startswith("@@"))[-1500:].strip())
    out = status(cfg, name)
    out["committed"] = "@@commit" in text
    return out


def open_bundle(cfg: sys_config.Config, name: str) -> tuple[int, int]:
    """(file descriptor, size) of the project's aurora.bundle, opened without following a link; FileNotFoundError."""
    project = prj_run.project_dir(cfg, name)
    try:
        fd = prj_safeio.open_in(project, BUNDLE, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except (OSError, ValueError):
        raise FileNotFoundError(BUNDLE) from None
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise FileNotFoundError(BUNDLE)
    return fd, st.st_size
