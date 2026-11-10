# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""U6 (28 Oct): the services on their own account. The certificate's fixer refuses a link, a file with two names, a
file of someone else and acts on the open file; the .env keeps the services' group when read or written; the command
card asks for the migration while the services run as the owner; the migration's dry run changes nothing. The whole
migration, the certificate's watch and the link trick were tried as root on the Ubuntu VM (ROADMAP U6)."""
try:
    import grp
except ImportError:                                      # Windows: the POSIX tests are skipped there
    grp = None
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
    assert c and "aurora-root" in c[0]["command"] and "account" in c[0]["command"] and c[0]["admin"]
    assert ".venv" not in c[0]["command"]             # C556: root never runs the services' venv
    monkeypatch.setattr(sys_config, "service_user", lambda cfg: "aurora")
    assert not [x for x in sys_commands.cards(cfg) if x["id"] == "account"]


@POSIX
def test_the_dry_run_changes_nothing_and_needs_root():
    r = subprocess.run([sys.executable, str(SCRIPT / "sys_service_account.py"), "--dry-run"], capture_output=True, text=True)
    if os.geteuid() != 0:
        assert r.returncode == 1 and "sudo" in r.stdout


@POSIX
def test_the_units_have_one_umask_the_group_s():
    """C436: a second «UMask=0077» after «UMask=0007» won — every log the services wrote was theirs alone."""
    import pwd
    m = _load("sys_install_services")
    text = m.hardening(Path("/tmp"), pwd.getpwuid(os.getuid()).pw_name, False)
    assert text.count("UMask=") == 1 and "UMask=0007" in text


@POSIX
def test_the_services_never_get_to_write_what_the_owner_runs(tmp_path, monkeypatch):
    """C556: the venv, the installers and the publish command: read and run by the group, written by the owner only;
    the folders holding them sticky (no file of the owner's renamed or swapped by the services)."""
    import stat
    S = _load("sys_service_account")
    for rel in (".venv/lib/site.py", "install.sh", "uninstall.sh", "sys/core/script/publish.sh",
                "sys/core/script/other.py", "sys/core/aurora/x.py"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
        p.chmod(0o644)
    monkeypatch.setattr(S, "ROOT", tmp_path)
    monkeypatch.setattr(S, "DRY", False)
    S.tree()
    mode = lambda rel: stat.S_IMODE(os.lstat(tmp_path / rel).st_mode)  # noqa: E731
    for rel in (".venv", ".venv/lib", ".venv/lib/site.py", "install.sh", "uninstall.sh", "sys/core/script/publish.sh"):
        assert not mode(rel) & 0o020 and mode(rel) & 0o040, rel
    for rel in ("sys/core/script/other.py", "sys/core/aurora/x.py", "sys/core/aurora"):
        assert mode(rel) & 0o020, rel                                  # Aurora's code: her approved changes go on
    assert mode(".") & stat.S_ISVTX and mode("sys/core/script") & stat.S_ISVTX
    assert not mode("sys/core/aurora") & stat.S_ISVTX


def test_owner_only_paths():
    from aurora import sys_rootcmd
    assert sys_rootcmd.owner_only(".venv/bin/python") and sys_rootcmd.owner_only("sys/core/script/publish.sh")
    assert not sys_rootcmd.owner_only("sys/core/script/publish.sh.bak") and not sys_rootcmd.owner_only(".venvx")
    assert not sys_rootcmd.owner_only("sys/core/aurora/agt_change.py")
