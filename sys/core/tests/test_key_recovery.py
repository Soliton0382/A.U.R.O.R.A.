# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔑 The recovery code of Aurora's own key (sys_key_recovery, N64): Argon2id and AES-256-GCM."""
from __future__ import annotations

import pytest

from aurora import sys_key_recovery as R
from aurora import sys_keyring


@pytest.fixture
def kcfg(cfg, monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(R, "_local", lambda: None)          # the published cipher, whatever this machine adds
    monkeypatch.setattr(R, "PARAMS", (1, 1, 8 * 1024))      # the test's own Argon2id: quick (the file says which)
    sys_keyring._cache.clear()
    return cfg


def test_the_code_brings_her_key_back_on_another_machine(kcfg, tmp_path):
    key = sys_keyring.own_key(kcfg)
    code = R.make(kcfg)
    assert len(R.normal(code)) == R.LENGTH and set(R.normal(code)) <= set(R.ALPHABET)
    blob = R.path(kcfg).read_bytes()
    assert blob.startswith(R.MAGIC) and key not in blob and R.normal(code).encode() not in blob
    (sys_keyring.folder(kcfg) / "aurora.key").unlink()                  # the machine lost: the backup's file only
    sys_keyring._cache.clear()
    copy = tmp_path / "from-backup.recovery"
    copy.write_bytes(blob)
    f = R.recover(kcfg, code.lower().replace("-", " "), copy)           # typed by hand
    assert f.read_bytes() == key and oct(f.stat().st_mode)[-3:] == "600"


def test_a_wrong_code_opens_nothing_and_a_new_code_retires_the_old(kcfg):
    sys_keyring.own_key(kcfg)
    old = R.make(kcfg)
    assert R.opens(kcfg, old) and not R.opens(kcfg, "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA") and not R.opens(kcfg, "")
    new = R.make(kcfg)
    assert R.opens(kcfg, new) and not R.opens(kcfg, old)
    with pytest.raises(ValueError):
        R.recover(kcfg, old)


def test_a_changed_file_or_its_parameters_open_nothing(kcfg):
    sys_keyring.own_key(kcfg)
    code = R.make(kcfg)
    good = R.path(kcfg).read_bytes()
    for at in (-5, len(R.MAGIC) + 3):                           # the sealed key, the Argon2id parameters
        bad = bytearray(good)
        bad[at] ^= 1
        R.path(kcfg).write_bytes(bytes(bad))
        assert not R.opens(kcfg, code)


def test_a_file_of_a_cipher_not_here_says_so(kcfg):
    sys_keyring.own_key(kcfg)
    R.path(kcfg).write_bytes(b"SLTC" + bytes(200))
    with pytest.raises(ValueError, match="cipher this installation does not have"):
        R.recover(kcfg, "AAAAA")


def test_only_a_process_holding_her_key_makes_a_code(kcfg):
    folder = sys_keyring.folder(kcfg)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "aurora.sealed").write_text("/etc/credstore.encrypted/aurora-key-x\n")
    with pytest.raises(sys_keyring.Locked):
        R.make(kcfg)
    assert not R.path(kcfg).exists()
