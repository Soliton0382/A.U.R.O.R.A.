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
