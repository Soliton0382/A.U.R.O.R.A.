# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import os
import sys

import pytest

from aurora import sec_fwpower, sys_routines

FAKE = r'''#!/usr/bin/env python3
# a stand-in for the firewall's console over ssh: the menu, «4», the prompt, one command written down
import sys
log = open(sys.argv[0] + ".log", "a", buffering=1)              # each line kept at once: the hang-up comes fast
log.write(" ".join(sys.argv[1:]) + "\n")
print("Main Menu\n    4.  Device Console\n    Select Menu Number [0-7]: ", end="", flush=True)
if sys.stdin.readline().strip() != "4":
    sys.exit(1)
print("console> ", end="", flush=True)
log.write("typed: " + sys.stdin.readline().strip() + "\n")
print("Connection to fw closed by remote host.", flush=True)
'''


@pytest.mark.skipif(sys.platform == "win32", reason="the console is reached through a terminal (pty)")
def test_the_console_menu_then_the_command(cfg, tmp_path, monkeypatch):
    ssh = tmp_path / "ssh"
    ssh.write_text(FAKE)
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    key = tmp_path / "key"
    key.write_text("k")
    cfg.values.update({"AURORA_FIREWALL_API_KIND": "sophos", "AURORA_FIREWALL_API_URL": "https://10.0.0.1:4444",
                       "AURORA_FIREWALL_SSH_KEY": str(key), "AURORA_FIREWALL_SSH_USER": "admin"})
    sec_fwpower.act(cfg, "restart")
    log = (tmp_path / "ssh.log").read_text()
    assert f"-i {key}" in log and "admin@10.0.0.1" in log and "typed: system restart all" in log


def test_only_what_is_supported_is_sent(cfg):
    cfg.values.update({"AURORA_FIREWALL_API_KIND": "opnsense"})
    with pytest.raises(sec_fwpower.PowerError, match="not supported"):
        sec_fwpower.act(cfg, "restart")
    with pytest.raises(sec_fwpower.PowerError, match="action"):
        sec_fwpower.act(cfg, "reboot-now")


def test_a_firewall_routine_only_restarts():
    sch = {"every": "day", "at": "06:00"}
    assert sys_routines.validate({"kind": "firewall", "title": "x", "schedule": sch})
    with pytest.raises(ValueError):
        sys_routines.validate({"kind": "firewall", "action": "shutdown", "title": "x", "schedule": sch})
