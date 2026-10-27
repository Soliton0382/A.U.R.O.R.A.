# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The firewall restarted or shut down (owner, 2026-10-28: «una routine che proceda con il restart del firewall…
abilitare lo spegnimento anche dei firewall quando l'ups è in batteria critica»).

Sophos: its XML API has neither, its console has both. Aurora signs in over SSH as the console's account
(AURORA_FIREWALL_SSH_USER, the default admin: the only one the console takes) with a key of its own
(AURORA_FIREWALL_SSH_KEY, RSA: Sophos refuses ED25519) the owner added under Administration → Device access; menu 4
(Device Console), then `system restart all` or `system shutdown` — neither asks to confirm. Measured 28 Oct: 88 s
without ping, then the API answered. Other kinds: not supported yet (said, nothing done).

restart() waits for the firewall's API to answer again and says how long it was away.
"""
from __future__ import annotations

import os
import re
import select
import time
from pathlib import Path
from urllib.parse import urlparse

from . import sys_config, sys_log

COMMANDS = {"restart": "system restart all", "shutdown": "system shutdown", "test": "exit"}   # test: in and out
BACK_S = 600


class PowerError(RuntimeError):
    pass


def _console(cfg: sys_config.Config, command: str, timeout: float = 40) -> str:
    """The console reached through its menu, one command typed; the screens read, for the log."""
    import pty                                         # not on Windows: the ports say «not supported»
    host = urlparse(str(cfg["AURORA_FIREWALL_API_URL"]).split()[0]).hostname
    key = Path(str(cfg["AURORA_FIREWALL_SSH_KEY"])).expanduser()
    if not host or not key.exists():
        raise PowerError(f"the firewall's console: no address or no key ({key})")
    pid, fd = pty.fork()
    if pid == 0:                                       # the child: ssh with a terminal, the key only, no prompt
        os.execvp("ssh", ["ssh", "-tt", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=8",
                          f"{cfg['AURORA_FIREWALL_SSH_USER']}@{host}"])
    seen = ""

    def read(until: str, seconds: float) -> bool:
        """Waits for `until` in what arrives from now on: an old prompt never answers for a new command."""
        nonlocal seen
        mark, end = len(seen), time.time() + seconds
        while time.time() < end:
            if select.select([fd], [], [], 0.3)[0]:
                try:
                    chunk = os.read(fd, 4096).decode("utf-8", "replace")
                except OSError:
                    return False                       # closed: for a restart, the firewall going down
                if not chunk:
                    return False
                seen += chunk
                if re.search(until, seen[mark:]):
                    return True
        return False

    try:
        if not read(r"Select Menu Number", timeout):
            raise PowerError("the firewall's console did not show its menu: " + seen[-200:].strip())
        os.write(fd, b"4\r")
        if not read(r"console>\s*$", 15):
            raise PowerError("no console prompt after menu 4")
        os.write(fd, (command + "\r").encode())
        read(r"closed|console>\s*$|Select Menu Number", 15)     # gone down, a new prompt, or the menu (exit)
        return seen
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass


def act(cfg: sys_config.Config, action: str) -> None:
    """restart or shutdown, sent; PowerError when it cannot be."""
    if action not in COMMANDS:
        raise PowerError(f"action: one of {', '.join(COMMANDS)}")
    kind = str(cfg["AURORA_FIREWALL_API_KIND"])
    if kind != "sophos":
        raise PowerError(f"restarting a {kind} firewall is not supported yet")
    log = sys_log.get_logger("firewall")
    if action != "test":
        log.warning("audit: firewall %s sent", action)
    _console(cfg, COMMANDS[action])


def restart(cfg: sys_config.Config, wait_s: float = BACK_S) -> dict:
    """Restarted, and its API waited for: {"ok", "away_s"}."""
    from . import sec_fwapi
    start = time.time()
    act(cfg, "restart")
    time.sleep(20)                                     # gone before the first look: never «back» before it went
    while time.time() - start < wait_s:
        try:
            if sec_fwapi.test(cfg).get("ok"):
                return {"ok": True, "away_s": round(time.time() - start)}
        except Exception:  # noqa: BLE001 — away: look again
            pass
        time.sleep(10)
    return {"ok": False, "away_s": round(time.time() - start)}
