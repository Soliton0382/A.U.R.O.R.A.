# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Start and stop the N152 phase 0 bench (§13.1), all as the calling user, nothing of the real session.

Outer side (prepare + reexec): a short 0700 runtime dir, a bench HOME, an environment built from nothing, then
`dbus-run-session` re-runs the caller inside a bus of its own. Inner side (Bench.up): AT-SPI bus, virtual KWin with
its own socket, PipeWire + WirePlumber (policy profile: no ALSA, no V4L2, no Bluetooth), xdg-desktop-portal and the
KDE backend — every process started here, by saved PID, with the bench environment only.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import guard

SOCKET = "wayland-banco"
WIDTH, HEIGHT = 1280, 800                              # chosen at start, written in the bench log
PORTAL = "/usr/libexec/xdg-desktop-portal"
PORTAL_KDE = "/usr/lib/x86_64-linux-gnu/libexec/xdg-desktop-portal-kde"
ATSPI_LAUNCHER = "/usr/libexec/at-spi-bus-launcher"
RT_PARENT = Path(f"/tmp/claude-{os.getuid()}")          # sockets need a path shorter than 108 bytes
APP_ID = "org.aurora.desk"
KWIN_SETTLE = 2.0
# KWin's screencast refuses QPainter compositing ("Unsupported compositing type", measured): OpenGL is needed, and
# the GPUs are full of Aurora's model. Mesa only (no NVIDIA EGL nor GBM backend), software rasteriser (llvmpipe /
# kms_swrast). check_gpu() verifies that no bench process holds a GPU device.
SOFTWARE_GL = {
    "KWIN_COMPOSE": "O2",
    "LIBGL_ALWAYS_SOFTWARE": "1",
    "GBM_ALWAYS_SOFTWARE": "1",
    "GBM_BACKEND": "dri",
    "__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/50_mesa.json",
    "__GLX_VENDOR_LIBRARY_NAME": "mesa",
    "MESA_LOADER_DRIVER_OVERRIDE": "kms_swrast",
}


def base_env(home: Path, rt: Path, data_dirs: str) -> dict:
    """The bench environment, built from nothing (never os.environ)."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "XDG_RUNTIME_DIR": str(rt),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_DIRS": data_dirs,
        "XDG_CONFIG_DIRS": "/etc/xdg",
        "XDG_CURRENT_DESKTOP": "KDE",
        "XDG_MENU_PREFIX": "plasma-",                  # KService indexes applications through this menu
        "XDG_SESSION_TYPE": "wayland",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GSETTINGS_BACKEND": "memory",
        "LIBGL_ALWAYS_SOFTWARE": "1",                  # GPUs are full of Aurora's model: software only
        "QT_QUICK_BACKEND": "software",
        "SAL_USE_VCLPLUGIN": "kf6",                    # LibreOffice through Qt on Wayland: its default wants X11
        "NO_AT_BRIDGE": "0",
        "DBUS_SYSTEM_BUS_ADDRESS": f"unix:path={rt}/no-system-bus",   # never the real system bus (guard)
        # every bench client too: Mesa's EGL only, never the NVIDIA vendor library (measured: without these the
        # KDE portal and GTK opened /dev/nvidia0 and /dev/nvidia1)
        "__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/50_mesa.json",
        "__GLX_VENDOR_LIBRARY_NAME": "mesa",
        "GBM_BACKEND": "dri",
        "GBM_ALWAYS_SOFTWARE": "1",
        "GSK_RENDERER": "cairo",
        "CUDA_VISIBLE_DEVICES": "",
    }


def prepare(scratch: Path) -> dict:
    """Outer side: folders and the environment for dbus-run-session. Returns the bench description."""
    scratch.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="run-", dir=scratch))
    RT_PARENT.mkdir(mode=0o700, exist_ok=True)
    rt = Path(tempfile.mkdtemp(prefix="n152rt-", dir=RT_PARENT))
    os.chmod(rt, 0o700)
    home = base / "home"
    for d in (home / ".config", home / ".local/share", home / ".local/state", home / ".cache", base / "log",
              base / "share/applications"):
        d.mkdir(parents=True, exist_ok=True)
    # the id aurora-desk would register (F2 b): a .desktop file only in the bench's XDG_DATA_DIRS
    (base / "share/applications" / f"{APP_ID}.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Aurora Desk Banco\nExec=/bin/false\nNoDisplay=true\n")
    # the virtual session must not lock itself (the greeter would cover every test window)
    (home / ".config/kscreenlockerrc").write_text(
        "[Daemon]\nAutolock=false\nLockOnResume=false\nLockOnStart=false\nTimeout=0\n")
    # PipeWire daemon of the bench: no realtime via rtkit (system bus), no X11 bell, no JACK
    pwc = base / "pwconf/pipewire.conf.d"
    pwc.mkdir(parents=True)
    shutil.copy("/usr/share/pipewire/pipewire.conf", base / "pwconf/pipewire.conf")
    (pwc / "bench.conf").write_text(
        "context.properties = {\n  module.rt = false\n  module.x11.bell = false\n"
        "  module.jackdbus-detect = false\n}\n")
    env = base_env(home, rt, f"{base / 'share'}:/usr/local/share:/usr/share")
    guard.check_env(env)
    desc = {"base": str(base), "rt": str(rt), "home": str(home), "socket": SOCKET,
            "width": WIDTH, "height": HEIGHT, "env": env}
    (base / "bench.json").write_text(json.dumps(desc, indent=1))
    return desc


def reexec_inside(desc: dict, argv: list) -> int:
    """Run argv inside dbus-run-session with the bench environment; returns its exit code."""
    env = dict(desc["env"])
    env["N152_BENCH"] = desc["base"]
    if os.environ.get("N152_KWIN_LOG"):               # debug only: Qt logging rules for the virtual KWin
        env["N152_KWIN_LOG"] = os.environ["N152_KWIN_LOG"]
    guard.check_env(env)
    cmd = ["/usr/bin/dbus-run-session", "--"] + argv
    return subprocess.call(cmd, env=env, close_fds=True)


class Bench:
    """Inner side: run inside dbus-run-session. up() starts every bench process; down() stops them by PID."""

    def __init__(self, base: Path):
        self.base = Path(base)
        self.desc = json.loads((self.base / "bench.json").read_text())
        self.env = dict(os.environ)
        guard.check_env(self.env)
        self.rt = Path(self.desc["rt"])
        self.logf = open(self.base / "log/bench.log", "a", buffering=1)
        self.procs = guard.Procs(self.log)
        self.real_before = guard.real_sockets()
        self.started = {}

    def log(self, msg: str) -> None:
        self.logf.write(f"{time.monotonic():.3f} {msg}\n")

    def out(self, name: str):
        return open(self.base / "log" / f"{name}.log", "ab")

    def wenv(self, **extra) -> dict:
        """Environment for a Wayland client of the bench."""
        e = dict(self.env)
        e.update({"WAYLAND_DISPLAY": SOCKET, "QT_QPA_PLATFORM": "wayland"})
        e.pop("N152_BENCH", None)
        e.update(extra)
        guard.check_env(e)
        return e

    def bus_names(self) -> list:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        r = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames",
                          None, GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, 2000, None)
        return list(r.unpack()[0])

    def wait_name(self, name: str, timeout: float = 20.0) -> float:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if name in self.bus_names():
                return time.monotonic() - t0
            time.sleep(0.1)
        raise TimeoutError(f"{name} never appeared on the bench bus")

    def wait_path(self, path: Path, who: str, timeout: float = 20.0) -> float:
        t0 = time.monotonic()
        while not path.exists():
            p = self.started.get(who)
            if p is not None and p.poll() is not None:
                raise RuntimeError(f"{who} exited rc={p.returncode} before {path.name} appeared")
            if time.monotonic() - t0 > timeout:
                raise TimeoutError(f"{path} never appeared")
            time.sleep(0.05)
        return time.monotonic() - t0

    def _start(self, name, argv, env):
        p = self.procs.start(name, argv, env, stdout=self.out(name), stderr=subprocess.STDOUT)
        self.started[name] = p
        return p

    def up(self) -> dict:
        names = self.bus_names()
        foreign = [n for n in names if not n.startswith(":") and n != "org.freedesktop.DBus"]
        if foreign:
            raise guard.BenchRefused(f"the bench bus is not fresh: {foreign}")
        times = {}
        t0 = time.monotonic()
        self._start("atspi", [ATSPI_LAUNCHER, "--launch-immediately"], dict(self.env))
        times["atspi"] = self.wait_name("org.a11y.Bus")
        self.set_a11y(True)
        self._start("pipewire", ["/usr/bin/pipewire"], dict(self.env, PIPEWIRE_CONFIG_DIR=str(self.base / "pwconf")))
        times["pipewire"] = self.wait_path(self.rt / "pipewire-0", "pipewire")
        self._start("wireplumber", ["/usr/bin/wireplumber", "-p", "policy"], dict(self.env))
        # KWin grants zkde_screencast to the KDE portal from its .desktop file, found through KService:
        # the bench HOME has no service cache until it is built here
        t1 = time.monotonic()
        with self.out("kbuildsycoca") as f:
            subprocess.run(["/usr/bin/kbuildsycoca6"], env=dict(self.env), stdout=f, stderr=subprocess.STDOUT,
                           timeout=120, close_fds=True)
        times["sycoca"] = time.monotonic() - t1
        kenv = dict(self.env, KWIN_FORCE_SW_CURSOR="1", QT_LOGGING_RULES=os.environ.get("N152_KWIN_LOG", ""))
        kenv.update(SOFTWARE_GL)
        # C748: a service the bus activates while KWin starts (the KDE portal, the wallet) must find the screen's name
        # already: without it Qt aborts, the bus tries again, a core dump each time (12 in a run, 26 Nov)
        self.activation_env({"WAYLAND_DISPLAY": SOCKET, "QT_QPA_PLATFORM": "wayland"})
        self._start("kwin", ["/usr/bin/kwin_wayland", "--virtual", "--socket", SOCKET,
                             "--width", str(WIDTH), "--height", str(HEIGHT)], kenv)
        times["kwin"] = self.wait_name("org.kde.KWin", 30)
        self.wait_path(self.rt / SOCKET, "kwin")
        time.sleep(KWIN_SETTLE)                        # plugins (screencast) load after the socket
        self.activation_env({"WAYLAND_DISPLAY": SOCKET, "QT_QPA_PLATFORM": "wayland"})
        self._start("portal-kde", [PORTAL_KDE], self.wenv(QT_LINUX_ACCESSIBILITY_ALWAYS_ON="1"))
        times["portal-kde"] = self.wait_name("org.freedesktop.impl.portal.desktop.kde", 30)
        self._start("portal", [PORTAL, "-r"], self.wenv())
        times["portal"] = self.wait_name("org.freedesktop.portal.Desktop", 30)
        times["total"] = time.monotonic() - t0
        self.log(f"up {json.dumps(times)}")
        self.check_real()
        return times

    def activation_env(self, extra: dict) -> None:
        """Services the bench bus activates by itself see the bench display (never the real one)."""
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                      "UpdateActivationEnvironment", GLib.Variant("(a{ss})", (extra,)), None,
                      Gio.DBusCallFlags.NONE, 2000, None)

    def set_a11y(self, on: bool) -> None:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Set",
                      GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", on))),
                      None, Gio.DBusCallFlags.NONE, 2000, None)

    def check_real(self) -> None:
        """The real runtime dir must hold the same Wayland sockets; no bench process on /dev/input."""
        now = guard.real_sockets()
        if not guard.same_real(self.real_before, now):
            raise guard.BenchRefused(f"real Wayland sockets changed: {self.real_before['wayland']} -> {now['wayland']}")
        pids = self.procs.pids() + [os.getpid()] + self.strays()
        self.unreadable = []
        held = guard.dev_input_holders(pids, self.unreadable)
        if held:
            raise guard.BenchRefused(f"/dev/input held by bench processes: {held}")
        gpu = guard.gpu_holders(pids, self.unreadable)
        if gpu:
            raise guard.BenchRefused(f"bench processes hold GPU devices: {sorted(set(gpu))[:6]}")
        sysbus = guard.system_bus_clients(pids)
        if sysbus:
            raise guard.BenchRefused(f"bench processes on the real system bus: {sysbus}")

    def alive(self) -> dict:
        return {n: p.poll() is None for n, p in self.started.items()}

    def strays(self) -> list:
        """Processes of ours that carry this bench's runtime dir but are not in our list (D-Bus activated)."""
        mine = set(self.procs.pids()) | {os.getpid()}
        out = []
        key = f"XDG_RUNTIME_DIR={self.rt}".encode()
        for d in os.listdir("/proc"):
            if not d.isdigit() or int(d) in mine:
                continue
            try:
                if os.stat(f"/proc/{d}").st_uid != os.getuid():
                    continue
                envb = Path(f"/proc/{d}/environ").read_bytes()
            except OSError:
                continue
            if key in envb.split(b"\0"):
                out.append(int(d))
        return out

    def _stop_strays(self, grace: float = 3.0) -> list:
        """The programs and services the bench bus activated, stopped by the PIDs just read; waited for."""
        # not dbus-run-session itself nor its daemon: dbus-run-session stops them when this process returns
        strays = [p for p in self.strays() if p != os.getppid() and _ppid(p) != os.getppid()]
        killed = []
        for pid in strays:
            try:
                os.kill(pid, 15)
                killed.append(pid)
            except ProcessLookupError:
                pass
        t0 = time.monotonic()
        while time.monotonic() - t0 < grace and any(Path(f"/proc/{p}").exists() and _ppid(p) != 1 for p in killed):
            time.sleep(0.05)
        return killed

    def down(self) -> dict:
        # The activated copies (programs, services) first, while the nested screen still exists; then the bench's own
        # processes (portal before KWin); then whatever woke meanwhile. Not the cause of C748: the aborts happen while
        # KWin is starting (measured 26 Nov, PIDs between KWin's and the bench's own portal).
        killed = self._stop_strays()
        self.procs.stop()
        killed += self._stop_strays()
        self.check_real()
        self.log(f"down strays={killed}")
        return {"strays": killed}


def _ppid(pid: int) -> int:
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return -1


def default_scratch() -> Path:
    return Path(os.environ.get("N152_SCRATCH") or Path(tempfile.gettempdir()) / "n152f0")


def which_missing() -> list:
    need = {"kwin_wayland": "/usr/bin/kwin_wayland", "dbus-run-session": "/usr/bin/dbus-run-session",
            "pipewire": "/usr/bin/pipewire", "wireplumber": "/usr/bin/wireplumber", "xdg-desktop-portal": PORTAL,
            "xdg-desktop-portal-kde": PORTAL_KDE, "at-spi-bus-launcher": ATSPI_LAUNCHER, "gcc": "/usr/bin/gcc"}
    out = [k for k, p in need.items() if not os.access(p, os.X_OK)]
    if not shutil.which("qrencode", path="/usr/bin:/bin"):
        out.append("qrencode")
    return out


if __name__ == "__main__":
    sys.exit("run sys/core/desk/bench/run_phase0.py")
