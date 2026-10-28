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
# Sealed like Aurora's own key (C461, 29 Oct 2026: a plain file on the same disk opened the escrow, so a stolen disk
# opened everything): the installer, as root, makes it a systemd credential bound to this machine and its TPM
# (sys_keyring), given to the units that use it by the same drop-in, and destroys the file and the owner's copy;
# backup.key.sealed beside it says so. A terminal, which systemd gives nothing, uses the recovery code (use_code).
CRED = "aurora-backup-key"
_given: list[bytes] = []                                 # the key from a recovery code typed in this process


def key_path(cfg: sys_config.Config) -> Path:
    return Path(os.path.expanduser(str(cfg["AURORA_BACKUP_KEY_FILE"])))


def marker(cfg: sys_config.Config) -> Path:
    return key_path(cfg).with_name(key_path(cfg).name + ".sealed")


def cred_path(cfg: sys_config.Config) -> Path:
    from . import sys_keyring
    return sys_keyring.cred_path(cfg).with_name(sys_keyring.cred_path(cfg).name.replace(sys_keyring.CRED, CRED, 1))


def has_key(cfg: sys_config.Config) -> bool:
    """Whether this installation has a backup key: a file, or sealed for the services (this process may not hold it)."""
    return key_path(cfg).is_file() or marker(cfg).exists() or _held() is not None


def _held() -> bytes | None:
    d = os.environ.get("CREDENTIALS_DIRECTORY", "")
    f = Path(d) / CRED if d else None
    return f.read_bytes() if f is not None and f.is_file() else None


def use_code(code: str) -> None:
    """The key from its recovery code, for the rest of this process (a terminal: sys_restore.py --code)."""
    raw = key_from_code(code)
    if len(raw) != 32:
        raise BackupError("that is not a backup recovery code")
    _given[:] = [raw]


def init_key(cfg: sys_config.Config) -> str:
    """Make the key (once) and return its recovery code; an existing key is never replaced."""
    p = key_path(cfg)
    if p.exists() or marker(cfg).exists():
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
    """The key: a recovery code typed here, the credential systemd opened for this service, or the file."""
    held = _given[0] if _given else _held()
    if held is not None:
        if len(held) != 32:
            raise BackupError("the backup's sealed key is not 32 bytes")
        return held
    p = key_path(cfg)
    if not p.is_file() and marker(cfg).exists():
        raise BackupError("the backup's key is sealed for Aurora's services: give its recovery code (--code)")
    if not p.is_file():
        raise BackupError(f"no backup key ({p}): run `sys_backup.py init` once, and keep the recovery code safe")
    raw = p.read_bytes()
    if len(raw) != 32:
        raise BackupError(f"{p} is not a backup key (32 bytes)")
    return raw



def seal_host(cfg: sys_config.Config, owner_home: Path | None = None) -> str:
    """As root (the installer): the key file becomes a systemd credential (host+tpm2 when the TPM works), checked,
    then the file destroyed, and the owner's own copy too when it is the same key. A key sealed with the host key
    alone is sealed again with the TPM once it works. Returns what was done."""
    import pwd
    import subprocess
    from . import sys_keyring as K
    if os.geteuid() != 0:
        raise PermissionError("seal-host needs root")
    svc = pwd.getpwnam(sys_config.service_user(cfg))
    raw = str(cfg["AURORA_BACKUP_KEY_FILE"])           # «~» is the services' account's home, not root's (C456)
    f = Path(svc.pw_dir) / raw[2:] if raw.startswith("~/") else Path(raw)
    cred, mark = cred_path(cfg), f.with_name(f.name + ".sealed")
    if mark.exists() and cred.exists():
        lines = mark.read_text().splitlines()
        if (lines[1] if len(lines) > 1 else "host") == "host+tpm2" or not K.tpm():
            done = "already sealed"
        else:
            key = subprocess.run(["systemd-creds", "decrypt", f"--name={CRED}", str(cred), "-"], check=True,
                                 capture_output=True).stdout
            mem = Path(os.environ.get("RUNTIME_DIRECTORY") or "/run") / f"aurora-backup-key-{os.getpid()}"   # in memory
            fd = os.open(mem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as h:
                    h.write(key)
                _seal_checked(mem, cred, "host+tpm2", key)
            finally:
                K._shred(mem)
            K._write_private(mark, f"{cred}\nhost+tpm2\n".encode())
            os.chown(mark, svc.pw_uid, svc.pw_gid)
            done = "sealed again with the TPM"
    elif not f.is_file():
        return "no backup key yet"
    else:
        key = f.read_bytes()
        if len(key) != 32:
            raise BackupError(f"{f} is not a backup key (32 bytes)")
        K.CREDSTORE.mkdir(mode=0o700, exist_ok=True)
        with_key = "host+tpm2" if K.tpm() else "host"
        _seal_checked(f, cred, with_key, key)
        K._write_private(mark, f"{cred}\n{with_key}\n".encode())
        os.chown(mark, svc.pw_uid, svc.pw_gid)
        K._shred(f)
        done = f"sealed ({with_key})"
    mine = Path(owner_home) / ".config" / "aurora" / "backup.key" if owner_home else None
    if mine is not None and mine.is_file() and mine.resolve() != f.resolve():
        held = subprocess.run(["systemd-creds", "decrypt", f"--name={CRED}", str(cred), "-"], check=True,
                              capture_output=True).stdout
        if mine.read_bytes() == held:                    # the same key: the plain copy goes (the code opens it)
            K._shred(mine)
            note = mine.with_name(mine.name + ".sealed")     # so that an init here never makes a second key
            note.write_text(f"{cred}\nsealed for Aurora's services: use the recovery code (--code)\n")
            st = mine.parent.stat()
            os.chown(note, st.st_uid, st.st_gid)
            done += "; the owner's plain copy destroyed"
        else:
            done += f"; {mine} is another key: left as it is"
    return done


def _seal_checked(src: Path, cred: Path, with_key: str, key: bytes) -> None:
    import subprocess
    from . import sys_keyring as K
    tmp = cred.with_suffix(".tmp")
    K._encrypt(src, tmp, with_key, CRED)
    back = subprocess.run(["systemd-creds", "decrypt", f"--name={CRED}", str(tmp), "-"], check=True,
                          capture_output=True).stdout
    if back != key:
        tmp.unlink()
        raise BackupError("the sealed backup key does not give the same key back: nothing changed")
    os.chmod(tmp, 0o600)
    os.replace(tmp, cred)

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
