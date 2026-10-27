# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import os
import shutil
import sys

import pytest

from aurora import sys_power_hosts as H

pytestmark = pytest.mark.skipif(not shutil.which("ssh-keygen") or sys.platform == "win32", reason="ssh-keygen")

FAKE = r'''#!/bin/sh
# a stand-in for ssh: the last argument is the word sent; «test» answers ok, the others «closed by remote host»
for a; do last="$a"; done
echo "$@" >> "$0.log"
case "$last" in
  test) echo ok ;;
  *) echo "Connection to host closed by remote host." >&2; exit 255 ;;
esac
'''


def test_a_machine_kept_checked_and_only_counted_once_tried(cfg, tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        H.put(cfg, {"name": "x", "host": "a b", "user": "u"})
    with pytest.raises(ValueError):
        H.put(cfg, {"name": "x", "host": "10.0.0.5", "user": "u; rm"})
    h = H.put(cfg, {"name": "Mini PC", "host": "10.0.0.5", "user": "pi", "ups_off": True})
    assert h["port"] == "22" and h["os"] == "linux" and H.ups_targets(cfg) == []      # not tried yet: not counted
    ssh = tmp_path / "ssh"
    ssh.write_text(FAKE)
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert H.test(cfg, h["id"])["ok"] and [x["name"] for x in H.ups_targets(cfg)] == ["Mini PC"]
    assert H.run(cfg, h, "shutdown")["ok"]                                          # the connection drops: it went
    log = (tmp_path / "ssh.log").read_text()
    assert "pi@10.0.0.5 test" in log and "pi@10.0.0.5 shutdown" in log and "IdentitiesOnly=yes" in log
    H.put(cfg, {**h, "host": "10.0.0.6"}, h["id"])                                  # another machine: tried again
    assert H.ups_targets(cfg) == [] and H.delete(cfg, h["id"])


def test_the_target_gets_a_key_that_opens_no_shell(cfg):
    s = H.setup(cfg, {"user": "pi", "os": "linux", "name": "x", "host": "h"})
    assert s["authorized_keys"].startswith(f'command="{H.SCRIPT}",no-pty,') and "ssh-ed25519 " in s["authorized_keys"]
    assert s["sudoers"] == "pi ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff"
    assert "*) echo refused; exit 1" in s["script"] and "visudo -cf" in s["commands"][2]
    assert "/home/pi/.ssh/authorized_keys" in s["commands"][3]
    assert "/sbin/shutdown -h now" in H.setup(cfg, {"user": "me", "os": "macos", "name": "x", "host": "h"})["sudoers"]
    assert oct(H.key(cfg).stat().st_mode & 0o777) == "0o600"


def test_each_firewall_has_its_own_ups_tick(cfg):
    from aurora import sec_firewalls
    cfg.values.update({"AURORA_FIREWALL_API_URL": "https://10.0.0.1:4444", "AURORA_FIREWALL_API_USER": "a"})
    assert sec_firewalls.ups_targets(cfg) == []
    sec_firewalls.save(cfg, "main", {"ups_off": True})
    other = sec_firewalls.save(cfg, "new", {"name": "Lab", "kind": "pfsense", "url": "https://10.0.0.2"})["id"]
    assert [x["id"] for x in sec_firewalls.ups_targets(cfg)] == ["main"]
    sec_firewalls.save(cfg, other, {"ups_off": True})
    t = sec_firewalls.ups_targets(cfg)
    assert [x["id"] for x in t] == ["main", other] and t[1]["cfg"]["AURORA_FIREWALL_API_URL"] == "https://10.0.0.2"
