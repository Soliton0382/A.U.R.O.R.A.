# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own firewall on this machine (owner, 2026-10-06: "managing Ubuntu's firewall would make Aurora very quick
to defend herself").

The main firewall protects the house; this one protects Aurora's machine from whoever attacks her directly — in a
second, with no round trip to the firewall's API. It uses only /usr/local/sbin/aurora-nft (installed by the owner with
sys/deploy/nft/install.sh, the only root command Aurora may run): an address in the table "inet aurora" for some hours,
then out by itself (an nftables timeout). Why it blocks:
  honeypot   someone opened one of the decoy ports (AURORA_HONEYPOT_PORTS): nobody has a reason to
  login      the API's own lockout (AURORA_AUTH_MAX_FAILS wrong credentials): the address is also kept off the machine
Never blocked: the protected addresses (AURORA_DEFENCE_PROTECTED: the owner's phone…), this machine, the firewall,
loopback. Every block is recorded (<STATUS>/security/hostfw.json), told, and can be lifted from the Security page.
"""
from __future__ import annotations

import ipaddress
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import sys_config

HELPER = Path("/usr/local/sbin/aurora-nft")
SOCKET = Path("/run/aurora-nftd.sock")
_lock = threading.Lock()


def call(*args: str, timeout: float = 15) -> tuple[int, str]:
    """(exit code, output) of aurora-nft. Through its socket (aurora-nftd.socket): Aurora's services are hardened
    (NoNewPrivileges) and sudo cannot work inside them — it never did, until C194; sudo -n is kept for the shell."""
    if SOCKET.exists():
        import socket
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(str(SOCKET))
                s.sendall((" ".join(args) + "\n").encode())
                s.shutdown(socket.SHUT_WR)
                data = b""
                while chunk := s.recv(65536):
                    data += chunk
        except OSError as e:
            return 1, f"the socket of Aurora's firewall does not answer: {e}"
        text = data.decode(errors="replace")
        m = re.search(r"#rc (\d+)\s*$", text)
        return (int(m.group(1)) if m else 1), text[:m.start()].strip() if m else text.strip()
    if not HELPER.is_file() or not shutil.which("sudo"):
        return 1, "aurora-nft not installed: sudo bash sys/deploy/nft/install.sh"
    try:
        r = subprocess.run(["sudo", "-n", str(HELPER), *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return r.returncode, (r.stdout or r.stderr).strip()


def available() -> bool:
    return call("list")[0] == 0


def _file(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "security"
    d.mkdir(parents=True, exist_ok=True)
    return d / "hostfw.json"


def _load(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(_file(cfg).read_text())
    except (OSError, ValueError):
        return []


def never(cfg: sys_config.Config, ip: str) -> str:
    """Why an address is never blocked here ("" = it may be)."""
    from . import sec_defence, sec_fwapi
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "not an address"
    if a.version != 4 or a.is_loopback or a.is_unspecified or a.is_multicast:
        return "never blocked"
    if any(a in n for n in sec_defence.protected(cfg)):
        return "a protected address"
    try:
        sec_fwapi.blockable(cfg, ip)                     # the firewall itself, this machine's own addresses
    except sec_fwapi.FirewallAPIError as e:
        return str(e)
    return ""


def block(cfg: sys_config.Config, ip: str, why: str, hours: float | None = None) -> dict:
    """Block `ip` on this machine for some hours; {"ok", "why"}."""
    if not cfg["AURORA_HOSTFW"]:
        return {"ok": False, "why": "AURORA_HOSTFW off"}
    reason = never(cfg, ip)
    if reason:
        return {"ok": False, "why": reason}
    hours = float(hours or cfg["AURORA_HOSTFW_HOURS"])
    secs = int(max(60, min(hours * 3600, 604800)))
    rc, out = call("block", ip, str(secs))
    if rc != 0:
        return {"ok": False, "why": (out or "aurora-nft not installed: sudo bash sys/deploy/nft/install.sh")[:200]}
    with _lock:
        items = _load(cfg)
        items.append({"ip": ip, "why": why, "at": time.time(), "until": time.time() + secs})
        _file(cfg).write_text(json.dumps(items[-500:]))
    return {"ok": True, "until": time.time() + secs}


def unblock(cfg: sys_config.Config, ip: str) -> dict:
    rc, _out = call("unblock", ip)
    with _lock:
        items = _load(cfg)
        for b in items:
            if b["ip"] == ip and b["until"] > time.time():
                b["until"] = time.time()
                b["lifted"] = True
        _file(cfg).write_text(json.dumps(items[-500:]))
    return {"ok": rc == 0}


def active(cfg: sys_config.Config) -> list[dict]:
    now = time.time()
    return [b for b in _load(cfg) if b["until"] > now]
