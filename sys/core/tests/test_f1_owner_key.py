# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Audit F1: root copies the firewall key named in .env only if it is a regular file of the owner's, never via a link."""
import getpass
import importlib.util
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "script" / "sys_service_account.py"


def _load():
    spec = importlib.util.spec_from_file_location("sas_f1", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_only_a_regular_file_of_the_owner_is_copied_and_never_through_a_link(tmp_path):
    S = _load()
    me = getpass.getuser()
    key = tmp_path / "id"
    key.write_text("k")
    keys = tmp_path / "status" / "keys"
    keys.parent.mkdir()
    S.copy_owner_key(key, keys, me, account=me)
    assert (keys / "firewall_key").read_text() == "k"
    (tmp_path / "link").symlink_to(key)
    with pytest.raises(OSError):
        S.copy_owner_key(tmp_path / "link", keys, me, account=me)
    if os.stat("/etc/hostname").st_uid != os.getuid():
        with pytest.raises(PermissionError):
            S.copy_owner_key(Path("/etc/hostname"), keys, me, account=me)
    target = tmp_path / "elsewhere"
    target.write_text("x")
    (keys / "firewall_key").unlink()
    (keys / "firewall_key").symlink_to(target)               # a link planted at the destination is replaced, not followed
    S.copy_owner_key(key, keys, me, account=me)
    assert target.read_text() == "x" and not (keys / "firewall_key").is_symlink()
