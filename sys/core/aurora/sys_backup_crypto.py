# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The backup's key and encryption (moved from sys_backup, 7 October 2026: one module per part): the owner's key and
its recovery code, the sub-keys, and the streams in frames of AES-256-GCM with the last one marked (a cut file is
refused). An installation may add a layer of its own inside the frames (aurora.local.backup_layer()): each frame
passes through it before AES-256-GCM, whose security the backup rests on; a file says by its first bytes which it
was made with, and one made with a layer this installation does not have is refused by name."""
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
    try:                                               # N64: Aurora's key's recovery copy, now that there is a backup key
        from . import sys_keyring
        sys_keyring.escrow(cfg)
    except Exception:                                  # noqa: BLE001 — sealed for the services and not one of them: later
        pass
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
def _layer():
    """This installation's own layer inside the frames, if it has one: MAGIC (as long as MAGIC), NONCE (its length),
    key(the backup's encryption key) and xor(layer key, nonce, frame index, data)."""
    try:
        from aurora import local                       # ImportError, not only ModuleNotFoundError (C267)
    except ImportError:
        return None
    return getattr(local, "backup_layer", lambda: None)()


def encrypt_stream(src, dst, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    layer = _layer()
    aes, prefix = AESGCM(key), os.urandom(8)
    nonce, lk = (os.urandom(layer.NONCE), layer.key(key)) if layer else (b"", b"")
    dst.write((layer.MAGIC if layer else MAGIC) + prefix + nonce)
    i, chunk = 0, src.read(FRAME)
    while True:
        nxt = src.read(FRAME) if chunk else b""
        last = not nxt
        body = layer.xor(lk, nonce, i, chunk) if layer else chunk
        ct = aes.encrypt(prefix + struct.pack(">I", i), body, struct.pack(">I?", i, last) + nonce)   # the nonce bound
        dst.write(struct.pack(">I", len(ct)) + ct)
        if last:
            return
        i, chunk = i + 1, nxt


def decrypt_stream(src, dst, key: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    head, layer = src.read(len(MAGIC)), None
    if head != MAGIC:
        layer = _layer()
        if layer is None or head != layer.MAGIC:
            raise BackupError("made with a layer this installation does not have (README, the restore steps)"
                              if head.startswith(MAGIC[:3]) else "not an Aurora backup file")
    prefix = src.read(8)
    nonce = src.read(layer.NONCE) if layer else b""
    lk = layer.key(key) if layer else b""
    aes, i = AESGCM(key), 0
    while True:
        n = src.read(4)
        if len(n) < 4:
            raise BackupError("the file is cut short: its last part is missing")
        ct = src.read(struct.unpack(">I", n)[0])
        try:
            pt = aes.decrypt(prefix + struct.pack(">I", i), ct, struct.pack(">I?", i, False) + nonce)
            last = False
        except Exception:                               # noqa: BLE001 - the same frame, read as the last one
            try:
                pt = aes.decrypt(prefix + struct.pack(">I", i), ct, struct.pack(">I?", i, True) + nonce)
                last = True
            except Exception as e:                      # noqa: BLE001
                raise BackupError("wrong key, or the file was changed") from e
        dst.write(layer.xor(lk, nonce, i, pt) if layer else pt)
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
