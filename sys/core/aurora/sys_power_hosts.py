# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Computers and servers Aurora can restart or shut down over SSH (owner, 2026-10-28: «aggiungere anche altri tipi di
device, come computer o server in modalità ssh (con procedura guidata su come fare, come creare lo script di shutdown
o restart sulla macchina target, la chiave rsa da aggiungere e come farlo e dove…)»), each with its own «shut down when
the UPS's battery is low».

The way in is narrow on purpose. Aurora has a key of its own (<STATUS>/keys/power_ed25519, made here, never the
owner's). On the target, that key's line in authorized_keys forces one script, aurora-power, whatever is asked. The
script knows three words: test, restart and shutdown. sudo lets it run only the two power commands. So the key opens
no shell. The guided window gives the target's commands with the user filled in: the script, the sudoers line, the key's
line.
"""
from __future__ import annotations

import json
import re
import secrets
import subprocess
import threading
from pathlib import Path

from . import sys_config, sys_log

_lock = threading.Lock()
FIELDS = {"name": 60, "host": 200, "user": 64, "port": 6, "os": 10, "ups_off": 0}
OSES = ("linux", "macos")
ACTIONS = ("test", "restart", "shutdown")
SCRIPT = "/usr/local/sbin/aurora-power"
POWER = {"linux": ("/usr/bin/systemctl reboot", "/usr/bin/systemctl poweroff"),
         "macos": ("/sbin/shutdown -r now", "/sbin/shutdown -h now")}


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR")
    d.mkdir(parents=True, exist_ok=True)
    return d


def key(cfg: sys_config.Config) -> Path:
    """Aurora's own key for the targets, made the first time (ed25519: these are computers, not a Sophos)."""
    k = _dir(cfg) / "keys" / "power_ed25519"
    if not k.exists():
        k.parent.mkdir(parents=True, exist_ok=True)
        k.parent.chmod(0o700)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "aurora-power", "-f", str(k)],
                       check=True, capture_output=True, timeout=30)
    return k


def public_key(cfg: sys_config.Config) -> str:
    return key(cfg).with_suffix(".pub").read_text(encoding="ascii").strip()


def load(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads((_dir(cfg) / "power_hosts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, items: list[dict]) -> None:
    f = _dir(cfg) / "power_hosts.json"
    f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    f.chmod(0o600)


def check(item: dict) -> dict:
    out = {k: str(item.get(k) or "").strip()[:n] for k, n in FIELDS.items() if n}
    out["ups_off"] = bool(item.get("ups_off"))
    out["port"] = out["port"] or "22"
    out["os"] = out["os"] or "linux"
    if not out["name"]:
        raise ValueError("name: required")
    if not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", out["host"]):
        raise ValueError("host: an address or a name")
    if not re.fullmatch(r"[a-z_][a-z0-9_.\-]*", out["user"], re.I):
        raise ValueError("user: a login name on the target")
    if not out["port"].isdigit() or not 1 <= int(out["port"]) <= 65535:
        raise ValueError("port: 1-65535")
    if out["os"] not in OSES:
        raise ValueError(f"os: one of {', '.join(OSES)}")
    return out


def put(cfg: sys_config.Config, item: dict, hid: str | None = None) -> dict:
    clean = check(item)
    with _lock:
        items = load(cfg)
        if hid:
            for i, x in enumerate(items):
                if x["id"] == hid:
                    items[i] = {**x, **clean, "id": hid}
                    if any(x.get(k) != clean[k] for k in ("host", "user", "port")):
                        items[i]["tested"] = None          # another machine: tried again before it counts
                    _save(cfg, items)
                    return items[i]
            raise KeyError(hid)
        new = {"id": secrets.token_hex(4), **clean, "tested": None}
        _save(cfg, items + [new])
        return new


def delete(cfg: sys_config.Config, hid: str) -> bool:
    with _lock:
        items = load(cfg)
        kept = [x for x in items if x["id"] != hid]
        if len(kept) != len(items):
            _save(cfg, kept)
    return len(kept) != len(items)


def setup(cfg: sys_config.Config, item: dict) -> dict:
    """What the owner runs on the target, the user filled in: the script, the sudo rule, the key's line."""
    reboot, poweroff = POWER[item.get("os") or "linux"]
    user = item["user"]
    script = (f"#!/bin/sh\n# Aurora's power commands: only these, whatever was asked\n"
              f"case \"$SSH_ORIGINAL_COMMAND\" in\n  test) echo ok ;;\n  restart) sudo -n {reboot} ;;\n"
              f"  shutdown) sudo -n {poweroff} ;;\n  *) echo refused; exit 1 ;;\nesac\n")
    sudoers = f"{user} ALL=(root) NOPASSWD: {reboot}, {poweroff}"
    line = (f'command="{SCRIPT}",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding '
            f"{public_key(cfg)}")
    home = f"/Users/{user}" if item.get("os") == "macos" else ("/root" if user == "root" else f"/home/{user}")
    commands = [
        f"sudo tee {SCRIPT} > /dev/null <<'EOF'\n{script}EOF",
        f"sudo chmod 755 {SCRIPT}",
        f"echo '{sudoers}' | sudo tee /etc/sudoers.d/aurora-power > /dev/null && sudo chmod 440 /etc/sudoers.d/aurora-power"
        " && sudo visudo -cf /etc/sudoers.d/aurora-power",
        f"sudo -u {user} mkdir -p {home}/.ssh && echo '{line}' | sudo -u {user} tee -a {home}/.ssh/authorized_keys > /dev/null"
        f" && sudo chmod 600 {home}/.ssh/authorized_keys",
    ]
    return {"script": script, "sudoers": sudoers, "authorized_keys": line, "commands": commands, "path": SCRIPT}


def run(cfg: sys_config.Config, item: dict, action: str, timeout: int = 20) -> dict:
    """test, restart or shutdown sent over SSH with Aurora's key; for the last two a dropped connection is success."""
    if action not in ACTIONS:
        raise ValueError(f"action: one of {', '.join(ACTIONS)}")
    cmd = ["ssh", "-i", str(key(cfg)), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new", "-o", f"ConnectTimeout={min(timeout, 10)}", "-p", str(item["port"]),
           f"{item['user']}@{item['host']}", action]
    sys_log.get_logger("power").warning("audit: %s sent to %s (%s)", action, item["name"], item["host"])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": action != "test", "detail": "no answer (it may be going down)"}
    text = (r.stdout + r.stderr).strip()
    if action == "test":
        ok = r.returncode == 0 and r.stdout.strip().endswith("ok")
    else:                                              # 255 with «closed by remote host»: it went down
        ok = r.returncode == 0 or "closed" in text.lower()
    return {"ok": ok, "detail": text[-300:]}


def test(cfg: sys_config.Config, hid: str) -> dict:
    with _lock:
        items = load(cfg)
    it = next((x for x in items if x["id"] == hid), None)
    if it is None:
        raise KeyError(hid)
    out = run(cfg, it, "test")
    with _lock:
        items = load(cfg)
        for x in items:
            if x["id"] == hid:
                x["tested"] = bool(out["ok"])
        _save(cfg, items)
    return out


def ups_targets(cfg: sys_config.Config) -> list[dict]:
    """The machines to shut down with the UPS: chosen, and tried once with success."""
    return [x for x in load(cfg) if x.get("ups_off") and x.get("tested")]
