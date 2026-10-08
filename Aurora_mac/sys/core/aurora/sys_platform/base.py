# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What Aurora asks of the operating system, in one place (the Mac and Windows ports, phase 1, 2026-10-08).

Every place of the Linux code that speaks to the system directly (systemctl, /proc, nvidia-smi, fcntl, bwrap, nft,
v4l2/PulseAudio, /etc/aurora, sudo...) is listed in PORTING.md with the method of this interface that replaces it. A
platform answers each question the way its system can; where it cannot, it says so (None, "missing", []) and never
pretends: a measure it cannot take is "not measured", a cage it cannot build means nothing runs uncaged.

Every command goes through `self.run` (a Runner): the tests give recorded outputs of launchctl, PowerShell, ffmpeg,
nvidia-smi... so each platform is checked on any machine. This file, linux.py and __init__.py are the same in both port
folders (tests/test_platform_shared.py compares them when both are there).
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


@dataclass
class Result:
    code: int
    out: str = ""
    err: str = ""

    # the names of subprocess.CompletedProcess, so a call site keeps its shape
    returncode = property(lambda self: self.code)
    stdout = property(lambda self: self.out)
    stderr = property(lambda self: self.err)


Runner = Callable[[Sequence[str], float], Result]


def run_command(cmd: Sequence[str], timeout: float = 30) -> Result:
    """The real runner: no shell, text in UTF-8 whatever the system's code page, never an exception for a failure."""
    try:
        r = subprocess.run(list(cmd), capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return Result(127, "", f"{cmd[0]}: not found")
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{cmd[0]}: no answer in {timeout:.0f} s")
    text = lambda b: b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b or "")   # noqa: E731
    return Result(r.returncode, text(r.stdout), text(r.stderr))


@dataclass
class Device:
    id: str            # what ffmpeg is given (a path, an index, a DirectShow name)
    name: str          # what the owner reads


@dataclass
class Gpu:
    index: int
    name: str
    util: float | None = None          # percent; None = not measured on this system
    mem_used: float | None = None      # MiB
    mem_total: float | None = None     # MiB (unified memory on a Mac: the machine's)
    temp: float | None = None
    temp_limit: float | None = None


# the services of Aurora, by their Linux unit names: each platform maps them to its own (launchd labels, task names)
SERVICES = ("aurora-api", "aurora-llm", "aurora-models", "aurora-rem", "aurora-harvester", "aurora-sentinel",
            "aurora-https", "aurora-tunnel", "aurora-backup", "aurora-mount", "aurora-retime", "aurora-nft")

# GPU columns asked of nvidia-smi (Linux and Windows have the same tool and the same CSV)
NVIDIA_QUERY = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,temperature.gpu.tlimit"


def _num(s: str) -> float | None:
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None                                    # "[N/A]", "[Not Supported]"


def query_nvidia(run: "Runner") -> list[Gpu]:
    """Every NVIDIA GPU with nvidia-smi (Linux, Windows). An older driver without the thermal limit refuses the whole
    query for that one field: asked again without it."""
    r = run(["nvidia-smi", f"--query-gpu={NVIDIA_QUERY}", "--format=csv,noheader,nounits"], 10)
    if r.code == 0:
        return parse_nvidia(r.out)
    short = NVIDIA_QUERY.rsplit(",", 1)[0]
    r = run(["nvidia-smi", f"--query-gpu={short}", "--format=csv,noheader,nounits"], 10)
    return parse_nvidia("\n".join(f"{line}, [N/A]" for line in r.out.splitlines())) if r.code == 0 else []


def host_port(ip: str, port) -> str:
    """The way ss writes an address: "127.0.0.1:631", "[::1]:631", "*:22"."""
    return f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"


def parse_nvidia(csv: str) -> list[Gpu]:
    out = []
    for line in csv.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 7 or not p[0].isdigit():
            continue
        out.append(Gpu(int(p[0]), p[1], _num(p[2]), _num(p[3]), _num(p[4]), _num(p[5]), _num(p[6])))
    return out


@dataclass
class Platform:
    """The interface. Subclasses: linux.Linux (the reference: what Aurora does today), mac.Mac, windows.Windows."""
    run: Runner = run_command
    env: dict = field(default_factory=lambda: dict(os.environ))
    name = "base"

    # ---- services ---------------------------------------------------------------------------------------------
    def service_state(self, unit: str) -> str:
        """active | inactive | failed | missing, or the system's own word for a moment between (Linux: activating,
        deactivating, reloading — said as systemd says them, as Aurora's pages always did)."""
        raise NotImplementedError

    def service_info(self, unit: str) -> dict:
        """{"state", "mem_mib", "restarts", "result", "status"}: result "success" or why it ended, status its exit
        code; None where this system does not tell."""
        raise NotImplementedError

    def service_next_run(self, unit: str) -> str | None:
        """When a timed service (the backup) runs next, as the system says it; None when not timed or unknown."""
        raise NotImplementedError

    def service_command(self, unit: str) -> str:
        """What the service runs ("" when unknown): a second copy of Aurora never restarts the other's (C140)."""
        raise NotImplementedError

    def service_action(self, verb: str, units: Sequence[str], wait: bool = True, timeout: float = 120) -> Result:
        """start | stop | restart, for Aurora's own services only (the Linux polkit rule's limit, kept everywhere)."""
        raise NotImplementedError

    def _ours(self, units: Sequence[str], verb: str) -> None:
        if verb not in ("start", "stop", "restart"):
            raise ValueError(f"verb {verb!r}: start, stop or restart")
        for u in units:
            if u.removesuffix(".service").removesuffix(".timer").removesuffix(".target") not in SERVICES + ("aurora",):
                raise ValueError(f"{u}: not one of Aurora's services")

    # ---- the machine ------------------------------------------------------------------------------------------
    def gpus(self) -> list[Gpu]:
        raise NotImplementedError

    def accelerator(self) -> str:
        """cuda | metal | cpu: what llama.cpp and torch will use here."""
        raise NotImplementedError

    def cpu_times(self) -> tuple[float, float]:
        """(idle, total) CPU time since boot, for a load between two samples (sys_metrics): psutil reads /proc/stat on
        Linux, host_statistics on the Mac, GetSystemTimes on Windows. Idle includes the waiting for disks, as
        Linux's /proc/stat reading always did."""
        import psutil
        t = psutil.cpu_times()
        return t.idle + getattr(t, "iowait", 0.0), sum(t)

    def memory(self) -> dict:
        """{"total_mib", "used_mib", "swap_used_mib"}: used = total - available (Linux's MemAvailable)."""
        import psutil
        v, sw = psutil.virtual_memory(), psutil.swap_memory()
        return {"used_mib": (v.total - v.available) // 2**20, "total_mib": v.total // 2**20, "swap_used_mib": sw.used // 2**20}

    def os_info(self) -> dict:
        raise NotImplementedError

    def machine_id(self) -> str:
        """A stable id of this machine (the ethics code binds an exemption to it); "" when it cannot be read."""
        raise NotImplementedError

    def is_admin(self) -> bool:
        raise NotImplementedError

    def is_mount(self, path: Path) -> bool:
        """In the system's mount table, read WITHOUT touching the folder: a NAS asleep would hang a stat (sys_backup)."""
        raise NotImplementedError

    def gpu_free_mib(self, index: int) -> float | None:
        """Memory free on GPU `index` now, as the driver says (mdl_image: room for a picture); None = not measured."""
        raise NotImplementedError

    # ---- network ----------------------------------------------------------------------------------------------
    def listening(self) -> list[dict]:
        """The sockets waiting for connections: [{"proto": tcp|udp, "address": "host:port" ("[v6]:port"), "port",
        "process"}] — sec_hostaudit judges them; process "" where this system does not tell it to a non-admin."""
        raise NotImplementedError

    def own_addresses(self) -> set[str]:
        """Every address of this machine's interfaces: never blocked (sec_fwapi, C180)."""
        raise NotImplementedError

    def _psutil_addresses(self) -> set[str]:
        import socket
        import psutil
        return {a.address.split("%", 1)[0] for addrs in psutil.net_if_addrs().values() for a in addrs
                if a.family in (socket.AF_INET, socket.AF_INET6)}

    # ---- files ------------------------------------------------------------------------------------------------
    def key_dir(self) -> Path:
        """Where the owner's signing key pair lives (Linux: /etc/aurora), writable by the administrator only."""
        raise NotImplementedError

    def trusted_by_admin_only(self, path: Path) -> tuple[bool, str]:
        """(True, "") when only the administrator (root, SYSTEM, Administrators) can change `path` — the test the
        ethics code makes on the public key before trusting it."""
        raise NotImplementedError

    def is_private(self, path: Path) -> bool:
        """Only its owner (and the system's administrators) may read it: the guarantee mode 600/700 gives on Linux."""
        import stat
        return stat.S_IMODE(Path(path).stat().st_mode) & 0o077 == 0

    def make_private(self, path: Path) -> None:
        """Only its owner may read it, what is inside a folder too (the installer, on Aurora's folder)."""
        Path(path).chmod(0o700 if Path(path).is_dir() else 0o600)

    def lock(self, fh, exclusive: bool = True, wait: bool = True) -> bool:
        """A lock on an open file between processes; False when `wait` is False and someone else holds it."""
        raise NotImplementedError

    def unlock(self, fh) -> None:
        raise NotImplementedError

    def replace(self, src: Path, dst: Path) -> None:
        """Atomic replace (the tmp + rename every store of Aurora does)."""
        os.replace(src, dst)

    def process_env(self) -> dict:
        """Variables every process of Aurora is started with on this system (the services' launchers)."""
        return {}

    def venv_python(self, venv: Path) -> Path:
        return venv / "bin" / "python"

    def executable(self, folder: Path, name: str) -> Path:
        return folder / name

    def runtime_dir(self) -> Path:
        """Short-lived files of the session (sockets, the audio server's address)."""
        raise NotImplementedError

    def bold_font(self) -> Path | None:
        """A bold sans font for the videos' subtitles; None when none is found."""
        for f in self.fonts():
            if Path(f).is_file():
                return Path(f)
        return None

    def fonts(self) -> list[str]:
        raise NotImplementedError

    def ffmpeg_path(self, p: Path) -> str:
        """A path written as a filter's value (drawtext fontfile=, subtitles=), escaped twice as ffmpeg reads it
        twice: for the option (':' and "'") then for the filtergraph ('\\', "'", '[', ']', ',', ';'). Measured on a
        real Windows (v0.2.0's run): «C\\:/Windows/…» escaped once broke the graph; this form passed drawtext and
        subtitles with ':', a space, "'", ',', '[1]' and ';' in the path."""
        s = str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        for c in "\\'[],;":
            s = s.replace(c, "\\" + c)
        return s

    def dictionaries(self) -> list[Path]:
        """Word lists the privacy checks read (sec_privacy); [] where the system has none."""
        return []

    # ---- devices ----------------------------------------------------------------------------------------------
    def cameras(self) -> list[Device]:
        raise NotImplementedError

    def microphones(self) -> list[Device]:
        raise NotImplementedError

    def ffmpeg_camera(self, device: str, size: str) -> list[str]:
        """ffmpeg's input arguments for one picture from `device` at `size` (e.g. 1280x720)."""
        raise NotImplementedError

    def ffmpeg_microphone(self, device: str) -> list[str]:
        raise NotImplementedError

    # ---- cages and walls --------------------------------------------------------------------------------------
    def sandbox(self) -> str | None:
        """The cage plugins and projects run in: "bwrap", "sandbox-exec"; None = no cage here, so nothing runs."""
        raise NotImplementedError

    def cage(self, cmd: list[str], folder: Path, manifest: dict, filtered_env: Path, cfg) -> tuple[list[str], dict] | None:
        """A plugin's command inside this system's cage and the environment it needs there; None when this system has
        no cage now — then plg_host does not start the plugin (the owner chose the cages, 2026-10-08: «A»)."""
        raise NotImplementedError

    def host_firewall(self) -> str | None:
        """What blocks an address on this machine: "nft", "pf", "windows-firewall"; None when nothing can."""
        raise NotImplementedError

    # ---- what the owner is told -------------------------------------------------------------------------------
    def install_hint(self, tool: str) -> str:
        """The command that installs a missing tool (ffmpeg, pdftoppm...)."""
        raise NotImplementedError

    def as_admin(self, command: str) -> str:
        """How the owner runs `command` with the administrator's rights."""
        raise NotImplementedError

    manager = "systemd"                                  # who runs the services, as the pages name it
    listen_hint = "sudo ss -tulnp"                       # how the owner sees which program listens on a port

    def in_folder(self, folder, command: str) -> str:
        """A command the owner pastes in a terminal, run in `folder` (Linux and the Mac: cd && ...)."""
        return f"cd {folder} && {command}"


def cage_plan(folder: Path, manifest: dict, filtered_env: Path, cfg, tmp: Path) -> dict:
    """What any cage must give a plugin, the same contract as Linux's bubblewrap (plg_sandbox.wrap), as lists of real
    paths a system's own cage turns into its rules (the Mac: a sandbox profile; Windows: an AppContainer's ACLs):

      read   what it may read: Aurora's folder (code, venv), its own folder, the Python it runs on
      hide   never readable, even inside `read`: the real .env, the push keys, the other plugins' env files, the
             registered devices, the users' store, the other users' folders and state, its user's own .env
      allow  readable although inside `hide`: its own filtered .env (only its own secrets)
      write  writable: the folders the manifest names ("sandbox": {"write": [settings]}) and its private temp
      home   the user's home: hidden but for `read`
      network  False when the manifest says "sandbox": {"network": false} (forged plugins)
    """
    import sys
    from aurora import sys_users_layout as L

    def real(x) -> Path:
        return Path(os.path.realpath(x))
    base = cfg.base or cfg
    status = cfg.path("AURORA_STATUS_DIR")
    hide = [cfg.env_file, status / "push", status / "plugins" / "env", status / "devices.json", status / "users.db",
            base.path("AURORA_STATUS_DIR") / "users.db"]
    m = L.migrated(base)
    if m:
        me, admin = cfg.user or m["admin"], m["admin"]
        usr = L.usr(base)
        registered = L._registered(base) | {admin}
        for d in (x for x in usr.iterdir() if x.is_dir()) if usr.is_dir() else []:
            if d.name != me and not (me == admin and d.name not in registered):
                hide.append(d)
        for area in L.SYS_AREAS:
            users = L.root(base, area) / L.USERS
            hide += [d for d in (users.iterdir() if users.is_dir() else []) if d.is_dir() and d.name != me]
        hide.append(usr / me / ".env")
    write = []
    for key in manifest.get("sandbox", {}).get("write", []):
        w = cfg.path(key)
        w.mkdir(parents=True, exist_ok=True)
        write.append(w)
    tmp.mkdir(parents=True, exist_ok=True)
    reads = {real(cfg.root), real(folder), real(sys.base_prefix), real(sys.prefix), real(Path(sys.executable).parent)}
    return {"read": sorted(reads), "hide": sorted({real(h) for h in hide}), "allow": [real(filtered_env)],
            "write": sorted({real(w) for w in write} | {real(tmp)}), "home": real(Path.home()),
            "network": manifest.get("sandbox", {}).get("network") is not False, "tmp": real(tmp)}
