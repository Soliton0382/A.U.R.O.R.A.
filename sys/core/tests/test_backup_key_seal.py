# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C461: the backup's key sealed like Aurora's own — no plain copy left on the disk, the services given it by systemd,
a terminal opening it with the recovery code."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import sys_backup as B
from aurora import sys_backup_crypto as bc
from aurora import sys_keyring


@pytest.fixture
def sealing(cfg, tmp_path, monkeypatch):
    """systemd-creds as a stand-in, run «as root», the services' home and the owner's in the test's folder."""
    svc_home, owner = tmp_path / "svc", tmp_path / "owner"
    for h in (svc_home, owner):
        (h / ".config" / "aurora").mkdir(parents=True)
    cfg.values.update(AURORA_BACKUP_KEY_FILE="~/.config/aurora/backup.key")
    monkeypatch.setenv("HOME", str(svc_home))
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setenv("RUNTIME_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(sys_keyring, "CREDSTORE", tmp_path / "credstore")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda *a: None)
    import pwd
    monkeypatch.setattr(pwd, "getpwnam", lambda n: SimpleNamespace(pw_dir=str(svc_home), pw_uid=os.getuid(), pw_gid=os.getgid()))
    monkeypatch.setattr(sys_keyring, "tpm", lambda: True)
    real = subprocess.run

    def run(cmd, **kw):
        if cmd[0] != "systemd-creds":
            return real(cmd, **kw)
        if cmd[1] == "encrypt":
            how = next(a for a in cmd if a.startswith("--with-key=")).split("=", 1)[1]
            Path(cmd[-1]).write_bytes(how.encode() + b"|" + Path(cmd[-2]).read_bytes())
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return subprocess.CompletedProcess(cmd, 0, Path(cmd[-2]).read_bytes().split(b"|", 1)[1], b"")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(bc, "_given", [])
    code = B.init_key(cfg)
    (owner / ".config/aurora/backup.key").write_bytes(B.key_path(cfg).read_bytes())    # the owner's copy (28 Oct)
    return SimpleNamespace(cfg=cfg, code=code, owner=owner, key=B.key_path(cfg).read_bytes(), tmp=tmp_path)


def test_the_key_is_sealed_with_the_tpm_and_no_plain_copy_is_left(sealing):
    cfg = sealing.cfg
    out = bc.seal_host(cfg, sealing.owner)
    assert out.startswith("sealed (host+tpm2)") and "owner's plain copy destroyed" in out
    assert not B.key_path(cfg).exists() and not (sealing.owner / ".config/aurora/backup.key").exists()
    assert bc.cred_path(cfg).read_bytes() == b"host+tpm2|" + sealing.key and bc.cred_path(cfg).name.startswith("aurora-backup-key-")
    assert B.has_key(cfg) and (sealing.owner / ".config/aurora/backup.key.sealed").exists()
    assert bc.seal_host(cfg, sealing.owner) == "already sealed"


def test_the_services_read_it_from_systemd_and_a_terminal_from_the_code(sealing, monkeypatch):
    cfg = sealing.cfg
    bc.seal_host(cfg, sealing.owner)
    with pytest.raises(B.BackupError, match="recovery code"):
        B.load_key(cfg)                                 # a terminal: systemd gave it nothing
    with pytest.raises(B.BackupError, match="never replaced"):
        B.init_key(cfg)                                 # never a second key beside the sealed one
    creds = sealing.tmp / "creds"
    creds.mkdir()
    (creds / bc.CRED).write_bytes(sealing.key)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(creds))
    assert B.load_key(cfg) == sealing.key               # a service with the drop-in
    monkeypatch.delenv("CREDENTIALS_DIRECTORY")
    B.use_code(sealing.code)
    assert B.load_key(cfg) == sealing.key               # sys_restore.py --code


def test_an_owner_s_copy_that_is_another_key_is_left_as_it_is(sealing):
    (sealing.owner / ".config/aurora/backup.key").write_bytes(os.urandom(32))
    assert "another key: left as it is" in bc.seal_host(sealing.cfg, sealing.owner)
    assert (sealing.owner / ".config/aurora/backup.key").exists()


def test_a_key_sealed_before_the_tpm_worked_is_sealed_again_with_it(sealing, monkeypatch):
    monkeypatch.setattr(sys_keyring, "tpm", lambda: False)
    assert bc.seal_host(sealing.cfg).startswith("sealed (host)")
    monkeypatch.setattr(sys_keyring, "tpm", lambda: True)
    assert bc.seal_host(sealing.cfg) == "sealed again with the TPM"
    assert bc.cred_path(sealing.cfg).read_bytes() == b"host+tpm2|" + sealing.key
