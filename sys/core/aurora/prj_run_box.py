# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧱 The machine's limits around every project cage (C688, seventh review of N145, 20 Nov: a caged command wrote 1.5 GB
in 0.4 s with no file-size, disk or memory limit; a long run of disk_mb 10 wrote 954 MB between two of its 15 s looks;
the cage's /dev was a writable tmpfs as large as half the memory).

prj_run.cage puts this file, run as a script by Aurora's own python (`python -I prj_run_box.py <conf> bwrap …`, only
the standard library: nothing of the project is on its path), in front of bwrap. Before the cage starts it sets:
  - RLIMIT_CORE (1, 1) (C684: no core dump, no error window on the owner's desktop for a limit kill);
  - RLIMIT_FSIZE: no single file larger than the profile's file_mb (SIGXFSZ);
  - with a cgroup the API's unit delegates (prj_longrun_meter.delegated: Delegate=cpu memory pids), a cgroup of the
    cage's own, joined by its first process before bwrap: memory.max (its /tmp and /dev/shm RAM disks included),
    memory.swap.max 0, memory.oom.group, pids.max; ended (cgroup.kill) and removed when the cage ends. Without one, the
    fallback: RLIMIT_AS for an agent's writable command (never for Lean, the referee or the GPU: they map far more than
    they use) and, in the command, `ulimit -u` (RLIMIT_NPROC set before bwrap is counted against every process of the
    account on the host — measured: bwrap refused to start at 40 with 124 processes — inside it, in the cage's own
    user namespace only). C702: that fallback is no memory ceiling (per process: 6 × 200 MB and 953 MB in /tmp passed
    a 300 MB profile), and the command's output says so;
  - a disk guard on the project's filesystem (statvfs, every EVERY_S: a few microseconds): stopped when the machine's
    free space falls under a floor (FLOOR, never more than half of what was free at the start; free inodes likewise),
    and, with a budget, when the free space fell by more than the budget since the last exact measure — then the
    project is measured exactly (prj_run_disk: every folder, no link followed, the files it deleted and still holds
    open or mapped — C700: those mapped counted by the free space lost, their size unreadable unprivileged) and the
    command stopped only when it is really over; else the delta starts again from there (the machine's other writers
    are no reason to stop it). Exit DISK_STOP, the reason on stderr.
The long runs use the same script for the rlimits only (their own meter and their own guard: Guard, below).
What no unprivileged process can do here: a hard per-project disk quota (ext4 project quotas need root to set the
project id and the quota; a loop image needs root to mount) — see C688.
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import sys
import time
from pathlib import Path

MB = 1024 * 1024
DISK_STOP = 95                   # the cage stopped by the disk guard
JOIN_FAILED = 96                 # the cage's cgroup could not be joined (the same code as the long runs' entry)
EVERY_S = 0.002                  # the disk guard's look (a statvfs: microseconds)
FLOOR_EVERY_S = 0.05             # with the floor only (the terminal, the package): far from it, a slower look
CONFIRM_S = 0.25                 # at most four exact measures a second when the cheap trigger keeps firing
PREFIX = "cage-"
try:
    RAM_MB = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // MB
except (AttributeError, ValueError, OSError):
    RAM_MB = 8192


def profile(kind: str, readonly: bool = False) -> dict:
    """The limits of a cage. «run»: an agent's command, the referee, a proof, a search (14.5 GB on this machine's
    58 GB: a quarter, at most 16 GB; 512 processes; a file at most 1 GB; the project may grow by 2 GB, measured).
    «user»: the user's own terminal and package button — generous but present (half the memory, at most 32 GB; 1,024
    processes; a file at most 16 GB; the floor only). «longrun»: only the rlimits, prj_longrun has the rest."""
    if kind == "user":
        return {"cgroup": True, "mem_mb": min(32768, RAM_MB // 2), "tasks": 1024, "file_mb": 16384, "disk_mb": 0,
                "watch": True, "as": False, "shm_mb": 256}
    if kind == "longrun":
        return {"cgroup": False, "file_mb": 0, "watch": False, "as": False, "shm_mb": 64, "tasks": 0}
    return {"cgroup": True, "mem_mb": min(16384, RAM_MB // 4), "tasks": 512, "file_mb": 1024,
            "disk_mb": 0 if readonly else 2048, "watch": not readonly, "as": not readonly, "shm_mb": 64}


def prefix(lim: dict, project: Path) -> list[str]:
    """The argv put in front of bwrap for these limits."""
    conf = {"file_mb": int(lim.get("file_mb") or 0)}
    if lim.get("cgroup"):
        conf.update(mem_mb=int(lim["mem_mb"]), tasks=int(lim["tasks"]))
        try:
            from . import prj_longrun_meter as M
            base = M.delegated()
        except Exception:  # noqa: BLE001 — no delegation: the fallback below
            base = None
        conf["cg"] = str(base) if base is not None else ""
        if lim.get("as"):
            conf["as_mb"] = int(lim["mem_mb"])
    if lim.get("watch"):
        conf.update(watch=str(project), disk_mb=int(lim.get("disk_mb") or 0))
    return [sys.executable, "-I", str(Path(__file__).resolve()), json.dumps(conf, separators=(",", ":"))]


def command(lim: dict, cmd: str) -> str:
    """The command with its processes limited in its own user namespace (the fallback when no cgroup holds them)."""
    n = int(lim.get("tasks") or 0)
    return f"ulimit -u {n} 2>/dev/null; {cmd}" if n else cmd


# ---- the disk: measured and guarded -----------------------------------------------------------------------------
try:
    from .prj_run_disk import (MAX_ENTRIES, Unmeasurable, cgroup_procs, deleted_open_bytes, disk_bytes,  # noqa: F401
                               held, tree)
except ImportError:              # run as a script (python -I prj_run_box.py): its sibling by its path, nothing on sys.path
    import importlib.util as _iu
    _spec = _iu.spec_from_file_location("prj_run_disk", Path(__file__).with_name("prj_run_disk.py"))
    _disk = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_disk)
    MAX_ENTRIES, Unmeasurable, cgroup_procs, deleted_open_bytes, disk_bytes, held, tree = (
        _disk.MAX_ENTRIES, _disk.Unmeasurable, _disk.cgroup_procs, _disk.deleted_open_bytes, _disk.disk_bytes,
        _disk.held, _disk.tree)


def floor_bytes(size: int) -> int:
    """The machine's free space a cage never takes: 2 % of the filesystem, at least 1 GB, at most 20 GB."""
    return max(1024 * MB, min(20 * 1024 * MB, size // 50))


class Guard:
    """The disk guard of one command or attempt (see the module's text). check() → "" or why it must stop."""

    def __init__(self, path, budget_mb: int = 0, measure=None, base: int | None = None, hold=None, grown0: int = 0):
        st = os.statvfs(path)
        self.path, self.measure, self.budget, self.hold = str(path), measure, int(budget_mb) * MB, hold
        free = st.f_bavail * st.f_frsize
        self.floor = min(floor_bytes(st.f_blocks * st.f_frsize), free // 2)
        self.ifloor = min(st.f_files // 100, st.f_favail // 2) if st.f_files else 0
        self.ref, self.left, self.last = free, self.budget - max(0, int(grown0)), 0.0
        self.base = base if base is not None or not (self.budget and measure) else self._size(measure())[0]
        self.grown = max(0, int(grown0))
        self.clean = (free, self.grown)          # C700: (free, grown) at the last measure without hidden files

    @staticmethod
    def _size(m) -> tuple[int, int]:
        return (int(m[0]), int(m[1])) if isinstance(m, tuple) else (int(m), 0)

    def check(self) -> str:
        st = os.statvfs(self.path)
        free = st.f_bavail * st.f_frsize
        if free < self.floor:
            return (f"stopped: the machine's disk has {free // MB} MB free, under the floor of {self.floor // MB} MB "
                    "a command may not take (C688)")
        if self.ifloor and st.f_favail < self.ifloor:
            return f"stopped: the machine's disk has {st.f_favail} free inodes, under the floor of {self.ifloor} (C688)"
        if not self.budget or self.ref - free <= self.left:
            return ""
        now = time.monotonic()
        if now - self.last < CONFIRM_S:
            return ""
        self.last = now
        thaw = self.hold() if self.hold else None      # frozen while it is measured: no writes meanwhile
        try:                                           # O1: thawed whatever happens, unless it is stopped now
            try:
                size, hidden = self._size(self.measure())
            except Unmeasurable as e:
                thaw = None                            # stopped: left frozen until it is killed
                return f"stopped: the project's size cannot be measured ({e})"
            grown, note = size - self.base, ""
            if hidden:                                 # C700: deleted while mapped, their size unreadable here
                lost = self.clean[1] + (self.clean[0] - free)
                if lost > grown:
                    grown, note = lost, (f" ({hidden} holder(s) of files no folder lists — deleted while mapped, "
                                         "a socket that can carry descriptors, or a process whose descriptors "
                                         "cannot be read (C710): their size cannot be read without "
                                         "privileges, so the free space the disk lost meanwhile counts)")
            else:
                self.clean = (free, grown)
            self.grown = grown
            if grown > self.budget:
                thaw = None
                return f"stopped: the project grew by {grown / MB:.1f} MB > {self.budget // MB} MB{note} (C688, C700)"
            self.ref, self.left = free, self.budget - grown
            return ""
        finally:
            if thaw:
                thaw()


def hold(pid: int, cg: Path | None = None):
    """Freeze `pid`'s whole tree (its cgroup's cgroup.freeze, else SIGSTOP to each process, twice: a child born
    meanwhile too); the function that thaws it."""
    if cg is not None:
        try:
            (cg / "cgroup.freeze").write_text("1")
            for _ in range(50):                        # frozen when cgroup.events says so (a few ms)
                if "frozen 1" in (cg / "cgroup.events").read_text():
                    break
                time.sleep(0.002)
            return lambda: (cg / "cgroup.freeze").write_text("0")
        except OSError:
            pass
    stopped: set[int] = set()

    def stop(p: int) -> None:
        if p not in stopped:
            try:
                os.kill(p, signal.SIGSTOP)
                stopped.add(p)
            except OSError:
                pass
    for _ in range(2):
        tree(pid, stop)

    def thaw() -> None:
        for p in stopped:
            try:
                os.kill(p, signal.SIGCONT)
            except OSError:
                pass
    return thaw


# ---- the script in front of bwrap -------------------------------------------------------------------------------
def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _end(d: Path, remove: bool = True) -> None:
    try:
        (d / "cgroup.kill").write_text("1")
    except OSError:
        pass
    for _ in range(100):
        try:
            if not (d / "cgroup.procs").read_text().split():
                break
        except OSError:
            break
        time.sleep(0.02)
    if remove:
        try:
            d.rmdir()
        except OSError:
            pass


def _cgroup(base: Path, conf: dict) -> Path | None:
    """The cage's own cgroup under the delegated one (the stale ones of cages killed with their script removed)."""
    for old in base.glob(PREFIX + "*"):
        try:
            if not _alive(int(old.name.split("-")[1])):
                _end(old)
        except (ValueError, IndexError):
            pass
    d = base / f"{PREFIX}{os.getpid()}-{secrets.token_hex(4)}"
    try:
        d.mkdir()
        (d / "memory.max").write_text(str(int(conf["mem_mb"]) * MB))
        (d / "pids.max").write_text(str(int(conf["tasks"])))
        for f, v in (("memory.swap.max", "0"), ("memory.oom.group", "1")):
            if (d / f).exists():
                (d / f).write_text(v)
        return d
    except OSError as e:
        sys.stderr.write(f"aurora: no cgroup of its own for the cage ({e}): the rlimits only\n")
        _end(d)
        return None


def _oom(d: Path) -> int:
    try:
        for line in (d / "memory.events").read_text().splitlines():
            k, _, v = line.partition(" ")
            if k == "oom_kill":
                return int(v)
    except (OSError, ValueError):
        pass
    return 0


def _pdeathsig() -> None:
    try:
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0)      # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass


def _measure(root: Path, pid: int, cg: Path | None) -> tuple[int, int]:
    """The project's exact size and the files the cage deleted but holds (C700: its cgroup's processes too)."""
    b, hidden = held([*tree(pid), *cgroup_procs(cg)], root)
    return disk_bytes(root) + b, hidden


def _main(argv: list[str]) -> int:
    import resource
    conf, cmd = json.loads(argv[1]), argv[2:]
    resource.setrlimit(resource.RLIMIT_CORE, (1, 1))
    if conf.get("file_mb"):
        b = int(conf["file_mb"]) * MB
        resource.setrlimit(resource.RLIMIT_FSIZE, (b, b))
    cg = _cgroup(Path(conf["cg"]), conf) if conf.get("cg") else None
    if cg is None and conf.get("as_mb"):
        b = int(conf["as_mb"]) * MB
        resource.setrlimit(resource.RLIMIT_AS, (b, b))
        # C702: per process only — N processes, /tmp and /dev/shm in memory, memfd, SysV segments add up: said, never
        # presented as a ceiling (the kernel's is the cgroup's, where the API's unit delegates one)
        sys.stderr.write(f"aurora: no memory ceiling for the command as a whole here (no delegated cgroup): each "
                         f"process at most {conf['as_mb']} MB of address space, {conf.get('tasks')} processes (C702)\n")
        sys.stderr.flush()
    guard = None
    if conf.get("watch"):
        root = Path(conf["watch"])
        budget = int(conf.get("disk_mb") or 0)
        try:                                        # the base before the cage starts: nothing of it is open yet
            guard = Guard(root, budget, measure=lambda: _measure(root, child, cg),
                          base=disk_bytes(root) if budget else 0, hold=lambda: hold(child, cg))
        except Unmeasurable as e:
            sys.stderr.write(f"aurora: stopped before it started: the project's size cannot be measured ({e})\n")
            return DISK_STOP
        except OSError:
            guard = None
    if cg is None and guard is None:
        os.execvp(cmd[0], cmd)                      # nothing to watch: the cage itself, this process's limits
    me = os.getpid()
    child = os.fork()
    if child == 0:
        try:
            _pdeathsig()
            if os.getppid() != me:
                os._exit(1)
            if cg is not None:
                try:
                    (cg / "cgroup.procs").write_text(str(os.getpid()))
                except OSError:
                    os._exit(JOIN_FAILED)
            os.execvp(cmd[0], cmd)
        except BaseException:  # noqa: BLE001
            os._exit(127)
    def forward(n, _f) -> None:
        try:
            os.kill(child, n)
        except OSError:
            pass
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, forward)
    why, status = "", 0
    while True:
        r, status = os.waitpid(child, os.WNOHANG)
        if r:
            break
        if guard is not None:
            try:
                why = guard.check()
            except OSError:
                why = ""
            if why:
                if cg is not None:
                    _end(cg, remove=False)
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _r, status = os.waitpid(child, 0)
                break
        time.sleep(EVERY_S if guard is not None and guard.budget else FLOOR_EVERY_S)
    oom = 0
    if cg is not None:
        _end(cg, remove=False)
        oom = _oom(cg)
        _end(cg)
    if why:
        sys.stderr.write(f"\naurora: {why}\n")
        return DISK_STOP
    if oom:
        sys.stderr.write(f"\naurora: stopped: the command passed its memory limit ({conf.get('mem_mb')} MB; the "
                         "kernel's, its cgroup)\n")
    if os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        if sig in (signal.SIGKILL, signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            if sig != signal.SIGKILL:
                signal.signal(sig, signal.SIG_DFL)
            sys.stderr.flush()
            os.kill(me, sig)
        return 128 + sig
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
