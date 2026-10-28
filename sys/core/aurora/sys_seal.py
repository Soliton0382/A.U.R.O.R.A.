# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Sealed files for a user's most private data — health first (owner, 2026-10-05): diet plans, training, medical exams.

AES-256-GCM (the `cryptography` library, the same primitive the backup uses), one key per user: 32 random bytes in the
user's state folder (<AURORA_STATUS_DIR>/users/<name>/keys/<purpose>.key, mode 600), apart from the data it opens
(usr/<name>/...); both are in the encrypted backup, so a restore opens them again. A sealed file is MAGIC + a 12-byte
nonce + the ciphertext with its tag; the file's own name is bound to it (associated data), so a file renamed or swapped
does not open. What this protects: the data at rest — another user's processes, a stolen copy of the folder, a
misplaced file. Since 29 Oct each key file is wrapped by Aurora's own key (sys_keyring): the file alone opens
nothing. Root on this machine while it runs can still reach it: said plainly.
The owner's own post-quantum scheme stays his (owner, 2026-10-05): a cipher here can be swapped by its MAGIC later.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import sys_config, sys_users_layout as L

MAGIC = b"AURSEAL1"


def key_file(cfg: sys_config.Config, user: str | None, purpose: str) -> Path:
    return L.place(cfg, "state", user) / "keys" / f"{purpose}.key"


def _key(cfg: sys_config.Config, user: str | None, purpose: str) -> bytes:
    """A user's key for one purpose, wrapped by Aurora's own key (sys_keyring, N64): the file alone opens nothing. A
    key of before (32 bytes in plaintext) is wrapped the first time it is used."""
    given = os.environ.get(f"AURORA_SEAL_KEY_{purpose.upper()}", "")
    if given:                                            # a caged plugin: its host gave it this one key, opened (N64)
        return bytes.fromhex(given)
    from . import sys_keyring
    f = key_file(cfg, user, purpose)
    label = f"{f.parent.parent.name}/{purpose}"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        k = os.urandom(32)
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as h:
            h.write(sys_keyring.wrap(cfg, k, label))
        return k
    blob = f.read_bytes()
    if blob.startswith(sys_keyring.WRAP):
        return sys_keyring.unwrap(cfg, blob, label)
    if len(blob) != 32:
        raise RuntimeError(f"{f} is not a 32-byte key")
    tmp = f.with_suffix(".tmp")                          # a key of before: wrapped now, in place
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as h:
        h.write(sys_keyring.wrap(cfg, blob, label))
    os.replace(tmp, f)
    return blob


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


TEXT = "aurseal1:"                                       # one sealed line of text (JSONL files, a column)


def seal_text(cfg: sys_config.Config, text: str, label: str, user: str | None = None, purpose: str = "state") -> str:
    """A string sealed into one line of text (base64), bound to `label` (the file's or the row's name)."""
    import base64
    return TEXT + base64.b64encode(seal(cfg, text.encode("utf-8"), label, user, purpose)).decode("ascii")


def open_text(cfg: sys_config.Config, value: str, label: str, user: str | None = None, purpose: str = "state") -> str:
    """The string back; a value never sealed (written before N64) is given back as it is, for the migration."""
    import base64
    if not isinstance(value, str) or not value.startswith(TEXT):
        return value
    return unseal(cfg, base64.b64decode(value[len(TEXT):]), label, user, purpose).decode("utf-8")


def is_sealed(value) -> bool:
    return isinstance(value, (bytes, str)) and (value[:len(MAGIC)] == MAGIC if isinstance(value, bytes)
                                                else value.startswith(TEXT))


def read_any(cfg: sys_config.Config, path: Path, user: str | None = None, purpose: str = "state") -> bytes:
    """A sealed file's data, or the file as it is when it was written before N64 (sealed at its next write)."""
    blob = path.read_bytes()
    return unseal(cfg, blob, path.name, user, purpose) if blob.startswith(MAGIC) else blob
