# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The bench's guards (N152 §13.1): never next to the owner's real session.

- refuse to start if the runtime dir, the session bus or the Wayland display are the real ones;
- list /run/user/<uid>/ before and after every test: the same set of Wayland sockets is required;
- no bench process may hold a file under /dev/input;
- bench processes are stopped by their saved PID only (never a pattern match).
"""
import os
import signal
import stat
import subprocess
import time
from pathlib import Path


class BenchRefused(RuntimeError):
    """The bench would touch the real session: stop, never fall back."""


def real_runtime_dir() -> Path:
    return Path(f"/run/user/{os.getuid()}")


def _under(path: str, top: Path) -> bool:
    try:
        p = Path(path).resolve()
    except OSError:
        return True                                   # unknown: treated as the real one
    return p == top or top in p.parents


def check_env(env: dict) -> None:
    """Raise BenchRefused if env points at the owner's runtime dir, bus or display."""
    real = real_runtime_dir()
    rt = env.get("XDG_RUNTIME_DIR", "")
    if not rt or _under(rt, real):
        raise BenchRefused(f"XDG_RUNTIME_DIR is the real one or empty: {rt!r}")
    st = os.stat(rt)
    if stat.S_IMODE(st.st_mode) != 0o700 or st.st_uid != os.getuid():
        raise BenchRefused(f"bench runtime dir is not 0700 and ours: {oct(st.st_mode)}")
    bus = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    if str(real) in bus or "/run/user/" in bus:
        raise BenchRefused(f"session bus is the real one: {bus!r}")
    wd = env.get("WAYLAND_DISPLAY", "")
    if wd and (wd.startswith("/") and _under(wd, real)):
        raise BenchRefused(f"WAYLAND_DISPLAY points at the real runtime dir: {wd!r}")
    if wd in ("wayland-0",):
        raise BenchRefused("WAYLAND_DISPLAY is wayland-0, the owner's socket name")
    if env.get("DISPLAY") or env.get("XAUTHORITY"):
        raise BenchRefused("an X11 DISPLAY is set: the bench never speaks to Xwayland")
    if env.get("WAYLAND_SOCKET"):
        raise BenchRefused("WAYLAND_SOCKET is set")
    # the system bus is cut off: the virtual KWin's screen locker otherwise reads (and may set) the lock state of the
    # owner's real logind session, and module-rt would ask rtkit (seen on the first start, 24 Nov)
    sysbus = env.get("DBUS_SYSTEM_BUS_ADDRESS", "")
    want = f"unix:path={rt}/no-system-bus"
    if sysbus != want or os.path.exists(f"{rt}/no-system-bus"):
        raise BenchRefused(f"DBUS_SYSTEM_BUS_ADDRESS must be the bench's dead end {want!r}, not {sysbus!r}")


def real_sockets() -> dict:
    """Read-only listing of the real runtime dir: names, and the Wayland sockets among them."""
    real = real_runtime_dir()
    names = sorted(os.listdir(real)) if real.is_dir() else []
    wl = sorted(n for n in names if n.startswith("wayland-") and not n.endswith(".lock")
                and stat.S_ISSOCK(os.lstat(real / n).st_mode))
    return {"names": names, "wayland": wl}


def same_real(before: dict, after: dict) -> bool:
    return before["wayland"] == after["wayland"]


def dev_input_holders(pids, unreadable: list = None) -> list:
    """(pid, path) for every open file under /dev/input held by the given processes.

    A process that made itself non-dumpable (kwin_wayland does) has a root-owned /proc/<pid>/fd: without root it
    cannot be read; its PID goes to `unreadable` so the report says so instead of passing in silence."""
    out = []
    for pid in pids:
        fd_dir = Path(f"/proc/{pid}/fd")
        try:
            fds = list(fd_dir.iterdir())
        except PermissionError:
            if unreadable is not None:
                unreadable.append(pid)
            continue
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("/dev/input"):
                out.append((pid, target))
    return out


def gpu_holders(pids, unreadable: list = None) -> list:
    """(pid, path) for open GPU devices (/dev/dri, /dev/nvidia*) held by the given processes."""
    out = []
    for pid in pids:
        try:
            fds = list(Path(f"/proc/{pid}/fd").iterdir())
        except PermissionError:
            if unreadable is not None:
                unreadable.append(pid)
            continue
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("/dev/dri") or target.startswith("/dev/nvidia"):
                out.append((pid, target))
    return out


def nvidia_pids() -> list:
    """PIDs that nvidia-smi lists as using an NVIDIA GPU (compute or graphics); [] if nvidia-smi is absent."""
    try:
        out = subprocess.run(["/usr/bin/nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=20, env={"PATH": "/usr/bin:/bin"}).stdout
        full = subprocess.run(["/usr/bin/nvidia-smi"], capture_output=True, text=True, timeout=20,
                              env={"PATH": "/usr/bin:/bin"}).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = {int(x) for x in out.split() if x.strip().isdigit()}
    for line in full.splitlines():
        parts = line.replace("|", " ").split()
        if len(parts) > 4 and parts[3] in ("G", "C", "C+G") and parts[4].isdigit():
            pids.add(int(parts[4]))
    return sorted(pids)


def system_bus_clients(pids) -> list:
    """PIDs among pids holding a unix socket connected to the real system bus (read with ss, no root)."""
    try:
        out = subprocess.run(["/usr/bin/ss", "-xpn"], capture_output=True, text=True, timeout=10,
                             env={"PATH": "/usr/bin:/bin", "LANG": "C"}).stdout
    except (OSError, subprocess.SubprocessError):
        return [-1]                                   # unknown: reported as a failure of the check
    want = {str(p) for p in pids}
    rows = [ln.split() for ln in out.splitlines() if ln.startswith("u_")]
    # the server side carries the path; its peer inode is the client's socket
    peers = {r[7] for r in rows if len(r) > 7 and r[4] == "/run/dbus/system_bus_socket"}
    hit = set()
    for r in rows:
        if len(r) > 8 and r[5] in peers:
            for part in " ".join(r[8:]).split("pid=")[1:]:
                pid = part.split(",")[0]
                if pid in want:
                    hit.add(int(pid))
    return sorted(hit)


def descendants(pid: int) -> list:
    """Every live descendant of pid, read from /proc (children files)."""
    out, todo = [], [pid]
    while todo:
        p = todo.pop()
        try:
            tasks = os.listdir(f"/proc/{p}/task")
        except OSError:
            continue
        for t in tasks:
            try:
                kids = Path(f"/proc/{p}/task/{t}/children").read_text().split()
            except OSError:
                continue
            for k in kids:
                k = int(k)
                if k not in out:
                    out.append(k)
                    todo.append(k)
    return out


class Procs:
    """The bench's processes, by saved PID. stop() signals only these PIDs."""

    def __init__(self, log):
        self.log = log
        self.items = []                               # (name, Popen)

    def start(self, name: str, argv: list, env: dict, **kw) -> subprocess.Popen:
        check_env(env)
        p = subprocess.Popen(argv, env=env, close_fds=True, **kw)
        self.items.append((name, p))
        self.log(f"start {name} pid={p.pid} argv={argv[0]}")
        return p

    def pids(self) -> list:
        out = []
        for _, p in self.items:
            if p.poll() is None:
                out.append(p.pid)
                out += descendants(p.pid)
        return out

    def stop_one(self, p: subprocess.Popen, grace: float = 3.0) -> None:
        if p.poll() is not None:
            return
        try:
            os.kill(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        t0 = time.monotonic()
        while p.poll() is None and time.monotonic() - t0 < grace:
            time.sleep(0.05)
        if p.poll() is None:
            os.kill(p.pid, signal.SIGKILL)
            p.wait()

    def stop(self) -> None:
        for name, p in reversed(self.items):
            self.stop_one(p)
            self.log(f"stop {name} pid={p.pid} rc={p.returncode}")
        self.items = []
