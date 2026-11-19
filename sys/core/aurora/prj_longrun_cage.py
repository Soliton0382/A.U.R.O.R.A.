# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""⏳ The long runs' cage and files (ROADMAP N145; second review, 20 Nov: C625–C631): what prj_longrun needs that a run
must not be able to turn against Aurora.

  - files of the project opened without following a link anywhere on the path (openat, O_NOFOLLOW at each step): the
    run's progress line, the outputs hashed, the manifest and the report (C625: a link named MANIFEST.txt made Aurora
    overwrite her own shadow ledger; a link named PROGRESS made her read a file outside the project);
  - the run's own usage summed over its whole process tree, read from /proc each poll (C626: ulimit -t / -v counted
    per process: six children used six times the CPU declared); this machine has no per-run cgroup for the services'
    account (no user manager: aurora is not «lingering»), so CPU and memory are checked by Aurora once a second, and the
    per-process ulimit stays as a hard stop for a single process; the number of processes is a hard limit (ulimit -u
    counts in the cage's own user namespace, measured: 38 forks with -u 40), the cage's /tmp a tmpfs of the memory
    declared (bwrap --size);
  - the project's size measured without skipping any folder (C627: node_modules, __pycache__ were not counted);
  - the code frozen with a run hashed again before every resume (C628: a resume ran the code the agent changed).
"""
from __future__ import annotations

import glob
import hashlib
import os
import shlex
import threading
from pathlib import Path

from . import prj_run, sys_config

TASKS_MAX = 512                  # processes of one run at once (ulimit -u in its user namespace, and counted)
CLK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


# ---- files of the project, never through a link -------------------------------------------------------------------
# moved to prj_safeio (C643): the same opener serves the project tools and the projects plugin
from .prj_safeio import open_in, read_small, sha_in, write_new  # noqa: E402,F401
from .prj_safeio import parts as _parts  # noqa: E402,F401


# ---- the project's size, nothing skipped: prj_run_box (C688: the folders' own blocks counted too, a cap on entries)
from .prj_run_box import Unmeasurable, deleted_open_bytes, disk_bytes  # noqa: E402,F401


# ---- the run's usage over its whole process tree ------------------------------------------------------------------
def _stat(pid: str) -> tuple[int, float] | None:
    """(ppid, CPU seconds of the process and of its children it has waited for) from /proc/<pid>/stat."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    f = raw[raw.rfind(")") + 2:].split()             # after the command's name, which may hold spaces
    return int(f[1]), sum(int(x) for x in f[11:15]) / CLK   # utime, stime, cutime, cstime


def usage(pid: int) -> dict:
    """{"cpu_s", "rss_mb", "tasks", "pids"} of `pid` and every process below it (the cage's whole tree, C626)."""
    parent: dict[int, int] = {}
    cpu: dict[int, float] = {}
    for d in os.listdir("/proc"):
        if d.isdigit() and (s := _stat(d)):
            parent[int(d)], cpu[int(d)] = s
    tree, todo = set(), [pid]
    kids: dict[int, list[int]] = {}
    for p, pp in parent.items():
        kids.setdefault(pp, []).append(p)
    while todo:
        p = todo.pop()
        if p in tree or p not in parent:
            continue
        tree.add(p)
        todo += kids.get(p, [])
    rss = 0
    for p in tree:
        try:
            rss += int(Path(f"/proc/{p}/statm").read_text().split()[1]) * PAGE
        except (OSError, IndexError, ValueError):
            pass
    return {"cpu_s": round(sum(cpu[p] for p in tree), 2), "rss_mb": round(rss / (1024 * 1024), 1), "tasks": len(tree),
            "pids": sorted(tree)}


# ---- the cage's command --------------------------------------------------------------------------------------------
def wrapped(st: dict) -> str:
    """The run's command inside its shell limits: per process CPU and memory (a hard stop for one process; the run's
    total is Aurora's, usage()), the processes (its user namespace), each file at most the disk declared
    (no core dumps: the entry's RLIMIT_CORE 1).
    No address-space limit with the GPU (CUDA reserves far more than it uses)."""
    lim = st["limits"]
    mem = "" if lim.get("gpu") else f"ulimit -v {int(lim['mem_mb']) * 1024} || exit 97; "
    return (f"ulimit -S -t {int(lim['cpu_s'])} || exit 97; ulimit -H -t {int(lim['cpu_s']) + 5} || exit 97; {mem}"
            f"ulimit -u {TASKS_MAX} || exit 97; ulimit -f {int(lim['disk_mb']) * 1024} || exit 97; "
            f"exec bash -c {shlex.quote(st['command'])}")   # core dumps: RLIMIT_CORE 1 (prj_longrun_meter, C654-core)


def argv(cfg: sys_config.Config, root: Path, st: dict, work: str) -> list[str]:
    """prj_run's cage for this run: /tmp a tmpfs of the memory declared, its environment and, with the GPU, the GPU's
    device files."""
    from . import prj_run_box as B
    box = {**B.profile("longrun"), "file_mb": int(st["limits"]["disk_mb"])}    # its meter and its guard do the rest
    args = prj_run.cage(cfg, root, wrapped(st), tmp_mb=int(st["limits"]["mem_mb"]), box=box)
    at = args.index("--chdir")
    env = {"LONGRUN_ID": st["id"], "LONGRUN_ATTEMPT": str(st["attempts"]),
           "LONGRUN_RESUMED": "1" if st["attempts"] > 1 else "0",
           "LONGRUN_CHECKPOINT": str(root / work / st["id"])}
    extra = [a for k, v in env.items() for a in ("--setenv", k, v)]
    args[at:at] = extra
    if st["limits"].get("gpu"):                      # mount points in /dev: before it is made read only (O1)
        at = args.index("--remount-ro")
        args[at:at] = [a for d in sorted(glob.glob("/dev/nvidia*")) for a in ("--dev-bind", d, d)]
    return args


# ---- the code frozen with a run ----------------------------------------------------------------------------------
MAX_CODE_FILES = 64              # O6: the code files named with a run, and their bytes together (hashed in the API)
MAX_CODE_MB = 64


def code_state(root: Path, files: list, command: str) -> dict:
    """{"code": {rel: sha256}, "command_sha256"} of the code files named with a run (ValueError for a missing one,
    more than MAX_CODE_FILES, or more than MAX_CODE_MB together)."""
    files = list(files or [])
    if len(files) > MAX_CODE_FILES:
        raise ValueError(f"at most {MAX_CODE_FILES} code files")
    total = 0
    for rel in files:
        try:
            fd = open_in(root, "/".join(_parts(str(rel))), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        except (OSError, ValueError) as e:
            raise ValueError(f"{rel}: not a plain file of the project ({e})") from None
        try:
            total += os.fstat(fd).st_size
        finally:
            os.close(fd)
    if total > MAX_CODE_MB * 1024 * 1024:
        raise ValueError(f"the code files are {total // (1024 * 1024)} MB together: at most {MAX_CODE_MB} MB")
    code = {}
    for rel in files:
        rel = "/".join(_parts(str(rel)))
        code[rel] = sha_in(root, rel)
    return {"code": code, "command_sha256": hashlib.sha256(command.encode()).hexdigest()}


def code_changed(root: Path, st: dict) -> list[str]:
    """The frozen code files changed or gone since the start, and «the command» if its hash differs (C628)."""
    out = []
    for rel, h in (st.get("code") or {}).items():
        try:
            if sha_in(root, rel) != h:
                out.append(rel)
        except ValueError:
            out.append(rel)
    if st.get("command_sha256") and hashlib.sha256(st["command"].encode()).hexdigest() != st["command_sha256"]:
        out.append("the command")
    return out


# ---- the limits (prj_longrun's) --------------------------------------------------------------------------------------------------
def limits(cfg: sys_config.Config, a: dict) -> dict:
    """The declared limits, each one required (wall_s, mem_mb, disk_mb) or defaulted (cpu_s: the wall time), within the
    machine's ceilings; ValueError said as REFUSED."""
    def num(k):
        try:
            v = int(a.get(k))
        except (TypeError, ValueError):
            raise ValueError(f"declare {k} first (a whole number)") from None
        if v <= 0:
            raise ValueError(f"{k}: more than 0")
        return v
    lim = {"wall_s": num("wall_s"), "mem_mb": num("mem_mb"), "disk_mb": num("disk_mb")}
    lim["cpu_s"] = num("cpu_s") if a.get("cpu_s") not in (None, "") else lim["wall_s"]
    lim["gpu"] = bool(a.get("gpu"))
    top = {"wall_s": int(cfg["AURORA_LONGRUN_MAX_HOURS"]) * 3600, "mem_mb": int(cfg["AURORA_LONGRUN_MAX_MEM_MB"]),
           "disk_mb": int(cfg["AURORA_LONGRUN_MAX_DISK_MB"])}
    top["cpu_s"] = top["wall_s"] * max(1, os.cpu_count() or 1)
    over = [f"{k} {lim[k]} > {v}" for k, v in top.items() if lim[k] > v]
    if over:
        raise ValueError("beyond the machine's ceilings (AURORA_LONGRUN_MAX_*): " + ", ".join(over))
    return lim


def _patterns(outputs) -> list[str]:
    out = []
    for p in outputs or []:
        p = str(p or "").strip()
        if not p or p.startswith("/") or ".." in Path(p).parts or ".git" in Path(p).parts:
            raise ValueError(f"{p!r}: a pattern relative to the project, without .. or .git")
        out.append(p)
    if len(out) > 20:
        raise ValueError("at most 20 output patterns")
    return out


# ---- the disk, watched between the supervisor's looks (C688) -----------------------------------------------------
class DiskWatch(threading.Thread):
    """prj_run_box.Guard every EVERY_S on the project's filesystem, from before the cage starts (C688: measured every
    15 s, 100 processes × 10 MB wrote 954 MB on disk_mb 10 before the stop). On a stop: `why` set and the cage's
    process group killed at once (its supervisor ends the rest, the cgroup too)."""

    def __init__(self, root: Path, budget_mb: int, base: int):
        from . import prj_run_box as B
        super().__init__(name="longrun-disk", daemon=True)
        self.pids: list[int] = []                    # the run's processes, from the supervisor's last look
        self.proc = None
        self.why = ""
        self.done = threading.Event()
        self.every = B.EVERY_S
        self.meter = None
        try:                                         # C700: what earlier attempts left counts from the start
            grown0 = disk_bytes(root) - base if budget_mb else 0
        except B.Unmeasurable:
            grown0 = 0                               # its first exact measure stops it
        self.guard = B.Guard(root, budget_mb, measure=lambda: self.measure(root), base=base, grown0=grown0,
                             hold=lambda: B.hold(self.proc.pid, getattr(self.meter, "dir", None)))

    def measure(self, root: Path) -> tuple[int, int]:
        """C700: the processes read again now (the supervisor's list is up to 15 s old), its cgroup's too."""
        from . import prj_run_box as B
        pids = set(self.pids)
        if self.proc is not None:
            pids.update(B.tree(self.proc.pid))
        pids.update(B.cgroup_procs(getattr(self.meter, "dir", None)))
        b, hidden = B.held(pids, root)
        return disk_bytes(root) + b, hidden

    def run(self) -> None:
        import signal
        while not self.done.wait(self.every):
            try:
                why = self.guard.check()
            except OSError:
                continue
            if why:
                self.why = why
                if self.proc is not None:
                    try:
                        os.killpg(self.proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                return


# ---- the outputs' patterns, matched inside the project only (C689) ------------------------------------------------
MAX_VISIT = 200_000              # entries looked at to match the patterns, all patterns together
_MAGIC = set("*?[")


def _seg_match(segs: list[str], parts: list[str]) -> bool:
    """`parts` (a path's components) matched by the pattern's `segs`: «**» any number of folders, else fnmatch on one
    component (never across a «/»). The greedy wildcard match with a return to the last «**»: O(len·len), never
    exponential (a pattern of many «**» on a deep path)."""
    from fnmatch import fnmatchcase
    i = j = 0
    star, mark = -1, 0
    while j < len(parts):
        if i < len(segs) and segs[i] == "**":
            star, mark, i = i, j, i + 1
        elif i < len(segs) and fnmatchcase(parts[j], segs[i]):
            i, j = i + 1, j + 1
        elif star >= 0:
            mark += 1
            i, j = star + 1, mark
        else:
            return False
    while i < len(segs) and segs[i] == "**":
        i += 1
    return i == len(segs)


def _walk_files(root: Path, top: list[str], cap: int):
    """(rel, kind) of what is under root/top, streamed (no folder listed whole, then sorted: a folder of millions of
    names), never through a link (openat O_NOFOLLOW at each step, prj_safeio), `cap` entries at most. kind: "f" a
    regular file, "l" a link, "o" anything else. Raises OSError/ValueError when `top` is not a real folder."""
    import stat
    from . import prj_safeio as S
    fd = S._dir_fd(root, top, False)
    seen = 0
    stack = [(fd, "/".join(top) + "/" if top else "")]
    try:
        while stack:
            dfd, pre = stack.pop()
            try:
                with os.scandir(dfd) as it:
                    for e in it:
                        seen += 1
                        if seen > cap:
                            yield None, "cap"
                            return
                        try:
                            st = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        rel = pre + e.name
                        if stat.S_ISDIR(st.st_mode):
                            try:
                                nfd = os.open(e.name, os.O_RDONLY | S._DIR | S._NOFOLLOW | S._CLOEXEC, dir_fd=dfd)
                            except OSError:
                                continue
                            stack.append((nfd, rel + "/"))
                        else:
                            yield rel, "f" if stat.S_ISREG(st.st_mode) else "l" if stat.S_ISLNK(st.st_mode) else "o"
            finally:
                os.close(dfd)
    finally:
        for dfd, _p in stack:
            os.close(dfd)


def match_outputs(root: Path, pats: list[str], cap: int = MAX_VISIT) -> tuple[set[str], list[str], bool]:
    """(the regular files the patterns match, the patterns refused, capped). C689: Path.glob followed the links a run
    planted — a link to / with a deep pattern kept finish() scanning for ever, and «N names skipped» said which files
    exist outside the project. Here: one walk of the project (prj_safeio's openat, no link ever entered), at most `cap`
    entries for all the patterns together; a pattern whose fixed folders go through a link (or are not folders) is
    refused, and a link the walk meets is neither followed nor counted."""
    from . import prj_safeio as S
    files: set[str] = set()
    refused: list[str] = []
    wanted = []
    for pat in pats:
        segs = [x for x in pat.split("/") if x not in ("", ".")]
        fixed = []
        for x in segs[:-1]:
            if _MAGIC & set(x) or x == "**":
                break
            fixed.append(x)
        try:                                         # the fixed folders: real folders of the project, no link
            os.close(S._dir_fd(root, fixed, False))
        except FileNotFoundError:
            continue                                 # nothing there: nothing to match
        except (OSError, ValueError):
            refused.append(pat)
            continue
        wanted.append(segs)
    if not wanted:
        return files, refused, False
    capped = False
    for rel, kind in _walk_files(root, [], cap):
        if kind == "cap":
            capped = True
            break
        if kind == "f":
            parts = rel.split("/")
            if any(_seg_match(segs, parts) for segs in wanted):
                files.add(rel)
    return files, refused, capped


MAX_OUTPUTS = 500


def _prereg():
    from . import prj_prereg                         # here: it imports prj_run, as this module does
    return prj_prereg


def outputs(root: Path, st: dict) -> tuple[dict[str, str], int]:
    """({path: sha256}, names skipped) of the declared patterns, else of the files the run wrote — never prereg/,
    reviews/, longrun/…, never through a link, never a name holding a line break (C625)."""
    files: set[str] = set()
    if st.get("outputs"):                           # C689: inside the project only, no link followed, capped
        files, refused, capped = match_outputs(root, st["outputs"])
        st["outputs_refused"], st["outputs_capped"] = refused, capped
    else:
        t = float(st.get("t") or 0)
        for rel, v in prj_run.snapshot(root).items():
            if max(v[0], v[2]) / 1e9 >= t:              # the ctime too: an mtime set back is no way out (C649)
                files.add(rel)
    files = {f for f in files if not _prereg().locked(f) and not f.endswith("/.keep")}
    odd = {f for f in files if any(c in f for c in "\n\r\0")}
    out = {}
    for f in sorted(files - odd)[:MAX_OUTPUTS]:
        try:
            out[f] = sha_in(root, f)
        except ValueError:
            odd.add(f)
    return out, len(odd)


def pump(src, log: Path, over, limit: int) -> None:
    """The run's output copied to its log by Aurora, at most `limit` bytes (C631: the log grew by gigabytes between two
    looks); the rest read and dropped, `over` set."""
    with open(log, "ab") as fh:
        size = fh.tell()
        for chunk in iter(lambda: src.read(65536), b""):
            if size < limit:
                part = chunk[: limit - size]
                fh.write(part)
                fh.flush()
                size += len(part)
            if size >= limit and not over.is_set():
                over.set()
