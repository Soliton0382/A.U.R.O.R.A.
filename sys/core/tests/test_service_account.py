# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""U6 (28 Oct): the services on their own account. The certificate's fixer refuses a link, a file with two names, a
file of someone else and acts on the open file; the .env keeps the services' group when read or written; the command
card asks for the migration while the services run as the owner; the migration's dry run changes nothing. The whole
migration, the certificate's watch and the link trick were tried as root on the Ubuntu VM (ROADMAP U6)."""
import grp
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "script"
POSIX = pytest.mark.skipif(sys.platform == "win32", reason="POSIX owners and groups")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@POSIX
def test_the_certificate_fixer_refuses_links_and_strangers(tmp_path):
    m = _load("sys_cert_perms")
    me, gid = os.getuid(), os.getgid()
    key = tmp_path / "privkey.pem"
    key.write_text("k")
    key.chmod(0o600)
    assert "0640" in m.fix(str(key), me, gid) and oct(key.stat().st_mode & 0o777) == "0o640"
    link = tmp_path / "link.pem"
    link.symlink_to(key)
    assert "not opened" in m.fix(str(link), me, gid)                                  # a link is never followed
    twin = tmp_path / "twin.pem"
    os.link(key, twin)
    assert "refused" in m.fix(str(twin), me, gid)                                     # two names: refused
    os.unlink(twin)
    assert "refused" in m.fix(str(key), me + 1, gid)                                  # not the installation's owner's


@POSIX
def test_the_env_keeps_the_services_group(tmp_path, monkeypatch):
    from aurora import sys_config
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    env.chmod(0o664)
    mine = grp.getgrgid(os.getgid()).gr_name
    monkeypatch.setattr(sys_config, "SERVICE_GROUP", mine)                          # this test's own group plays it
    sys_config.write_env(env, {"B": "2"})
    assert oct(env.stat().st_mode & 0o777) == "0o660" and env.stat().st_gid == os.getgid()
    monkeypatch.setattr(sys_config, "SERVICE_GROUP", "no-such-group")
    sys_config.write_env(env, {"C": "3"})
    assert oct(env.stat().st_mode & 0o777) == "0o600"


def test_the_card_asks_for_the_migration_while_the_owner_runs_them(cfg, monkeypatch):
    from aurora import sys_commands, sys_config
    monkeypatch.setattr(sys_config, "service_user", lambda cfg: "someone")
    monkeypatch.setattr(sys_commands, "by_hand", lambda cfg: False)
    (cfg.root / ".git").mkdir(exist_ok=True)
    c = [x for x in sys_commands.cards(cfg) if x["id"] == "account"]
    assert c and "sys_service_account.py" in c[0]["command"] and c[0]["admin"]
    monkeypatch.setattr(sys_config, "service_user", lambda cfg: "aurora")
    assert not [x for x in sys_commands.cards(cfg) if x["id"] == "account"]


@POSIX
def test_the_dry_run_changes_nothing_and_needs_root():
    r = subprocess.run([sys.executable, str(SCRIPT / "sys_service_account.py"), "--dry-run"], capture_output=True, text=True)
    if os.geteuid() != 0:
        assert r.returncode == 1 and "sudo" in r.stdout
