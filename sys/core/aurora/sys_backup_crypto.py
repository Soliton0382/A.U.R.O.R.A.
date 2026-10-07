# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The backup's key and encryption (moved from sys_backup, 7 October 2026: one module per part): the owner's key and
its recovery code, the sub-keys, and the streams in frames of AES-256-GCM with the last one marked (a cut file is
refused)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
from pathlib import Path

from . import sys_config
from .sys_backup import FRAME, MAGIC, BackupError


# ---- key ------------------------------------------------------------------------------------------
def key_path(cfg: sys_config.Config) -> Path:
    return Path(os.path.expanduser(str(cfg["AURORA_BACKUP_KEY_FILE"])))


def init_key(cfg: sys_config.Config) -> str:
    """Make the key (once) and return its recovery code; an existing key is never replaced."""
    p = key_path(cfg)
    if p.exists():
        raise BackupError(f"{p} exists: a backup key is never replaced (the old snapshots would become unreadable)")
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = os.urandom(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    return recovery_code(raw)


def recovery_code(raw: bytes) -> str:
    code = base64.b32encode(raw).decode().rstrip("=")
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def key_from_code(code: str) -> bytes:
    s = code.replace("-", "").replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def load_key(cfg: sys_config.Config) -> bytes:
    p = key_path(cfg)
    if not p.is_file():
        raise BackupError(f"no backup key ({p}): run `sys_backup.py init` once, and keep the recovery code safe")
    raw = p.read_bytes()
    if len(raw) != 32:
        raise BackupError(f"{p} is not a backup key (32 bytes)")
    return raw


def _subkeys(raw: bytes) -> tuple[bytes, bytes]:
    """One key to encrypt, one to name the blobs (the name says nothing about the content without the key)."""
    return (hmac.new(raw, b"aurora-backup-encrypt", hashlib.sha256).digest(),
            hmac.new(raw, b"aurora-backup-blob-id", hashlib.sha256).digest())


# ---- encryption: frames of AES-256-GCM, the last one marked (a cut file is refused) ---------------
def encrypt_stream(src, dst, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aes, prefix = AESGCM(key), os.urandom(8)
    dst.write(MAGIC + prefix)
    i, chunk = 0, src.read(FRAME)
    while True:
        nxt = src.read(FRAME) if chunk else b""
        last = not nxt
        ct = aes.encrypt(prefix + struct.pack(">I", i), chunk, struct.pack(">I?", i, last))
        dst.write(struct.pack(">I", len(ct)) + ct)
        if last:
            return
        i, chunk = i + 1, nxt


def decrypt_stream(src, dst, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    head = src.read(len(MAGIC) + 8)
    if head[:len(MAGIC)] != MAGIC:
        raise BackupError("not an Aurora backup file")
    aes, prefix, i = AESGCM(key), head[len(MAGIC):], 0
    while True:
        n = src.read(4)
        if len(n) < 4:
            raise BackupError("the file is cut short: its last part is missing")
        ct = src.read(struct.unpack(">I", n)[0])
        try:
            pt = aes.decrypt(prefix + struct.pack(">I", i), ct, struct.pack(">I?", i, False))
            last = False
        except Exception:                               # noqa: BLE001 - the same frame, read as the last one
            try:
                pt = aes.decrypt(prefix + struct.pack(">I", i), ct, struct.pack(">I?", i, True))
                last = True
            except Exception as e:                      # noqa: BLE001
                raise BackupError("wrong key, or the file was changed") from e
        dst.write(pt)
        if last:
            if src.read(1):
                raise BackupError("data after the last part")
            return
        i += 1


def _encrypt_bytes(data: bytes, key: bytes) -> bytes:
    import io
    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out, key)
    return out.getvalue()


def _decrypt_bytes(data: bytes, key: bytes) -> bytes:
    import io
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(data), out, key)
    return out.getvalue()
