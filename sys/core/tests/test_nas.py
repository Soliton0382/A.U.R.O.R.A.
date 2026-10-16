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


def test_the_frames_share_is_read_only_with_its_own_line(tmp_path, monkeypatch):
    line = N.fstab_line("192.168.1.20", "astro", 1000, 1000, N.ASTRO, N.ASTRO_MARK, ro=True)
    assert line.startswith("//192.168.1.20/astro /mnt/aurora-astro cifs ro,") and line.endswith("# aurora-astro")
    backup = N.fstab_line("192.168.1.20", "backups", 1000, 1000)
    both = N.updated_fstab(N.updated_fstab("UUID=x / ext4 defaults 0 1\n", backup), line, N.ASTRO_MARK)
    assert both.count("# aurora-nas") == 1 and both.count("# aurora-astro") == 1      # each replaces only its own
    assert N.updated_fstab(both, None, N.ASTRO_MARK).count("# aurora-nas") == 1


def test_a_nas_frames_folder_is_its_mount_and_a_nas_asleep_is_said(tmp_path, monkeypatch):
    from aurora import ast_frames as F
    assert F.local("/data/lights") == (Path("/data/lights"), "")
    monkeypatch.setattr(B, "nas_reachable", lambda url, timeout=1.5: False)
    assert F.local("smb://192.168.1.20/astro/lights")[0] is None
    monkeypatch.setattr(B, "nas_reachable", lambda url, timeout=1.5: True)
    assert "not mounted" in F.local("smb://192.168.1.20/astro/lights", mount=tmp_path)[1]
    assert F.local("smb://192.168.1.20/astro/lights", mount=Path("/")) == (Path("/lights"), "")


def test_the_frames_folder_of_a_person_is_found_for_the_mount(cfg, tmp_path, monkeypatch):
    from aurora import sys_users_layout as L
    monkeypatch.setattr(L, "usr", lambda c: tmp_path)
    (tmp_path / "anna").mkdir()
    (tmp_path / "anna" / ".env").write_text("AURORA_ASTRO_FRAMES_DIR=smb://192.168.1.20/astro/lights\n")
    cfg.values["AURORA_ASTRO_FRAMES_DIR"] = ""
    assert N.astro_url(cfg) == "smb://192.168.1.20/astro/lights"
    (tmp_path / "anna" / ".env").write_text("AURORA_ASTRO_FRAMES_DIR=/data/lights\n")
    assert N.astro_url(cfg) == ""                                       # a local folder: nothing to mount
