# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""macOS (Apple Silicon first; Intel Macs run on the CPU). Choices, each written in PORTING.md with its reason:

 services     launchd agents of the owner (~/Library/LaunchAgents/com.aurora.<name>.plist, domain gui/<uid>):
              Aurora restarts her own services without root, as the polkit rule allows on Linux. They run while the
              owner is logged in — a Mac kept as a server logs in by itself (System Settings → Users → automatic login)
 GPU          the Apple GPU through Metal (llama.cpp, torch "mps"); its use is not measured without root
              (powermetrics): said as not measured, never guessed; its memory is the machine's (unified)
 camera, mic  ffmpeg's avfoundation; macOS asks the owner once per program (Privacy → Camera, Microphone): a
              service cannot show that question, so the first photo is taken from the Terminal (install guide)
 cage         sandbox-exec (Seatbelt) — its profile is phase 3; until then plugins and projects do not run
 wall         pf with an anchor of Aurora's, through a small root helper like Linux's aurora-nft — phase 4
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .base import Device, Gpu, Platform, Result, host_port

LABEL = "com.aurora.{}"
BREW = {"ffmpeg": "ffmpeg", "ffprobe": "ffmpeg", "pdftoppm": "poppler", "pdftotext": "poppler"}
# "[0] FaceTime HD Camera" (older ffmpeg) or "[0] FaceTime HD Camera  [uid:...] [serial:...]" (libavdevice/
# avfoundation.m, avf_log_device_entry, checked 2026-10-08): the name stops before the uid
DEVICE_LINE = re.compile(r"\[(\d+)\]\s+(.+?)(?:\s{2}\[uid:.*)?\s*$")


@dataclass
class Mac(Platform):
    name = "mac"
    manager = "launchd"
    listen_hint = "sudo lsof -nP -iTCP -sTCP:LISTEN"
    uid: int = field(default_factory=lambda: os.getuid() if hasattr(os, "getuid") else 501)
    home: Path = field(default_factory=Path.home)
    machine: str = field(default_factory=platform.machine)

    # ---- services: launchd agents -----------------------------------------------------------------------------
    def label(self, unit: str) -> str:
        return LABEL.format(unit.removesuffix(".service").removeprefix("aurora-"))

    def plist(self, unit: str) -> Path:
        return self.home / "Library" / "LaunchAgents" / f"{self.label(unit)}.plist"

    def _target(self, unit: str) -> str:
        return f"gui/{self.uid}/{self.label(unit)}"

    def service_state(self, unit: str) -> str:
        r = self.run(["launchctl", "print", self._target(unit)], 10)
        if r.code != 0:                                  # 113: not loaded — stopped by bootout, or never installed
            return "inactive" if self.plist(unit).is_file() else "missing"
        state = re.search(r"^\s*state = (.+)$", r.out, re.M)
        if state and state.group(1).strip() == "running":
            return "active"
        code = re.search(r"^\s*last exit code = (.+)$", r.out, re.M)
        exited = code.group(1).strip() if code else "(never exited)"
        return "inactive" if exited in ("0", "(never exited)") else "failed"

    def service_info(self, unit: str) -> dict:
        r = self.run(["launchctl", "print", self._target(unit)], 10)
        runs = re.search(r"^\s*runs = (\d+)$", r.out, re.M)
        code = re.search(r"^\s*last exit code = (-?\d+)", r.out, re.M)
        status = int(code.group(1)) if code else None
        return {"state": self.service_state(unit), "mem_mib": None,          # launchd does not tell the memory
                "restarts": max(0, int(runs.group(1)) - 1) if runs else None,
                "result": None if r.code != 0 else "success" if not status else "exit-code", "status": status}

    def _plist(self, unit: str) -> dict:
        import plistlib
        try:
            return plistlib.loads(self.plist(unit).read_bytes())
        except (OSError, ValueError, plistlib.InvalidFileException):
            return {}

    def service_next_run(self, unit: str) -> str | None:
        when = self._plist(unit).get("StartCalendarInterval")       # the backup: every day at its time
        if isinstance(when, dict) and "Hour" in when:
            return f"every day at {int(when['Hour']):02d}:{int(when.get('Minute', 0)):02d}"
        return None

    def service_command(self, unit: str) -> str:
        return " ".join(str(x) for x in self._plist(unit).get("ProgramArguments") or [])

    def service_action(self, verb: str, units: Sequence[str], wait: bool = True, timeout: float = 120) -> Result:
        self._ours(units, verb)
        last = Result(0)
        for u in units:
            if verb == "stop":
                last = self.run(["launchctl", "bootout", self._target(u)], timeout)
                if last.code not in (0, 3, 113):        # 3/113: it was not loaded — stopped already
                    return last
                last = Result(0)
                continue
            if not self.plist(u).is_file():
                return Result(1, "", f"{self.plist(u)} is not installed (run the installer)")
            if self.run(["launchctl", "print", self._target(u)], 10).code != 0:
                last = self.run(["launchctl", "bootstrap", f"gui/{self.uid}", str(self.plist(u))], timeout)
                if last.code not in (0, 5):                  # 5: «Input/output error» — loaded meanwhile (or a bad plist)
                    return last
                if verb == "start":
                    continue                              # loaded with RunAtLoad: it starts by itself
            last = self.run(["launchctl", "kickstart", *(["-k"] if verb == "restart" else []), self._target(u)], timeout)
            if last.code != 0:
                return last
        return last

    # ---- the machine ------------------------------------------------------------------------------------------
    def gpus(self) -> list[Gpu]:
        r = self.run(["system_profiler", "SPDisplaysDataType", "-json"], 30)
        try:
            cards = json.loads(r.out).get("SPDisplaysDataType", []) if r.code == 0 else []
        except ValueError:
            cards = []
        total = None
        if self.machine == "arm64":                       # unified memory: the GPU's is the machine's
            m = self.run(["sysctl", "-n", "hw.memsize"], 10)
            total = int(m.out.strip()) / 2**20 if m.code == 0 and m.out.strip().isdigit() else None
        return [Gpu(i, c.get("sppci_model", "GPU"), mem_total=total) for i, c in enumerate(cards)]

    def accelerator(self) -> str:
        return "metal" if self.machine == "arm64" else "cpu"

    def gpu_free_mib(self, index: int) -> float | None:
        # unified memory: what the GPU can still take is what the system has available
        try:
            import psutil
            return psutil.virtual_memory().available / 2**20 if self.machine == "arm64" else None
        except ImportError:
            return None

    def is_mount(self, path: Path) -> bool:
        r = self.run(["mount"], 10)                       # "//user@nas/share on /path (smbfs, ...)": no stat of the folder
        return any(f" on {path} (" in line for line in r.out.splitlines())

    def os_info(self) -> dict:
        r = self.run(["sw_vers"], 10)
        kv = dict(re.findall(r"^(\w+):\s*(.+)$", r.out, re.M))
        name = " ".join(x for x in (kv.get("ProductName"), kv.get("ProductVersion")) if x) or "macOS"
        return {"system": "Darwin", "name": name, "build": kv.get("BuildVersion", ""), "machine": self.machine}

    def machine_id(self) -> str:
        r = self.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], 10)
        m = re.search(r'"IOPlatformUUID"\s*=\s*"([0-9A-Fa-f-]+)"', r.out)
        return m.group(1) if m else ""

    def is_admin(self) -> bool:
        return os.geteuid() == 0

    # ---- network: netstat (psutil asks for root on the Mac to see other programs' sockets) ---------------------
    def listening(self) -> list[dict]:
        out, seen = [], set()
        for proto in ("tcp", "udp"):
            for line in self.run(["netstat", "-an", "-p", proto], 10).out.splitlines():
                p = line.split()
                if len(p) < 5 or not p[0].startswith(proto) or (proto == "tcp" and p[-1] != "LISTEN"):
                    continue
                host, _, port = p[3].rpartition(".")            # "127.0.0.1.8080", "*.22", "::1.631"
                if not port.isdigit():
                    continue
                addr = host_port(host, port)
                if (proto, addr) not in seen:
                    seen.add((proto, addr))
                    out.append({"proto": proto, "address": addr, "port": port, "process": ""})
        return out

    def own_addresses(self) -> set[str]:
        return self._psutil_addresses()

    # ---- files ------------------------------------------------------------------------------------------------
    def key_dir(self) -> Path:
        return Path("/Library/Application Support/Aurora/keys")

    def trusted_by_admin_only(self, path: Path) -> tuple[bool, str]:
        for x in (path.parent, path):                     # the same test as Linux: root's, writable by root only
            try:
                st = x.stat()
            except OSError as e:
                return False, f"{x}: {e.strerror}"
            if st.st_uid != 0 or st.st_mode & 0o022:
                return False, f"{x} must belong to root and be writable by root only"
        return True, ""

    def lock(self, fh, exclusive: bool = True, wait: bool = True) -> bool:
        import fcntl                                      # BSD flock: the same calls as Linux
        try:
            fcntl.flock(fh, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (0 if wait else fcntl.LOCK_NB))
            return True
        except BlockingIOError:
            return False

    def unlock(self, fh) -> None:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_UN)

    def runtime_dir(self) -> Path:
        return Path(self.env.get("TMPDIR") or "/tmp")     # the owner's own /var/folders/... (0700)

    def fonts(self) -> list[str]:
        return ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc"]

    def dictionaries(self) -> list[Path]:
        return [p for p in (Path("/usr/share/dict/words"),) if p.is_file()]

    # ---- devices: ffmpeg's avfoundation -----------------------------------------------------------------------
    def _avfoundation(self) -> tuple[list[Device], list[Device]]:
        r = self.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""], 20)
        video, audio, now = [], [], None
        for line in (r.err + r.out).splitlines():        # ffmpeg lists them on stderr and exits with 1: normal
            if "AVFoundation video devices" in line:
                now = video
            elif "AVFoundation audio devices" in line:
                now = audio
            elif now is not None and (m := DEVICE_LINE.search(line)):
                if now is video and m.group(2).startswith("Capture screen"):
                    continue                              # the screen is not a camera: never offered
                now.append(Device(m.group(1), m.group(2)))
        return video, audio

    def cameras(self) -> list[Device]:
        return self._avfoundation()[0]

    def microphones(self) -> list[Device]:
        return self._avfoundation()[1]

    def ffmpeg_camera(self, device: str, size: str) -> list[str]:
        return ["-f", "avfoundation", "-framerate", "30", "-video_size", size, "-i", f"{device}:none"]

    def ffmpeg_microphone(self, device: str) -> list[str]:
        return ["-f", "avfoundation", "-i", f":{device}"]

    # ---- cages and walls --------------------------------------------------------------------------------------
    def sandbox(self) -> str | None:
        return "sandbox-exec" if shutil.which("sandbox-exec") else None

    def cage(self, cmd, folder, manifest, filtered_env, cfg):
        """The plugin inside sandbox-exec with a profile made from cage_plan (the owner, 2026-10-08: «A»): everything
        the system allows by default, then the home hidden but Aurora's folder and the Python, the secrets hidden even
        there but the plugin's own filtered .env, writes only in its folders and its temp, no network when its manifest
        says so. In a profile the LAST rule that matches decides, so each line narrows or reopens the one above it."""
        if not self.sandbox():
            return None
        from .base import cage_plan
        user = getattr(cfg, "user", None)
        plan = cage_plan(folder, manifest, filtered_env, cfg,
                         Path(cfg.root) / "sys" / "tmp" / "cages" / (f"{folder.name}.{user}" if user else folder.name))
        prof = profile(plan)
        return (["/usr/bin/sandbox-exec", "-p", prof, *cmd],
                {"AURORA_ENV_FILE": str(plan["allow"][0]), "AURORA_IN_SANDBOX": "1", "TMPDIR": str(plan["tmp"])})

    def host_firewall(self) -> str | None:
        return "pf" if Path("/usr/local/sbin/aurora-pf").is_file() else None

    def install_hint(self, tool: str) -> str:
        return f"brew install {BREW['ffmpeg' if tool.startswith('ff') else 'pdftoppm' if tool.startswith('pdf') else tool] if tool.startswith(('ff', 'pdf')) else tool}"

    def as_admin(self, command: str) -> str:
        return f"sudo {command}"


def _q(path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _where(path: Path) -> str:
    """A folder and all under it, or one file (a path not there yet: as a folder, the wider of the two)."""
    return f"(literal {_q(path)})" if path.is_file() else f"(subpath {_q(path)})"


def profile(plan: dict) -> str:
    """The sandbox profile (SBPL) of a cage_plan."""
    rules = ["(version 1)", "(allow default)"]
    if str(plan["home"]) != "/":
        rules.append(f"(deny file-read* file-write* (subpath {_q(plan['home'])}))")
    rules.append("(allow file-read* " + " ".join(f"(subpath {_q(r)})" for r in plan["read"]) + ")")
    if plan["hide"]:
        rules.append("(deny file-read* file-write* " + " ".join(_where(h) for h in plan["hide"]) + ")")
    rules.append("(allow file-read* " + " ".join(f"(literal {_q(a)})" for a in plan["allow"]) + ")")
    rules.append("(deny file-write*)")
    rules.append("(allow file-write* " + " ".join(f"(subpath {_q(w)})" for w in plan["write"])
                 + ' (literal "/dev/null") (literal "/dev/tty") (regex #"^/dev/fd/"))')
    if not plan["network"]:
        rules.append("(deny network*)")
    return "\n".join(rules) + "\n"
