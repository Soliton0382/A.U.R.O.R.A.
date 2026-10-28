# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N64: Aurora's own key — the users' keys wrapped by it, its recovery copy, its systemd credential, the cages."""
from __future__ import annotations

import os

import pytest

from aurora import sys_backup, sys_keyring, sys_seal
from conftest import private


@pytest.fixture
def kcfg(cfg, tmp_path, monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    cfg.values.update(AURORA_BACKUP_KEY_FILE=str(tmp_path / "backup.key"))
    return cfg


def test_a_user_s_key_file_alone_opens_nothing(kcfg):
    key = sys_seal._key(kcfg, kcfg.user, "state")
    f = sys_seal.key_file(kcfg, kcfg.user, "state")
    assert len(key) == 32 and key not in f.read_bytes() and f.read_bytes().startswith(sys_keyring.WRAP)
    assert sys_seal._key(kcfg, kcfg.user, "state") == key                       # the same key back
    if os.name != "nt":
        assert private(f) and private(sys_keyring.folder(kcfg) / "aurora.key")


def test_a_key_of_before_is_wrapped_in_place_and_still_opens_its_data(kcfg):
    f = sys_seal.key_file(kcfg, kcfg.user, "health")
    f.parent.mkdir(parents=True, exist_ok=True)
    old = os.urandom(32)
    f.write_bytes(old)                                                          # the format until 29 Oct
    blob = sys_seal.seal(kcfg, b"esame del sangue inventato", "x.sealed", kcfg.user, "health")
    assert old not in f.read_bytes() and sys_seal._key(kcfg, kcfg.user, "health") == old
    assert sys_seal.unseal(kcfg, blob, "x.sealed", kcfg.user, "health") == b"esame del sangue inventato"


def test_the_services_write_the_missing_recovery_copy_and_a_locked_process_does_not(kcfg, monkeypatch):
    assert not sys_keyring.ensure_escrow(kcfg)                                  # no backup key yet
    sys_backup.init_key(kcfg)
    (sys_keyring.folder(kcfg) / "aurora.escrow").unlink()                       # as after the root seal
    assert sys_keyring.ensure_escrow(kcfg) and (sys_keyring.folder(kcfg) / "aurora.escrow").is_file()
    (sys_keyring.folder(kcfg) / "aurora.escrow").unlink()
    monkeypatch.setattr(sys_keyring, "escrow", lambda cfg, key=None: (_ for _ in ()).throw(sys_keyring.Locked("x")))
    assert not sys_keyring.ensure_escrow(kcfg)


def test_the_recovery_copy_gives_the_key_back_with_the_backup_s_key(kcfg):
    sys_backup.init_key(kcfg)
    first = sys_keyring.own_key(kcfg)
    assert sys_keyring.escrow(kcfg)
    f = sys_keyring.folder(kcfg) / "aurora.key"
    f.write_bytes(os.urandom(32))                                               # a restore elsewhere: the file lost
    sys_keyring._cache.clear()
    sys_keyring.recover(kcfg)
    assert f.read_bytes() == first


def test_a_sealed_key_is_never_replaced_by_a_new_one(kcfg):
    folder = sys_keyring.folder(kcfg)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "aurora.sealed").write_text("/etc/credstore.encrypted/aurora-key-x\n")
    sys_keyring._cache.clear()
    with pytest.raises(sys_keyring.Locked):
        sys_keyring.own_key(kcfg)
    assert not (folder / "aurora.key").exists()


def test_the_services_read_the_credential_systemd_opened_for_them(kcfg, tmp_path, monkeypatch):
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / sys_keyring.CRED).write_bytes(b"k" * 32)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(creds))
    sys_keyring._cache.clear()
    assert sys_keyring.where(kcfg) == "credential" and sys_keyring.own_key(kcfg) == b"k" * 32
    sys_keyring._cache.clear()


def test_a_caged_plugin_gets_its_own_store_s_key_only(kcfg, monkeypatch):
    from aurora import plg_host
    assert set(plg_host.SEAL_KEYS) == {"calendar", "health", "diary", "push", "expenses", "routines"}                   # never the memory's or the state's
    k = sys_seal._key(kcfg, kcfg.user, "calendar")
    monkeypatch.setenv("AURORA_SEAL_KEY_CALENDAR", k.hex())
    assert sys_seal._key(kcfg, kcfg.user, "calendar") == k


def test_two_installations_never_share_a_sealed_key(tmp_path):
    from types import SimpleNamespace
    one, two = (SimpleNamespace(base=None, root=tmp_path / n) for n in ("a", "b"))
    assert sys_keyring.cred_path(one).parent == sys_keyring.CREDSTORE
    assert sys_keyring.cred_path(one) != sys_keyring.cred_path(two)


@pytest.fixture
def fake_creds(kcfg, tmp_path, monkeypatch):
    """systemd-creds as a stand-in (a prefix naming the binding), run «as root» into a credstore of the test."""
    import pwd
    import subprocess
    store = tmp_path / "credstore"
    monkeypatch.setattr(sys_keyring, "CREDSTORE", store)
    monkeypatch.setattr(sys_keyring.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys_keyring.os, "chown", lambda *a: None)
    monkeypatch.setattr(pwd, "getpwnam", lambda n: pwd.getpwuid(os.getuid()))
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[1] == "encrypt":
            how = next(a for a in cmd if a.startswith("--with-key=")).split("=", 1)[1]
            from pathlib import Path
            Path(cmd[-1]).write_bytes(how.encode() + b"|" + Path(cmd[-2]).read_bytes())
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        from pathlib import Path
        return subprocess.CompletedProcess(cmd, 0, Path(cmd[-2]).read_bytes().split(b"|", 1)[1], b"")
    monkeypatch.setattr(sys_keyring.subprocess, "run", run)
    monkeypatch.setenv("RUNTIME_DIRECTORY", str(tmp_path))
    sys_keyring._cache.clear()
    return calls


def test_the_key_is_bound_to_a_working_tpm_and_to_the_host_key_alone_without_one(kcfg, fake_creds, monkeypatch):
    monkeypatch.setattr(sys_keyring, "tpm", lambda: True)
    key = sys_keyring.own_key(kcfg)
    assert sys_keyring.seal_host(kcfg) == "sealed (host+tpm2)" and sys_keyring.bound(kcfg) == "host+tpm2"
    assert sys_keyring.cred_path(kcfg).read_bytes() == b"host+tpm2|" + key
    assert "--tpm2-pcrs=" in next(c for c in fake_creds if c[1] == "encrypt")    # no PCR: a firmware update never locks it
    assert not (sys_keyring.folder(kcfg) / "aurora.key").exists()
    assert sys_keyring.seal_host(kcfg) == "already sealed (host+tpm2)"


def test_a_key_sealed_before_the_tpm_worked_is_sealed_again_with_it(kcfg, fake_creds, monkeypatch):
    monkeypatch.setattr(sys_keyring, "tpm", lambda: False)
    key = sys_keyring.own_key(kcfg)
    assert sys_keyring.seal_host(kcfg) == "sealed (host)"
    (sys_keyring.folder(kcfg) / "aurora.sealed").write_text(f"{sys_keyring.cred_path(kcfg)}\n")   # a marker of before
    assert sys_keyring.bound(kcfg) == "host" and sys_keyring.seal_host(kcfg) == "already sealed (host)"
    monkeypatch.setattr(sys_keyring, "tpm", lambda: True)
    assert sys_keyring.seal_host(kcfg) == "sealed again with the TPM"
    assert sys_keyring.cred_path(kcfg).read_bytes() == b"host+tpm2|" + key and sys_keyring.bound(kcfg) == "host+tpm2"
    from pathlib import Path
    assert not list(Path(os.environ["RUNTIME_DIRECTORY"]).glob("aurora-key-*"))   # the opened key not left in /run
