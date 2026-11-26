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
  - at most AURORA_PROJECT_RUN_S seconds, the output's last 8,000 characters;
  - the machine's limits (C688, prj_run_box): a file's size, memory and processes (a cgroup of its own when the
    API's unit delegates one, else RLIMIT_AS and ulimit -u), the project's growth and the machine's free disk.
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
TMP_MB = 2048                    # a cage's /tmp (tmpfs: memory) unless the caller declares its own (C626)
HIDDEN_KB = 64                   # the empty tmpfs over the hidden folders
HIDDEN_SYSTEM = ("/etc/aurora", "/sys/fs/cgroup")   # O3: the machine's own setup, never a cage's to read


def project_dir(cfg: sys_config.Config, name: str) -> Path:
    if not NAME.fullmatch(name or ""):
        raise ValueError("project names: lowercase letters, digits, . _ - (max 64)")
    p = cfg.path("AURORA_PROJECTS_DIR") / name
    if not p.is_dir():
        raise ValueError(f"no project {name}: create it first (projects.project_create)")
    return p


def _locked() -> tuple[str, ...]:
    """The folders only Aurora writes (prj_prereg.LOCKED: prereg/, reviews/, discover/, longrun/, novelty/)."""
    from . import prj_prereg                         # here: prj_prereg imports this module
    return tuple(prj_prereg.LOCKED)


def trusted_venv(project: Path) -> bool:
    """The project's own environment goes first on PATH only when it is the one project_install made: its python a
    link to the interpreter running Aurora (C615: a script named python in the project's .venv, written by a caged command or a
    write tool was taken for it). A caged command cannot make that link: .venv is read only in every cage."""
    py = project / ".venv" / "bin" / "python"
    try:                                             # C629: .venv itself a link (to a folder of the run's) never trusted
        return (not (project / ".venv").is_symlink() and py.is_symlink()
                and py.resolve() == Path(sys.executable).resolve())
    except OSError:
        return False


def guard_dirs(project: Path) -> None:
    """C629: .venv and the folders only Aurora writes must be real folders (or absent): a link or a file there was
    skipped by the read-only binds and stayed writable. ValueError: the command is refused, said why."""
    for d in (".venv", *_locked()):
        p = project / d
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise ValueError(f"{d} in the project is a link or a file, not a folder: refused (only Aurora makes it; "
                             "ask the owner to remove it)")


def cage(cfg: sys_config.Config, project: Path, command: str, readonly: bool = False,
         tmp_mb: int | None = None, git_writable: bool = False, box: dict | None = None) -> list[str]:
    """The bwrap command. `readonly` (the referee, N142): the project bound read only too; its scratch is the private
    tmpfs /tmp, and pytest keeps no cache in the project. /tmp is a tmpfs of at most `tmp_mb` MB (TMP_MB by default;
    C626: tmpfs is the machine's memory), the hidden folders' empty tmpfs of HIDDEN_KB. `git_writable` (C675): the
    project's .git left writable — only for the user's own git (the terminal, the package button) and no
    host-side git runs on an existing project (C674): what a hook planted there could do runs in a cage.
    C688: the machine's limits in front of bwrap (prj_run_box: a file's size, a cgroup's memory and processes or
    their fallback, the disk guard); `box` is their profile — by default «user» for the user's own git cages
    (git_writable: the terminal, the package button), else «run». /dev read only, /dev/shm a small tmpfs (O1: /dev
    was a writable tmpfs of half the memory)."""
    from . import prj_run_box as B
    guard_dirs(project)
    lim = box if box is not None else B.profile("user" if git_writable else "run", readonly)
    venv = Path(sys.prefix)                         # the Python environment running Aurora (its .venv)
    # C684: a command killed by a limit leaves no core dump (a piped core_pattern skips it only at RLIMIT_CORE 1; at
    # 0 systemd-coredump still records it, and the desktop shows the owner an error window for each): prj_run_box
    args = [*B.prefix(lim, project), "bwrap", "--die-with-parent", "--new-session", "--unshare-all",
            "--ro-bind", "/", "/", "--dev", "/dev", "--size", str(int(lim.get("shm_mb") or 64) * 1024 * 1024),
            "--tmpfs", "/dev/shm", "--proc", "/proc", "--size", str(int(tmp_mb or TMP_MB) * 1024 * 1024),
            "--tmpfs", "/tmp"]
    # /run hidden whole (C420, 28 Oct: the host's sockets were there — docker answered «200 OK» from inside, root at one
    # call; libvirt, the system D-Bus with the polkit rule, the firewall helper's socket): no network here, no DNS needed
    # O3 (eighth review): /etc/aurora (the firewall's rules, root's configuration) and the host's cgroup tree hidden too
    for hidden in ("/home", "/root", "/mnt", "/media", "/srv", "/run", *HIDDEN_SYSTEM):
        if Path(hidden).is_dir():
            args += ["--size", str(HIDDEN_KB * 1024), "--tmpfs", hidden]
    root = venv.parent                               # Aurora's folder (its .venv is in it): hidden wherever it lives,
    if (root / "sys" / "core").is_dir():             # outside /home too (C444: .env, the keys, Caddy's socket were there)
        args += ["--size", str(HIDDEN_KB * 1024), "--tmpfs", str(root)]
    if venv.is_dir():
        args += ["--ro-bind", str(venv), str(venv)]
    fem = fem_home(root)                             # N155: FEniCSx (dolfinx, gmsh) read only, as $FEM_PYTHON
    if fem:
        args += ["--ro-bind", str(fem), str(fem)]
    own = project / ".venv" / "bin"                  # the libraries Aurora installed for it (projects.project_install)
    first = f"{own}:" if trusted_venv(project) else ""
    args += ["--ro-bind" if readonly else "--bind", str(project), str(project)]
    if not readonly:                                 # C615: a caged command made a python in .venv and every later
        for d in (".venv", *_locked()):              # «python» was its own; prereg/, reviews/, discover/… could be
            try:                                     # forged: always there, always read only (empty when unused)
                (project / d).mkdir(exist_ok=True)
            except OSError:
                pass
    for ro in ((() if git_writable else (".git",)) + (".venv", *_locked())):   # C420: a hook or core.fsmonitor in .git, a python in .venv ran
        if (project / ro).is_dir() and not (project / ro).is_symlink():   # later outside the cage: read only
            args += ["--ro-bind", str(project / ro), str(project / ro)]
    args += [a for h in HIDDEN_SYSTEM if Path(h).is_dir() for a in ("--remount-ro", h)]   # O3: empty, read only
    args += ["--remount-ro", "/dev", "--clearenv",          # O1: after every mount point made in /dev
             "--setenv", "PATH", f"{first}{venv / 'bin'}:/usr/local/bin:/usr/bin:/bin", "--setenv", "HOME", "/tmp",
             "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
             *(["--setenv", "TMPDIR", "/tmp", "--setenv", "PYTEST_ADDOPTS", "-p no:cacheprovider"] if readonly else []),
             *(["--setenv", "FEM_PYTHON", str(fem / "env" / "bin" / "python"), "--setenv", "CUDA_VISIBLE_DEVICES", "",
                "--setenv", "OMPI_MCA_plm", "isolated", "--setenv", "OMP_NUM_THREADS", "4"] if fem else []),
             "--chdir", str(project), "--", "bash", "-c", B.command(lim, command)]
    return args


def fem_home(root: Path) -> Path | None:
    """sys/runtime/fenicsx when its environment is installed (sys_fem_install.sh), else None (N155)."""
    home = (root / "sys" / "runtime" / "fenicsx").resolve()
    return home if (home / "env" / "bin" / "python").is_file() else None


FEM_RULE = ("Finite elements (Aurora's tool, N155): FEniCSx (dolfinx 0.9, PETSc, MPICH, gmsh, numpy, scipy) is in the "
            "cage as $FEM_PYTHON: run a script of the project with `$FEM_PYTHON -I script.py` (CPU only, no network). "
            "Use it to check a formula or a law with an independent method — Poisson, magnetostatics, eddy currents, "
            "elasticity, heat — and always compare with a case whose exact solution is known first.")


def fem_rule() -> str:
    return FEM_RULE if fem_home(Path(sys.prefix).parent) else ""


SKIP = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
MAX_FILES = 20000


TABLES = (".csv", ".npz")         # the data tables (prj_provenance): never left out of a snapshot, whatever its size


def snapshot_full(project: Path) -> tuple[dict[str, tuple[int, int, int, int]], bool]:
    """(each file of the project → (mtime, size, ctime, inode), capped): without the folders a command fills by itself
    (C384). C649: the ctime and the inode are in it (a table overwritten with the same size and its mtime set back by
    `touch -r` looked unchanged; the ctime cannot be set back without root); past MAX_FILES only the data tables are
    still listed, and `capped` says the rest was not."""
    out: dict[str, tuple[int, int, int, int]] = {}
    stack, capped = [project], False
    while stack:
        try:
            entries = list(stack.pop().iterdir())
        except OSError:                              # C661: a folder it cannot read (chmod 000) hid its tables:
            capped = True                            # what is in it is not known, none of its tables is evidence
            continue
        for e in entries:
            if e.name in SKIP or e.is_symlink():
                continue
            try:
                is_dir, is_file = e.is_dir(), e.is_file()
                if not is_dir and not is_file:
                    os.lstat(e)                      # C661: neither, because it cannot be looked at: not known
            except OSError:
                capped = True
                continue
            if is_dir:
                stack.append(e)
            elif is_file:
                if len(out) >= MAX_FILES and not e.name.lower().endswith(TABLES):
                    capped = True
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:                      # C661: a file it cannot stat (a folder r-- without x)
                    capped = True
                    continue
                out[e.relative_to(project).as_posix()] = (st.st_mtime_ns, st.st_size, st.st_ctime_ns, st.st_ino)
    return out, capped


def snapshot(project: Path) -> dict[str, tuple[int, int, int, int]]:
    """Each file of the project (path → mtime, size, ctime, inode); see snapshot_full."""
    return snapshot_full(project)[0]


def changed(before: dict, after: dict) -> list[str]:
    """The files a command wrote: new ones and those whose time or size changed (a removed file is not «written»)."""
    return sorted(k for k, v in after.items() if before.get(k) != v)


def git_mark(project: Path) -> tuple[int, int] | None:
    """The identity of the project's .git before a command (None: there was none)."""
    try:
        st = os.lstat(project / ".git")
        return (st.st_dev, st.st_ino)
    except OSError:
        return None


def _rename_new(src: Path, dst: Path) -> None:
    """rename(2) that never replaces what is at `dst` (renameat2 RENAME_NOREPLACE; a lexical check where the system
    has none): FileExistsError when something is there."""
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        fn = libc.renameat2
    except (OSError, AttributeError):
        fn = None
    if fn is not None:
        at = -100                                    # AT_FDCWD
        if fn(at, os.fsencode(src), at, os.fsencode(dst), 1) == 0:     # 1: RENAME_NOREPLACE
            return
        err = ctypes.get_errno()
        if err not in (22, 38, 95):                  # EINVAL, ENOSYS, EOPNOTSUPP: this filesystem has no flag
            raise OSError(err, os.strerror(err), str(dst))
    if os.path.lexists(dst):
        raise FileExistsError(17, "exists", str(dst))
    os.rename(src, dst)


def set_aside_git(project: Path, before: tuple[int, int] | None) -> str:
    """C658: a .git a caged command made where there was none is renamed «.git.set-aside-<time>-<random>» (nothing
    of git reads it under that name, nothing is deleted): host-side git ran what its configuration named. C691: the
    name has 64 random bits and the rename never replaces anything (a command planted .git.set-aside-<t>/keep for
    the next seconds and kept its .git: the rename onto a full folder failed); tried again under a new name.
    "" or the note."""
    import secrets
    import stat
    now = git_mark(project)
    if now is None or now == before:
        return ""
    last: OSError | None = None
    for attempt in range(8):
        aside = project / f".git.set-aside-{int(time.time())}-{secrets.token_hex(8)}"
        try:
            _rename_new(project / ".git", aside)
            return f"the command made a .git (none before): set aside as {aside.name}, never run (C658)"
        except FileExistsError as e:                # a name taken (never by chance: 64 bits): another one
            last = e
        except OSError as e:
            last = e
            # C673: the command took the write permission off the project's folder (chmod 555 .): Aurora's own
            # account owns it, so the permission is given back and the rename tried again
            try:
                os.chmod(project, os.stat(project).st_mode | stat.S_IWUSR | stat.S_IXUSR)
            except OSError:
                break
            if attempt >= 2:
                break
    return (f"a .git made by the command could not be set aside ({last}): host-side git refuses it unless its "
            "configuration holds only the keys git init writes (C670)")


_going: dict[str, int] = {}      # C709: the agent's writable commands running now, per project folder


class Busy(RuntimeError):
    """The owner holds the project now (a terminal open, a «Salva»): the command is not run — not a failure of it."""


def going(project) -> int:
    """How many of the agent's writable commands run now on this project's folder (C709)."""
    try:
        return _going.get(str(Path(project).resolve()), 0)
    except OSError:
        return 0


def _enter(project: Path) -> str:
    """C709 (C701 extended): a writable command ends by setting aside a .git it did not find (C658), and which of the
    two made it cannot be told — so it never overlaps the owner's own git: refused while the user's terminal is open
    on the project or its package («Salva») is being made; they refuse while it runs. Checked and counted under
    prj_longrun._lock, the lock the terminal and the package check under. The key."""
    from . import prj_longrun, prj_package, prj_term
    key = str(project.resolve())
    with prj_longrun._lock:
        if (n := prj_term.open_on(project)):
            raise Busy(f"the owner has {n} terminal(s) open on this project: the command runs once they are "
                               "closed (its end sets aside a .git it did not find, C709)")
        if prj_package.making(project):
            raise Busy("the owner is saving this project (its package, a commit): run the command again in a "
                               "moment (its end would set the new .git aside, C709)")
        _going[key] = _going.get(key, 0) + 1
    return key


def _leave(key: str) -> None:
    from . import prj_longrun
    with prj_longrun._lock:
        if _going.get(key, 0) <= 1:
            _going.pop(key, None)
        else:
            _going[key] -= 1


def run(cfg: sys_config.Config, name: str, command: str, readonly: bool = False) -> dict:
    """{"exit", "seconds", "output", "changed"}: the command's result in the cage and the files it wrote (C384: the
    run's summary counted only the write tool's files); ValueError for a bad name or command. `readonly`: nothing of
    the project can be written (the referee's cage, N142)."""
    if not shutil.which("bwrap"):
        raise RuntimeError("bubblewrap (bwrap) is not installed: no cage, nothing is run")
    command = str(command or "").strip()
    if not command or len(command) > 2000:
        raise ValueError("a command of 1 to 2000 characters")
    project = project_dir(cfg, name)
    limit = int(cfg["AURORA_PROJECT_RUN_S"])
    key = _enter(project) if not readonly else ""
    try:
        return _run(cfg, name, project, command, limit, readonly)
    finally:
        if key:
            _leave(key)


def _run(cfg: sys_config.Config, name: str, project: Path, command: str, limit: int, readonly: bool) -> dict:
    before, capped0 = snapshot_full(project)
    gmark = git_mark(project)
    t0 = time.time()
    # C688: its own process group — on the timeout prj_run_box's script and bwrap are ended together
    proc = subprocess.Popen(cage(cfg, project, command, readonly), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        so, se = proc.communicate(timeout=limit)
        code, out = proc.returncode, (so + ("\n" + se if se else ""))
    except subprocess.TimeoutExpired:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        so, _se = proc.communicate()
        code = -1
        out = f"{so or ''}\nSTOPPED after {limit} s (AURORA_PROJECT_RUN_S)"
    out = out.strip()
    note = set_aside_git(project, gmark) if not readonly else ""
    if note:
        out = (out + "\n" + note).strip()
    after, capped1 = snapshot_full(project)
    written = changed(before, after)
    if not readonly and (written or capped0 or capped1):   # C632: the tables a command wrote, by hash (prj_provenance)
        from . import prj_provenance
        prj_provenance.record(cfg, name, project, written, "run")
        if capped0 or capped1:                       # C649: more files than counted: no table of it is evidence
            prj_provenance.record_capped(cfg, name)
    return {"exit": code, "seconds": round(time.time() - t0, 1),
            "output": out if len(out) <= KEEP else "…" + out[-KEEP:], "changed": written}
