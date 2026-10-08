# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Linux: what Aurora does today, gathered here as the reference the other platforms are measured against. Each method
says the module it comes from; the behaviour is the same (systemd, /proc via psutil, nvidia-smi, fcntl, bwrap, nft,
v4l2 and PulseAudio/PipeWire, /etc/aurora, sudo)."""
from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .base import Device, Gpu, Platform, Result, query_nvidia



@dataclass
class Linux(Platform):
    name = "linux"
    sysfs: Path = Path("/sys")
    etc: Path = Path("/etc")

    # services: systemd units, started and stopped by the service user through the polkit rule (50-aurora.rules)
    def _show(self, unit: str, *props: str) -> dict:
        args = [x for p in props for x in ("-p", p)]
        r = self.run(["systemctl", "show", unit, *args], 10)
        return dict(line.split("=", 1) for line in r.out.splitlines() if "=" in line) if r.code == 0 else {}

    def service_state(self, unit: str) -> str:                       # net_cloudflare.service_state, sys_health
        v = self._show(unit, "LoadState", "ActiveState")
        if v.get("LoadState") != "loaded":
            return "missing"                                          # not-found, masked, error: not usable
        return v.get("ActiveState") or "inactive"

    def service_info(self, unit: str) -> dict:                       # sys_soak._unit, sys_backup.unit_failure
        v = self._show(unit, "LoadState", "ActiveState", "MemoryCurrent", "NRestarts", "Result", "ExecMainStatus")
        mem, restarts, status = v.get("MemoryCurrent", ""), v.get("NRestarts", ""), v.get("ExecMainStatus", "")
        return {"state": "missing" if v.get("LoadState") != "loaded" else v.get("ActiveState") or "inactive",
                "mem_mib": round(int(mem) / 2**20, 1) if mem.isdigit() else None,
                "restarts": int(restarts) if restarts.isdigit() else None,
                "result": v.get("Result"), "status": int(status) if status.lstrip("-").isdigit() else None}

    def service_next_run(self, unit: str) -> str | None:              # api/backup (the timer)
        r = self.run(["systemctl", "show", "-p", "NextElapseUSecRealtime", "--value", unit.replace(".service", ".timer")], 10)
        return r.out.strip() or None

    def service_command(self, unit: str) -> str:                       # api/knowledge._runs_here
        return self._show(unit, "ExecStart").get("ExecStart", "")

    def service_action(self, verb: str, units: Sequence[str], wait: bool = True, timeout: float = 120) -> Result:   # agents, knowledge, backup
        self._ours(units, verb)
        return self.run(["systemctl", verb, *([] if wait else ["--no-block"]), *units], timeout)

    def gpus(self) -> list[Gpu]:                                       # sys_metrics, kno_mood, mdl_image
        return query_nvidia(self.run)

    def accelerator(self) -> str:
        return "cuda" if self.gpus() else "cpu"

    def gpu_free_mib(self, index: int) -> float | None:                # mdl_image.free_gb
        r = self.run(["nvidia-smi", "-i", str(index), "--query-gpu=memory.free", "--format=csv,noheader,nounits"], 30)
        try:
            return float(r.out.strip()) if r.code == 0 else None
        except ValueError:
            return None

    def is_mount(self, path: Path) -> bool:                             # sys_backup.mounted
        try:
            return any(line.split()[1] == str(path) for line in Path("/proc/self/mounts").read_text().splitlines())
        except (OSError, IndexError):
            return False

    def os_info(self) -> dict:                                         # sys_bugreport
        name = ""
        try:
            for line in (self.etc / "os-release").read_text(encoding="utf-8").splitlines():
                if line.startswith("PRETTY_NAME="):
                    name = line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return {"system": "Linux", "name": name or "Linux", "kernel": platform.release(), "machine": platform.machine()}

    def machine_id(self) -> str:                                       # sys_ethics
        try:
            return (self.etc / "machine-id").read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def is_admin(self) -> bool:
        return os.geteuid() == 0

    def listening(self) -> list[dict]:                                 # sec_hostaudit.sockets (ss -tulnpH)
        import re
        out, seen = [], set()
        for line in self.run(["ss", "-tulnpH"], 10).out.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            proto, addr = parts[0], parts[4]
            port = addr.rsplit(":", 1)[-1]
            proc = (re.search(r'\(\("([^"]+)"', line) or [None, ""])[1]
            if (proto, addr, proc) in seen or not port.isdigit():
                continue
            seen.add((proto, addr, proc))
            out.append({"proto": proto, "address": addr, "port": port, "process": proc})
        return out

    def own_addresses(self) -> set[str]:                               # sec_fwapi (ip -j addr show)
        import json
        try:
            return {a["local"] for iface in json.loads(self.run(["ip", "-j", "addr", "show"], 5).out or "[]")
                    for a in iface.get("addr_info", []) if a.get("local")}
        except ValueError:
            return set()

    def key_dir(self) -> Path:                                         # sys_ethics.KEY_DIR
        return self.etc / "aurora"

    def trusted_by_admin_only(self, path: Path) -> tuple[bool, str]:   # sys_ethics.owner_public_key
        for x in (path.parent, path):
            try:
                st = x.stat()
            except OSError as e:
                return False, f"{x}: {e.strerror}"
            if st.st_uid != 0 or st.st_mode & 0o022:
                return False, f"{x} must belong to root and be writable by root only"
        return True, ""

    def lock(self, fh, exclusive: bool = True, wait: bool = True) -> bool:   # mdl_image, mdl_budget, sys_backup...
        import fcntl
        flags = (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (0 if wait else fcntl.LOCK_NB)
        try:
            fcntl.flock(fh, flags)
            return True
        except BlockingIOError:
            return False

    def unlock(self, fh) -> None:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_UN)

    def runtime_dir(self) -> Path:                                     # sns_av._env
        return Path(self.env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")

    def fonts(self) -> list[str]:                                      # kno_story.FONT
        return ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

    def dictionaries(self) -> list[Path]:                              # sec_privacy.DICTS
        return [p for p in (Path("/usr/share/dict/words"), Path("/usr/share/dict/italian"),
                            Path("/usr/share/dict/american-english"), Path("/usr/share/dict/british-english")) if p.is_file()]

    def cameras(self) -> list[Device]:                                 # sns_av.cameras
        out = []
        found = sorted((self.sysfs / "class" / "video4linux").glob("video*"), key=lambda p: int(p.name[5:] or 0))
        for d in found:
            try:
                if (d / "index").read_text().strip() != "0":          # a webcam's metadata node gives no images
                    continue
                out.append(Device(f"/dev/{d.name}", (d / "name").read_text().strip().split(":")[0]))
            except OSError:
                continue
        return out

    def microphones(self) -> list[Device]:                             # sns_av.microphones
        r = self.run(["pactl", "list", "sources"], 10)
        mics, cur = [], {}
        for line in r.out.splitlines():
            s = line.strip()
            if s.startswith(("Name:", "Nome:")):
                cur = {"id": s.split(":", 1)[1].strip()}
            elif s.startswith(("Description:", "Descrizione:")) and cur:
                if not cur["id"].endswith(".monitor"):                # the outputs' monitors are not microphones
                    mics.append(Device(cur["id"], s.split(":", 1)[1].strip()))
                cur = {}
        return mics

    def ffmpeg_camera(self, device: str, size: str) -> list[str]:
        return ["-f", "v4l2", "-video_size", size, "-i", device]

    def ffmpeg_microphone(self, device: str) -> list[str]:
        return ["-f", "pulse", "-i", device]

    def sandbox(self) -> str | None:                                   # plg_sandbox.available, prj_run
        return "bwrap" if shutil.which("bwrap") else None

    def cage(self, cmd, folder, manifest, filtered_env, cfg):              # plg_host: bubblewrap, as before
        from aurora import plg_sandbox
        return (plg_sandbox.wrap(cmd, folder, manifest, filtered_env, cfg), {}) if plg_sandbox.available() else None

    def host_firewall(self) -> str | None:                             # sec_hostfw
        return "nft" if Path("/usr/local/sbin/aurora-nft").is_file() else None

    def install_hint(self, tool: str) -> str:                          # sys_features: the same rule
        return f"sudo apt install {'ffmpeg' if tool.startswith('ff') else 'poppler-utils' if tool.startswith('pdf') else tool}"

    def as_admin(self, command: str) -> str:
        return f"sudo {command}"
