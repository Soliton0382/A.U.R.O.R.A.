# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""⏳ The whole long run's CPU, memory and processes (C654, third review of N145, 20 Nov): the CPU «of the whole run»
was summed from /proc over its live processes, and a parent that ignores SIGCHLD has its children reaped by the
kernel — their time reaches no parent: 12 children of 0.5 s used 6.0 s and the sum read 0.46 s (0.48 s polling ten
times a second); a subreaper's RUSAGE_CHILDREN saw 0.02 s of it (measured: the kernel reaps them before any wait).

The best of three ways this machine allows (Meter.mode):
  - "cgroup": the API's unit delegates its cgroup (Delegate=cpu memory pids, ProtectControlGroups=private): the API
    moves itself into the leaf `main` once, and each attempt runs in a cgroup of its own, joined before bwrap starts
    (the cage's cgroup namespace has it as its root, and the kernel refuses a write to a namespace root's limits from
    inside). The kernel's hard limits: memory.max (the run's memory, its /tmp RAM disk included; memory.oom.group: the
    run ends whole), memory.swap.max 0, pids.max. The CPU: cpu.stat usage_usec, every process that ever ran in it
    whoever reaped it, and the run ended (cgroup.kill) once it passes cpu_s. cpu.max is a rate (cores), not a total of
    seconds: it cannot be the limit of a budget, and is left alone.
  - "ledger": no delegation (this machine today): the service's own cgroup counts every process of the service, reaped
    or not (cpu.stat, readable by its processes). What it counted beyond what its living and zombie processes hold (in
    their own time and their waited children's) was reaped unseen: that CPU is charged to the run, on top of its tree.
    An upper bound: CPU lost by any other process of the service is charged too (a stop too early, never one missed);
    counted only when two readings in a row agree (a process reaped between the reads of its parent and its own shows
    once). The hard limits stay the shell's (ulimit -t per process, -u processes) and the wall time.
  - "proc": no cgroup v2 at all (another system): the /proc sum of before, which misses what the kernel reaps.
"""
from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

CG = Path("/sys/fs/cgroup")
SUB = "main"                                   # the API's own leaf in a delegated cgroup
CONTROLLERS = ("cpu", "memory", "pids")
PREFIX = "longrun-"
JOIN_FAILED = 96                               # the entry's exit code when the run's cgroup could not be joined
CLK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
NCPU = max(1, os.cpu_count() or 1)
LOG = logging.getLogger("aurora.longrun")
ENTRY = ("import os, resource, sys\n"
         "resource.setrlimit(resource.RLIMIT_CORE, (1, 1))\n"
         "if sys.argv[1]:\n"
         "    try:\n"
         "        open(sys.argv[1], 'w').write(str(os.getpid()))\n"
         "    except OSError:\n"
         f"        os._exit({JOIN_FAILED})\n"
         "os.execvp(sys.argv[2], sys.argv[2:])\n")

_lock = threading.Lock()
_root: list = []                               # [Path | None]: the delegated cgroup, decided once per process


# ---- where this process lives ----------------------------------------------------------------------------------
def own() -> str | None:
    """This process's cgroup v2 path ("/" in a private cgroup namespace), None without cgroup v2."""
    try:
        for line in Path("/proc/self/cgroup").read_text().splitlines():
            if line.startswith("0::"):
                return line[3:].strip() or "/"
    except OSError:
        pass
    return None


def _dir(rel: str) -> Path:
    return CG / rel.lstrip("/")


def _read(d: Path, name: str) -> str:
    try:
        return (d / name).read_text()
    except OSError:
        return ""


def _key(text: str, key: str) -> int | None:
    for line in text.splitlines():
        k, _, v = line.partition(" ")
        if k == key and v.strip().isdigit():
            return int(v)
    return None


def cpu_usec(d: Path) -> int | None:
    return _key(_read(d, "cpu.stat"), "usage_usec")


def _ours(d: Path) -> bool:
    """A cgroup systemd delegated to us: ours, its processes and children ours to move and make, the controllers."""
    try:
        if d.stat().st_uid != os.geteuid():
            return False
    except OSError:
        return False
    return (set(CONTROLLERS) <= set(_read(d, "cgroup.controllers").split())
            and all(os.access(d / f, os.W_OK) for f in ("cgroup.procs", "cgroup.subtree_control")))


def delegated(force: Path | None = None) -> Path | None:
    """The cgroup systemd delegated to this service, ready for a cgroup per run (this process moved into its `main`
    leaf, the controllers on for its children), or None. Decided once per process (`force`: the tests' own)."""
    with _lock:
        if force is not None:
            return _prepare(force)
        if not _root:
            _root.append(_find())
        return _root[0]


def _find() -> Path | None:
    rel = own()
    if rel is None or not os.environ.get("INVOCATION_ID"):     # a systemd service only: never a desktop's scope
        return None
    d = _dir(rel)
    if d.name == SUB and d != CG:
        d = d.parent
    if not (d == CG or d.name.endswith(".service")) or not _ours(d):
        return None
    return _prepare(d)


def _prepare(d: Path) -> Path | None:
    leaf = d / SUB
    try:
        leaf.mkdir(exist_ok=True)
        for _ in range(50):                    # no process may stay in an inner cgroup (the kernel's rule)
            pids = _read(d, "cgroup.procs").split()
            if not pids:
                break
            for p in pids:
                try:
                    (leaf / "cgroup.procs").write_text(p)
                except ProcessLookupError:
                    pass
        on = set(_read(d, "cgroup.subtree_control").split())
        if need := [c for c in CONTROLLERS if c not in on]:
            (d / "cgroup.subtree_control").write_text(" ".join("+" + c for c in need))
    except OSError as e:
        LOG.warning("long runs: the delegated cgroup %s is not usable (%s): the service's counter instead", d, e)
        return None
    for old in [*d.glob(PREFIX + "*"), *d.glob("cage-*")]:   # an earlier API's (prj_run_box's cages too), empty
        try:
            old.rmdir()
        except OSError:
            pass
    return d


# ---- one attempt's meter ---------------------------------------------------------------------------------------
def _scan() -> dict[int, tuple[str, int, float]]:
    """{pid: (state, ppid, CPU seconds of it and of the children it waited for)} from /proc/<pid>/stat."""
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            raw = Path(f"/proc/{d}/stat").read_text()
        except OSError:
            continue
        f = raw[raw.rfind(")") + 2:].split()   # after the command's name, which may hold spaces
        out[int(d)] = (f[0], int(f[1]), sum(int(x) for x in f[11:15]) / CLK)
    return out


class Meter:
    """The CPU, memory and processes of one attempt, from before it starts (the ledger's baseline) to its end."""

    def __init__(self, lim: dict, name: str, tasks_max: int, root: Path | None = None):
        self.lim, self.tasks_max, self.dir, self.mode = lim, int(tasks_max), None, "proc"
        self.cpu, self._lost, self.oom = 0.0, [], 0
        base = root if root is not None else delegated()
        if base is not None:
            try:
                self.dir, self.mode = self._make(base, name), "cgroup"
            except OSError as e:
                LOG.warning("long runs: no cgroup of its own for %s (%s): the service's counter instead", name, e)
        rel = own()
        if self.dir is None and rel is not None and cpu_usec(_dir(rel)) is not None:
            self.mode, self.rel, self.svc = "ledger", rel, _dir(rel)
            self.u0, self.l0 = self._ledger(_scan())

    def _make(self, base: Path, name: str) -> Path:
        d = base / (PREFIX + re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:80] + f".{os.getpid()}")
        if d.exists():
            self._end(d)
        d.mkdir()
        try:
            (d / "memory.max").write_text(str(int(self.lim["mem_mb"]) * 1024 * 1024))
            (d / "pids.max").write_text(str(self.tasks_max))
            for f, v in (("memory.swap.max", "0"), ("memory.oom.group", "1")):
                if (d / f).exists():
                    (d / f).write_text(v)
        except OSError:
            d.rmdir()
            raise
        return d

    def argv(self, args: list[str]) -> list[str]:
        """The cage's command behind a small entry: RLIMIT_CORE 1 byte, soft and hard (C654-core: a run stopped by a
        limit — SIGXCPU, SIGXFSZ — left a core dump each, and the desktop showed the owner an error window for each;
        with a piped core_pattern the kernel skips the dump only at 1, at 0 systemd-coredump still records it), and
        with a cgroup of its own, the cgroup joined first (the cage's every process born in it)."""
        return [sys.executable, "-I", "-c", ENTRY, str(self.dir / "cgroup.procs") if self.mode == "cgroup" else "",
                *args]

    def _ledger(self, procs) -> tuple[float, float]:
        """(the service's counted CPU, what its processes hold), the counter read last: never less than they hold."""
        live = {int(p) for p in _read(self.svc, "cgroup.procs").split()}
        mine = "0::" + self.rel
        held = 0.0
        for p, (state, _pp, cpu) in procs.items():
            if p in live or (state == "Z" and _read(Path(f"/proc/{p}"), "cgroup").strip() == mine):
                held += cpu
        return (cpu_usec(self.svc) or 0) / 1e6, held

    def read(self, pid: int) -> dict:
        """{"cpu_s" (this attempt, never less than read before), "rss_mb", "tasks", "pids", "unseen_s", "mode"}."""
        procs = _scan()
        kids: dict[int, list[int]] = {}
        for p, (_s, pp, _c) in procs.items():
            kids.setdefault(pp, []).append(p)
        tree, todo = set(), [pid]
        while todo:
            p = todo.pop()
            if p in tree or p not in procs:
                continue
            tree.add(p)
            todo += kids.get(p, [])
        rss = 0
        for p in tree:
            try:
                rss += int(Path(f"/proc/{p}/statm").read_text().split()[1]) * PAGE
            except (OSError, IndexError, ValueError):
                pass
        tasks, unseen = len(tree), 0.0
        if self.mode == "cgroup":
            cpu = (cpu_usec(self.dir) or 0) / 1e6
            tasks = max(tasks, _key("pids.current " + _read(self.dir, "pids.current"), "pids.current") or 0)
            self.oom = _key(_read(self.dir, "memory.events"), "oom_kill") or 0
        else:
            cpu = sum(procs[p][2] for p in tree)
            if self.mode == "ledger":
                u, held = self._ledger(procs)
                self._lost = (self._lost + [(u - self.u0) - (held - self.l0)])[-2:]
                unseen = max(0.0, min(self._lost)) if len(self._lost) == 2 else 0.0
                cpu += unseen
        self.cpu = max(self.cpu, cpu)
        return {"cpu_s": round(self.cpu, 2), "rss_mb": round(rss / (1024 * 1024), 1), "tasks": tasks,
                "pids": sorted(tree), "unseen_s": round(unseen, 2), "mode": self.mode}

    def kill(self, proc: subprocess.Popen) -> None:
        """The run ended: its process group (TERM, then KILL) and, with a cgroup, every process in it."""
        for sig, wait in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                break
            try:
                proc.wait(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        if self.dir is not None:
            self._end(self.dir, remove=False)

    @staticmethod
    def _end(d: Path, remove: bool = True) -> None:
        try:
            (d / "cgroup.kill").write_text("1")
        except OSError:
            pass
        for _ in range(100):                   # 5 s at most for the killed to leave
            if not _read(d, "cgroup.procs").split():
                break
            time.sleep(0.05)
        if remove:
            try:
                d.rmdir()
            except OSError:
                pass

    def close(self) -> dict:
        """After the attempt: its own cgroup's final CPU (exact: everything that ran in it) and memory, then the
        cgroup ended and removed. {"cpu_s", "peak_mb", "oom"}."""
        out = {"cpu_s": round(self.cpu, 2), "peak_mb": None, "oom": self.oom}
        if self.dir is not None:
            self._end(self.dir, remove=False)
            cpu = cpu_usec(self.dir)
            peak = _key("peak " + _read(self.dir, "memory.peak"), "peak")
            self.oom = _key(_read(self.dir, "memory.events"), "oom_kill") or self.oom
            self.cpu = max(self.cpu, (cpu or 0) / 1e6)
            out = {"cpu_s": round(self.cpu, 2), "peak_mb": round(peak / (1024 * 1024), 1) if peak else None,
                   "oom": self.oom}
            self._end(self.dir)
            self.dir = None
        return out


def pause(poll_s: float, left_cpu_s: float) -> float:
    """The next look: sooner as the CPU left nears its end (every core busy spends it NCPU times faster)."""
    return max(0.05, min(poll_s, left_cpu_s / NCPU))
