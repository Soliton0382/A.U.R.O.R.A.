# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔑 The recovery code of Aurora's own key (owner, 29 Oct 2026: «vai con A, il codice di ripristino»; N64).

A second way back to her key (sys_keyring), independent of the escrow and the backup's key: her key sealed with a
code — Argon2id (64 MiB, 3 passes, 4 lanes; the parameters in the file) then AES-256-GCM — in
<STATUS>/keys/aurora.recovery, which the backup carries. The code (25 characters from 31, about 124 bits, no
look-alike letters) is made here, shown once on the page (⚙️ System → 🔑 Keys and recovery) and written nowhere:
whoever has the code and a backup opens the users' data, as with the backup's key. A new code replaces the file, so
the old one opens nothing after it.

An installation may seal it with a cipher of its own (aurora.local.recovery_cipher(): seal(key, code) and
open(blob, code)); a file opens by its first bytes, whichever made it.

  python -m aurora.sys_key_recovery recover [file]   after a restore on another machine: the code asked, her key
                                                     back as a file (keys/aurora.key), sealed again by the installer
"""
from __future__ import annotations

import os
import secrets
import struct
import sys
from pathlib import Path

from . import sys_config, sys_keyring

FILE = "aurora.recovery"
MAGIC = b"AURREC1"
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"            # no I, L, O, 0, 1: read aloud or copied by hand
LENGTH, GROUP = 25, 5
PARAMS = (3, 4, 64 * 1024)                              # Argon2id: passes, lanes, KiB
_HEAD = struct.Struct(">III")


def path(cfg: sys_config.Config) -> Path:
    return sys_keyring.folder(cfg) / FILE


def normal(code: str) -> str:
    """The code as typed (lower case, spaces, dashes) back to its characters."""
    return "".join(c for c in str(code or "").upper() if c in ALPHABET)


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return "-".join(raw[i:i + GROUP] for i in range(0, LENGTH, GROUP))


def _local():
    """This installation's own cipher for the recovery file, if it has one."""
    try:
        from aurora import local                       # ImportError, not only ModuleNotFoundError (C267)
    except ImportError:
        return None
    return getattr(local, "recovery_cipher", lambda: None)()


def _kek(code: str, salt: bytes, params: tuple[int, int, int]) -> bytes:
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    it, lanes, mem = params
    if not (1 <= it <= 10 and 1 <= lanes <= 16 and 8 * 1024 <= mem <= 1024 * 1024):
        raise ValueError("the recovery file asks for Argon2id parameters out of range")
    return Argon2id(salt=salt, length=32, iterations=it, lanes=lanes, memory_cost=mem).derive(normal(code).encode())


def seal(key: bytes, code: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(16), os.urandom(12)
    head = MAGIC + _HEAD.pack(*PARAMS) + salt + nonce
    return head + AESGCM(_kek(code, salt, PARAMS)).encrypt(nonce, key, head)


def open_blob(blob: bytes, code: str) -> bytes:
    """Her key from a recovery file (ValueError: a wrong code, a changed file, or a cipher not here)."""
    if not normal(code):
        raise ValueError("no code")
    if not blob.startswith(MAGIC):
        own = _local()
        if own is None:
            raise ValueError("this recovery file was made by a cipher this installation does not have")
        key = own.open(blob, normal(code))
    else:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        n = len(MAGIC) + _HEAD.size
        params, salt, nonce = _HEAD.unpack(blob[len(MAGIC):n]), blob[n:n + 16], blob[n + 16:n + 28]
        try:
            key = AESGCM(_kek(code, salt, params)).decrypt(nonce, blob[n + 28:], blob[:n + 28])
        except InvalidTag:
            raise ValueError("the code does not open the recovery file") from None
    if len(key) != 32:
        raise ValueError("the recovery file does not hold a key")
    return key


def status(cfg: sys_config.Config) -> dict:
    try:
        return {"exists": True, "created": path(cfg).stat().st_mtime}
    except OSError:
        return {"exists": False, "created": None}


def make(cfg: sys_config.Config) -> str:
    """A new code: her key sealed with it, the old file replaced. Only a process holding her key (the services)."""
    code, key = new_code(), sys_keyring.own_key(cfg)
    own = _local()
    sys_keyring._write_private(path(cfg), own.seal(key, normal(code)) if own else seal(key, code))
    return code


def opens(cfg: sys_config.Config, code: str) -> bool:
    """Whether the code opens the recovery file (a check from the page; nothing written)."""
    try:
        return len(open_blob(path(cfg).read_bytes(), code)) == 32
    except (OSError, ValueError):
        return False


def recover(cfg: sys_config.Config, code: str, src: Path | None = None) -> Path:
    """Her key back as a file, from the recovery file (here, or `src`) and the code."""
    key = open_blob((src or path(cfg)).read_bytes(), code)
    f = sys_keyring.folder(cfg) / "aurora.key"
    sys_keyring._write_private(f, key)
    return f


def main(argv: list[str]) -> int:
    if argv[:1] != ["recover"]:
        print("usage: python -m aurora.sys_key_recovery recover [recovery-file]", file=sys.stderr)
        return 2
    import getpass
    cfg = sys_config.get()
    try:
        f = recover(cfg, getpass.getpass("Recovery code: "), Path(argv[1]) if len(argv) > 1 else None)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Aurora's key back in {f}: run the installer to seal it again")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
