# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Sealed files for a user's most private data — health first (owner, 2026-10-05): diet plans, training, medical exams.

AES-256-GCM (the `cryptography` library, the same primitive the backup uses), one key per user: 32 random bytes in the
user's state folder (<AURORA_STATUS_DIR>/users/<name>/keys/<purpose>.key, mode 600), apart from the data it opens
(usr/<name>/...); both are in the encrypted backup, so a restore opens them again. A sealed file is MAGIC + a 12-byte
nonce + the ciphertext with its tag; the file's own name is bound to it (associated data), so a file renamed or swapped
does not open. What this protects: the data at rest — another user's processes, a stolen copy of the folder, a
misplaced file. It does not protect against root on this machine, who can read the key: said plainly.
The owner's own post-quantum scheme stays his (owner, 2026-10-05): a cipher here can be swapped by its MAGIC later.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import sys_config, sys_users_layout as L

MAGIC = b"AURSEAL1"


def _key(cfg: sys_config.Config, user: str | None, purpose: str) -> bytes:
    d = L.place(cfg, "state", user) / "keys"
    f = d / f"{purpose}.key"
    if not f.exists():
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as h:
            h.write(os.urandom(32))
    k = f.read_bytes()
    if len(k) != 32:
        raise RuntimeError(f"{f} is not a 32-byte key")
    return k


def seal(cfg: sys_config.Config, data: bytes, label: str, user: str | None = None, purpose: str = "health") -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_key(cfg, user, purpose)).encrypt(nonce, data, label.encode())


def unseal(cfg: sys_config.Config, blob: bytes, label: str, user: str | None = None, purpose: str = "health") -> bytes:
    """The data back; ValueError when it is not sealed here, was changed, or belongs to another name."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 12 + 16:
        raise ValueError("not a sealed file")
    try:
        return AESGCM(_key(cfg, user, purpose)).decrypt(blob[len(MAGIC):len(MAGIC) + 12], blob[len(MAGIC) + 12:], label.encode())
    except InvalidTag:
        raise ValueError("the sealed file does not open: changed, or not this user's") from None


def write(cfg: sys_config.Config, path: Path, data: bytes, user: str | None = None, purpose: str = "health") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as h:
        h.write(seal(cfg, data, path.name, user, purpose))
    os.replace(tmp, path)
    return path


def read(cfg: sys_config.Config, path: Path, user: str | None = None, purpose: str = "health") -> bytes:
    return unseal(cfg, path.read_bytes(), path.name, user, purpose)
