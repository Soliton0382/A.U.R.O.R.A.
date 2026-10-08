# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Windows 10/11, x64 (an NVIDIA card through CUDA, or the CPU). Choices, each written in PORTING.md with its reason:

 services     scheduled tasks of the owner in the folder \\Aurora\\ (at logon, restarted on failure): Aurora starts and
              stops her own without the administrator, as the polkit rule allows on Linux. Asked through PowerShell's
              ScheduledTasks module, whose states are English names whatever the language of Windows (schtasks.exe
              prints them translated: «Pronto», «In esecuzione»). A stop ends the process (no SIGTERM on Windows):
              the services must save as they go, which they already do (tmp + replace)
 text         every process starts with PYTHONUTF8=1: 70 places read and write text without an encoding, and
              Windows would use cp1252 (the accents of every Italian text)
 files        os.replace fails while another process has the file open (a sharing violation, not on Linux):
              replace() tries again for a moment. chmod 0600 does nothing here: the secrets are kept by the folder's
              ACL (the installer gives the Aurora folder to the owner and SYSTEM only)
 key          %ProgramData%\\Aurora\\keys, trusted when only SYSTEM, Administrators and TrustedInstaller may write it
              and its owner is one of them — read as SIDs, never as names (translated: «Administrators» is not the
              same word in every Windows)
 camera, mic  ffmpeg's dshow; a device is named by its unique «alternative name» (two identical webcams differ)
 cage         none yet (no bwrap): plugins and projects do not run — never uncaged (phase 3: AppContainer)
 wall         Windows Firewall rules through a helper run as SYSTEM — phase 4
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Sequence

from .base import Device, Gpu, Platform, Result, host_port, query_nvidia

TASKS = "\\Aurora\\"
LOCK_AT = 1 << 30                 # the locked byte: past any content, so the content stays readable
WINGET = {"ffmpeg": "Gyan.FFmpeg", "ffprobe": "Gyan.FFmpeg", "pdftoppm": "oschwartz10612.Poppler",
          "pdftotext": "oschwartz10612.Poppler"}
# a task's last result that is not a failure (WinError.h, «Task Scheduler error and success constants», checked
# 2026-10-08): 0 the program ended well; SCHED_S_TASK_READY, _RUNNING, _HAS_NOT_RUN, _TERMINATED (stopped by the
# user), _QUEUED. Every SCHED_E_ (0x8004....) is a failure — 0x8004130F is SCHED_E_ACCOUNT_INFORMATION_NOT_SET.
NOT_FAILED = {0, 0x41300, 0x41301, 0x41303, 0x41306, 0x41325}
# who may change the signing key: SYSTEM, Administrators, TrustedInstaller
ADMIN_SIDS = {"S-1-5-18", "S-1-5-32-544", "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"}
# rights that change a file or its permissions (FILE_WRITE_DATA, APPEND, WRITE_EA, WRITE_ATTRIBUTES, DELETE,
# WRITE_DAC, WRITE_OWNER, GENERIC_ALL, GENERIC_WRITE)
WRITE_BITS = 0x2 | 0x4 | 0x10 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000
# '"Name" (video)', '"Name" (video, audio)' or '"Name" (none)' (libavdevice/dshow.c, ffmpeg 5 and later, checked
# 2026-10-08): a device of both kinds is a camera and a microphone
DSHOW_TYPED = re.compile(r'\]\s+"(.+)"\s+\(([a-z, ]+)\)\s*$')
DSHOW_PLAIN = re.compile(r'\]\s+"(.+)"\s*$')
DSHOW_ALT = re.compile(r'Alternative name\s+"(.+)"\s*$')


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


@dataclass
class Windows(Platform):
    name = "windows"
    manager = "Utilità di pianificazione"
    listen_hint = "Get-NetTCPConnection -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess"

    def _ps(self, script: str, timeout: float = 60) -> Result:
        return self.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                         "-Command", script], timeout)

    # ---- services: scheduled tasks ----------------------------------------------------------------------------
    def task(self, unit: str) -> str:
        return unit.removesuffix(".service").removeprefix("aurora-")

    def service_state(self, unit: str) -> str:
        t = _ps_quote(self.task(unit))
        r = self._ps(f"$t = Get-ScheduledTask -TaskPath '{TASKS}' -TaskName {t} -ErrorAction Stop; "
                     f"$t.State.ToString() + '|' + (Get-ScheduledTaskInfo -InputObject $t).LastTaskResult", 30)
        if r.code != 0 or "|" not in r.out:
            return "missing"
        state, last = (r.out.strip().splitlines()[-1].split("|") + [""])[:2]   # extra fields ignored
        if state == "Running":
            return "active"
        if state == "Queued":                             # started, not running yet: systemd's «activating»
            return "activating"
        try:
            code = int(last) & 0xFFFFFFFF
        except ValueError:
            code = 0
        return "inactive" if code in NOT_FAILED or state == "Disabled" else "failed"

    def _task_info(self, unit: str) -> list[str] | None:
        t = _ps_quote(self.task(unit))
        r = self._ps(f"$t = Get-ScheduledTask -TaskPath '{TASKS}' -TaskName {t} -ErrorAction Stop; $i = Get-ScheduledTaskInfo -InputObject $t; "
                     "$n = if ($i.NextRunTime) { $i.NextRunTime.ToString('s') } else { '' }; "
                     "$a = ($t.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }) -join ' ; '; "
                     "$t.State.ToString() + '|' + $i.LastTaskResult + '|' + $n + '|' + $a", 30)
        if r.code != 0 or "|" not in r.out:
            return None
        return r.out.strip().splitlines()[-1].split("|", 3)

    def service_info(self, unit: str) -> dict:
        info = self._task_info(unit)
        if info is None:
            return {"state": "missing", "mem_mib": None, "restarts": None, "result": None, "status": None}
        try:
            code = int(info[1]) & 0xFFFFFFFF
        except ValueError:
            code = None
        return {"state": self.service_state(unit), "mem_mib": None, "restarts": None,
                "result": "success" if code in NOT_FAILED else "exit-code", "status": code}

    def service_next_run(self, unit: str) -> str | None:
        info = self._task_info(unit)
        return (info[2] or None) if info and len(info) > 2 else None

    def service_command(self, unit: str) -> str:
        info = self._task_info(unit)
        return info[3] if info and len(info) > 3 else ""

    def service_action(self, verb: str, units: Sequence[str], wait: bool = True, timeout: float = 120) -> Result:
        self._ours(units, verb)
        last = Result(0)
        for u in units:
            t = _ps_quote(self.task(u))
            steps = {"start": ["Start"], "stop": ["Stop"], "restart": ["Stop", "Start"]}[verb]
            script = "; ".join(f"{s}-ScheduledTask -TaskPath '{TASKS}' -TaskName {t} -ErrorAction Stop" for s in steps)
            last = self._ps(script, timeout)
            if last.code != 0:
                return last
        return last

    # ---- the machine ------------------------------------------------------------------------------------------
    def gpus(self) -> list[Gpu]:
        return query_nvidia(self.run)

    def accelerator(self) -> str:
        return "cuda" if self.gpus() else "cpu"

    def gpu_free_mib(self, index: int) -> float | None:
        r = self.run(["nvidia-smi", "-i", str(index), "--query-gpu=memory.free", "--format=csv,noheader,nounits"], 30)
        try:
            return float(r.out.strip()) if r.code == 0 else None
        except ValueError:
            return None

    def is_mount(self, path: Path) -> bool:
        return False                                      # no mounts: the NAS is written as \\nas\share (PORTING.md)

    def os_info(self) -> dict:
        r = self._ps("$o = Get-CimInstance Win32_OperatingSystem; $o.Caption + '|' + $o.Version + '|' + $o.OSArchitecture", 30)
        parts = (r.out.strip().splitlines() or [""])[-1].split("|")
        parts += [""] * (3 - len(parts))
        return {"system": "Windows", "name": parts[0].strip() or "Windows", "build": parts[1].strip(),
                "machine": parts[2].strip()}

    def machine_id(self) -> str:
        r = self.run(["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"], 10)
        m = re.search(r"MachineGuid\s+REG_SZ\s+([0-9A-Fa-f-]{36})", r.out)
        return m.group(1).lower() if m else ""

    def is_admin(self) -> bool:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    # ---- network: psutil (GetExtendedTcpTable / UdpTable) ------------------------------------------------------
    def listening(self) -> list[dict]:
        import socket
        import psutil
        out, seen = [], set()
        for c in psutil.net_connections(kind="inet"):
            tcp = c.type == socket.SOCK_STREAM
            if (tcp and c.status != psutil.CONN_LISTEN) or (not tcp and c.raddr) or not c.laddr:
                continue
            try:
                proc = psutil.Process(c.pid).name() if c.pid else ""
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc = ""
            proto, addr = ("tcp" if tcp else "udp"), host_port(c.laddr.ip, c.laddr.port)
            if (proto, addr, proc) not in seen:
                seen.add((proto, addr, proc))
                out.append({"proto": proto, "address": addr, "port": str(c.laddr.port), "process": proc})
        return out

    def own_addresses(self) -> set[str]:
        return self._psutil_addresses()

    # ---- files ------------------------------------------------------------------------------------------------
    def key_dir(self) -> Path:
        return Path(self.env.get("ProgramData") or r"C:\ProgramData") / "Aurora" / "keys"

    def _acl(self, path: Path) -> tuple[str, list[tuple[str, int, str, str]]] | None:
        """(owner SID, [(SID, rights mask, Allow|Deny, propagation)]) or None when it cannot be read."""
        script = (f"$a = Get-Acl -LiteralPath {_ps_quote(str(path))}; "
                  "'OWNER|' + $a.GetOwner([System.Security.Principal.SecurityIdentifier]).Value; "
                  "foreach ($r in $a.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) "
                  "{ $r.IdentityReference.Value + '|' + [int64][int]$r.FileSystemRights + '|' + $r.AccessControlType + '|' + $r.PropagationFlags }")
        r = self._ps(script, 30)
        if r.code != 0:
            return None
        owner, rules = "", []
        for line in r.out.splitlines():
            p = line.strip().split("|")
            if p[0] == "OWNER" and len(p) == 2:
                owner = p[1]
            elif len(p) == 4 and p[0].startswith("S-"):
                try:
                    rules.append((p[0], int(p[1]) & 0xFFFFFFFF, p[2], p[3]))
                except ValueError:
                    continue
        return (owner, rules) if owner else None

    def trusted_by_admin_only(self, path: Path) -> tuple[bool, str]:
        for x in (path.parent, path):
            acl = self._acl(x)
            if acl is None:
                return False, f"{x}: permissions not readable"
            owner, rules = acl
            if owner not in ADMIN_SIDS:
                return False, f"{x} must belong to SYSTEM or the Administrators (owner {owner})"
            for sid, mask, kind, propagation in rules:
                if kind != "Allow" or "InheritOnly" in propagation:   # an inherit-only rule is not on x itself
                    continue
                if mask & WRITE_BITS and sid not in ADMIN_SIDS:
                    return False, f"{x} may be changed by {sid}: only SYSTEM and the Administrators may"
        return True, ""

    def lock(self, fh, exclusive: bool = True, wait: bool = True) -> bool:
        """msvcrt locks one byte, far past the content (LOCK_AT): Windows's locks are mandatory, a locked byte
        cannot even be read by another process, and Aurora reads the GPU lock's file to say who holds it. There is
        no shared lock, so a shared one is exclusive (where Aurora takes one it only asks «is someone holding it?»).
        msvcrt's own waiting gives up after 10 s: here the waiting is ours and does not give up."""
        import msvcrt
        pos = fh.tell()
        try:
            while True:
                fh.seek(LOCK_AT)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    return True
                except OSError:
                    if not wait:
                        return False
                    time.sleep(0.05)
        finally:
            fh.seek(pos)

    def unlock(self, fh) -> None:
        import msvcrt
        pos = fh.tell()
        fh.seek(LOCK_AT)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            fh.seek(pos)

    def replace(self, src: Path, dst: Path) -> None:
        import os
        for i in range(20):                               # a reader holding dst open: a sharing violation, briefly
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if i == 19:
                    raise
                time.sleep(0.05)

    def process_env(self) -> dict:
        return {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

    def venv_python(self, venv: Path) -> Path:
        return venv / "Scripts" / "python.exe"

    def executable(self, folder: Path, name: str) -> Path:
        return folder / (name if PureWindowsPath(name).suffix else f"{name}.exe")

    def runtime_dir(self) -> Path:
        return Path(self.env.get("TEMP") or self.env.get("TMP") or str(Path(self.env.get("LOCALAPPDATA", "C:/")) / "Temp"))

    def fonts(self) -> list[str]:
        win = self.env.get("WINDIR") or r"C:\Windows"
        return [str(Path(win) / "Fonts" / f) for f in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf")]

    # ---- devices: ffmpeg's dshow ------------------------------------------------------------------------------
    def _dshow(self) -> tuple[list[Device], list[Device]]:
        r = self.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], 20)
        video, audio, section, last = [], [], None, None
        for line in (r.err + r.out).splitlines():        # listed on stderr, exit code 1: normal
            if "DirectShow video devices" in line:
                section = video
                continue
            if "DirectShow audio devices" in line:
                section = audio
                continue
            if (m := DSHOW_ALT.search(line)) and last is not None:
                last.id = m.group(1)                      # unique, where two devices share a name
                continue
            if m := DSHOW_TYPED.search(line):             # ffmpeg 5 and later: the kinds on the same line
                kinds = {k.strip() for k in m.group(2).split(",")}
                last = Device(m.group(1), m.group(1)) if kinds & {"video", "audio"} else None
                if "video" in kinds:
                    video.append(last)
                if "audio" in kinds:
                    audio.append(last)                    # the same object: its alternative name reaches both
                continue
            if section is not None and (m := DSHOW_PLAIN.search(line)):   # ffmpeg 4: under a heading
                last = Device(m.group(1), m.group(1))
                section.append(last)
        return video, audio

    def cameras(self) -> list[Device]:
        return self._dshow()[0]

    def microphones(self) -> list[Device]:
        return self._dshow()[1]

    def ffmpeg_camera(self, device: str, size: str) -> list[str]:
        return ["-f", "dshow", "-video_size", size, "-i", f"video={device}"]

    def ffmpeg_microphone(self, device: str) -> list[str]:
        return ["-f", "dshow", "-i", f"audio={device}"]

    # ---- cages and walls --------------------------------------------------------------------------------------
    def sandbox(self) -> str | None:
        return None

    def host_firewall(self) -> str | None:
        helper = Path(self.env.get("ProgramData") or r"C:\ProgramData") / "Aurora" / "bin" / "aurora-wfw.ps1"
        return "windows-firewall" if helper.is_file() else None

    def install_hint(self, tool: str) -> str:
        return f"winget install --id {WINGET['ffmpeg' if tool.startswith('ff') else 'pdftoppm' if tool.startswith('pdf') else tool] if tool.startswith(('ff', 'pdf')) else tool} -e"

    def as_admin(self, command: str) -> str:
        return f"[PowerShell as administrator] {command}"

    def in_folder(self, folder, command: str) -> str:
        # Windows PowerShell 5.1 (the one every Windows has) knows no "&&"
        return f"Set-Location -LiteralPath {_ps_quote(str(folder))}; {command}"
