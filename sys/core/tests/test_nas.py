# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The NAS mount writes into /etc/fstab as root: every value it writes is checked, and its line is the only one it
touches."""
import importlib.util
from pathlib import Path

import pytest

from aurora import sys_backup as B

spec = importlib.util.spec_from_file_location("nas", Path(__file__).resolve().parents[1] / "script" / "sys_nas_mount.py")
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)


def test_the_owner_s_address_is_understood_and_nothing_else_gets_through():
    assert N.parse("smb://192.168.1.20/backups/aurora/") == ("192.168.1.20", "backups", "aurora")
    assert N.parse("smb://nas.local/data") == ("nas.local", "data", "")
    assert N.parse("smb://nas/share/a/b") == ("nas", "share", "a/b")
    for bad in ("smb://192.168.1.20", "/mnt/x", "smb://1.2.3.4/share/../etc", "smb://host/sh are/x",
                "smb://host;rm/x", "smb://host/share\n/x", "smb://300.1.1.1/s", "smb://host/share/x y",
                "smb://host/sha,re/x", "smb://-host/s"):
        with pytest.raises(ValueError):
            N.parse(bad)


def test_one_marked_line_replaced_never_duplicated_and_no_password_in_fstab():
    line = N.fstab_line("192.168.1.20", "backups", 1000, 1000)
    assert line.startswith("//192.168.1.20/backups /mnt/aurora-nas cifs ") and line.endswith("# aurora-nas")
    assert "nofail" in line and "x-systemd.automount" in line and "credentials=/etc/aurora/nas.cred" in line
    assert "password" not in line.split(" 0 0")[0]
    fstab = "UUID=x / ext4 defaults 0 1\n//192.168.1.20/media /home/u/media cifs credentials=/h,uid=1000 0 0\n"
    once = N.updated_fstab(fstab, line)
    twice = N.updated_fstab(once, N.fstab_line("10.0.0.2", "backups", 1000, 1000))
    assert twice.count("# aurora-nas") == 1 and "10.0.0.2" in twice and "192.168.1.20/backups" not in twice
    assert "/media /home/u/media" in twice and "UUID=x" in twice                      # the owner's own lines untouched
    assert N.updated_fstab(twice, None) == fstab
    assert N.credentials("nasuser", "p@ss w0rd!") == "username=nasuser\npassword=p@ss w0rd!\n"
    for u, p in (("", "x"), ("a\nb", "x"), ("a", "x\nusername=root")):
        with pytest.raises(ValueError):
            N.credentials(u, p)


def test_a_nas_asleep_is_said_at_once(cfg, monkeypatch):
    cfg.values["AURORA_BACKUP_DIR"] = "smb://192.168.1.20/backups/aurora/"
    monkeypatch.setattr(B, "nas_reachable", lambda url, timeout=1.5: False)
    with pytest.raises(B.BackupError, match="does not answer"):     # C125: never a 10 s wait on a hanging mount
        B.target(cfg)


def test_a_nas_folder_is_used_only_when_the_share_is_mounted(cfg, tmp_path, monkeypatch):
    cfg.values["AURORA_BACKUP_DIR"] = "smb://192.168.1.20/backups/aurora/"
    monkeypatch.setattr(B, "nas_reachable", lambda url, timeout=1.5: True)
    with pytest.raises(B.BackupError, match="not mounted"):
        B.target(cfg, mount=tmp_path / "not-a-mount")          # never the local disk in the NAS's place
    import os
    root_mount = Path("/")                                      # a mount point that exists on every machine
    assert os.path.ismount(root_mount)
    cfg.values["AURORA_BACKUP_DIR"] = "smb://h/share/tmp"
    assert B.target(cfg, mount=root_mount) == Path("/tmp")
