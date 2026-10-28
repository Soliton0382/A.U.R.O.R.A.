# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔐 Aurora's own key (owner, 29 Oct 2026: «facciamo in modo che aurora… si crei una chiave a cui ha accesso solo lei
nella sua cartella… cerchiamo di blindare il più possibile»; ROADMAP N64).

One key of her own of 32 random bytes opens every user's keys (sys_seal: each purpose's key is wrapped by it, AES-256-GCM,
bound to the user and the purpose). Where her key lives, strongest first:
 1. a systemd credential (LoadCredentialEncrypted=aurora-key, a drop-in per service): encrypted by systemd with
    this machine's TPM or its host key (root's), kept in /etc/credstore.encrypted (root's, outside Aurora and its
    backup), never in plaintext on the disk; systemd opens it for Aurora's services only, in a folder in memory
    (/run/credentials/<unit>, hidden from the plugins' cage with all of /run). `seal-host`, run as root by the
    installer, makes it from the file below and destroys the file; keys/aurora.sealed says where it is and how it
    is bound. With a TPM in full working order (systemd-analyze has-tpm2) it is bound to the chip and the host key
    (host+tpm2, no PCR: an update of the firmware does not lock it): a disk taken out of this machine opens nothing;
    without one, the host key alone — on the same disk, so a stolen disk still opens (owner, 29 Oct: «per maggiore
    sicurezza serve il tpm perfettamente funzionante»). A key sealed before the TPM worked is sealed again with it
    the next time the installer runs. A board that dies takes the TPM with it: the escrow below brings the key back.
 2. a file <AURORA_STATUS_DIR>/keys/aurora.key, mode 600, the services' account — made at the first need (an update,
    a new installation), until root seals it; the ports keep it (no systemd).
A recovery copy (aurora.escrow) is her key sealed with the backup's key, which never goes into the backup: a
restore on another machine opens the users' data with the backup's key alone (`recover`).
What this does not stop, said plainly: root on this machine while it runs — Aurora must open the key to work at night.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from . import sys_config

CRED = "aurora-key"
CREDSTORE = Path("/etc/credstore.encrypted")
WRAP = b"AURKEY1"                                        # a user's key wrapped by her key


class Locked(RuntimeError):
    """Her key is sealed for the services and this process is not one of them."""


def folder(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "keys"


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as h:
        h.write(data)
    os.replace(tmp, path)


def cred_path(cfg: sys_config.Config) -> Path:
    """This installation's sealed key (one per Aurora folder: two installations never share it)."""
    return CREDSTORE / f"{CRED}-{hashlib.sha256(str((cfg.base or cfg).root).encode()).hexdigest()[:10]}"


def where(cfg: sys_config.Config) -> str:
    """«credential» (systemd, this process holds it), «sealed» (systemd, not this process), «file», or «none»."""
    d = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if d and (Path(d) / CRED).is_file():
        return "credential"
    if (folder(cfg) / "aurora.sealed").exists():       # the marker, readable by the account (the credential is root's)
        return "sealed"
    return "file" if (folder(cfg) / "aurora.key").is_file() else "none"


_cache: dict[tuple[str, str], bytes] = {}      # (keys folder, where): never another folder's


def own_key(cfg: sys_config.Config) -> bytes:
    """Aurora's own key; made (as a file) the first time. Locked when systemd holds it for the services only."""
    state = where(cfg)
    slot = (str(folder(cfg)), state)
    if slot in _cache:
        return _cache[slot]
    if state == "credential":
        k = (Path(os.environ["CREDENTIALS_DIRECTORY"]) / CRED).read_bytes()
    elif state == "sealed":                              # never a second key of hers beside the sealed one
        raise Locked("Aurora's key is sealed for her services: this process is not one of them")
    else:
        f = folder(cfg) / "aurora.key"
        if state == "none":
            _write_private(f, os.urandom(32))
            escrow(cfg, f.read_bytes())
        k = f.read_bytes()
    if len(k) != 32:
        raise RuntimeError("Aurora's key is not 32 bytes")
    _cache[slot] = k
    return k


def wrap(cfg: sys_config.Config, key: bytes, label: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return WRAP + nonce + AESGCM(own_key(cfg)).encrypt(nonce, key, label.encode())


def unwrap(cfg: sys_config.Config, blob: bytes, label: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        return AESGCM(own_key(cfg)).decrypt(blob[len(WRAP):len(WRAP) + 12], blob[len(WRAP) + 12:], label.encode())
    except InvalidTag:
        raise ValueError(f"the key {label} does not open with Aurora's key") from None


def escrow(cfg: sys_config.Config, key: bytes | None = None) -> bool:
    """The recovery copy, sealed with the backup's key (outside the backup); False when there is no backup key yet."""
    from . import sys_backup as bc            # its crypto, through sys_backup (no import cycle)
    if not bc.key_path(cfg).is_file():
        return False
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    k = hashlib.sha256(bc.load_key(cfg) + b"aurora-key-escrow").digest()
    _write_private(folder(cfg) / "aurora.escrow", WRAP + nonce + AESGCM(k).encrypt(nonce, key or own_key(cfg), b"escrow"))
    return True


def ensure_escrow(cfg: sys_config.Config) -> bool:
    """The recovery copy written when it is missing, by a process that holds her key (the services, at start): the
    seal runs as root, whose home has no backup key, so it cannot write it there. False: not written (no backup key
    yet, or this process is not one of her services)."""
    if (folder(cfg) / "aurora.escrow").is_file():
        return True
    try:
        return escrow(cfg)
    except Locked:
        return False


def recover(cfg: sys_config.Config) -> Path:
    """After a restore on another machine: her key back as a file, from the escrow and the backup's key."""
    from . import sys_backup as bc            # its crypto, through sys_backup (no import cycle)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    blob = (folder(cfg) / "aurora.escrow").read_bytes()
    k = hashlib.sha256(bc.load_key(cfg) + b"aurora-key-escrow").digest()
    key = AESGCM(k).decrypt(blob[len(WRAP):len(WRAP) + 12], blob[len(WRAP) + 12:], b"escrow")
    f = folder(cfg) / "aurora.key"
    _write_private(f, key)
    return f


def _shred(f: Path) -> None:
    with open(f, "r+b") as h:
        h.write(os.urandom(max(f.stat().st_size, 32)))
        h.flush()
        os.fsync(h.fileno())
    f.unlink()


def tpm() -> bool:
    """Whether this machine has a TPM 2.0 in full working order for systemd (firmware, driver, system, libraries)."""
    try:
        return subprocess.run(["systemd-analyze", "has-tpm2", "-q"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def bound(cfg: sys_config.Config) -> str:
    """How the sealed key is bound: «host+tpm2», «host» (sealed before this was written down, or with no TPM), or
    «» when it is not sealed."""
    try:
        lines = (folder(cfg) / "aurora.sealed").read_text().splitlines()
    except OSError:
        return ""
    return lines[1].strip() if len(lines) > 1 and lines[1].strip() else "host"


def _encrypt(src: Path, dst: Path, with_key: str) -> None:
    extra = ["--tpm2-pcrs="] if "tpm2" in with_key else []
    subprocess.run(["systemd-creds", "encrypt", f"--name={CRED}", f"--with-key={with_key}", *extra, str(src), str(dst)],
                   check=True, capture_output=True)


def _reseal_tpm(cfg: sys_config.Config, cred: Path, marker: Path, svc) -> str:
    """A key sealed with the host key alone, now that the TPM works: the same key sealed again with the chip, checked
    before it replaces the old one (which is kept until then)."""
    key = subprocess.run(["systemd-creds", "decrypt", f"--name={CRED}", str(cred), "-"], check=True,
                         capture_output=True).stdout
    mem = Path(os.environ.get("RUNTIME_DIRECTORY") or "/run") / f"aurora-key-{os.getpid()}"
    fd = os.open(mem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # /run is in memory: the key never on a disk
    try:
        with os.fdopen(fd, "wb") as h:
            h.write(key)
        tmp = cred.with_suffix(".tmp")
        _encrypt(mem, tmp, "host+tpm2")
    finally:
        _shred(mem)
    back = subprocess.run(["systemd-creds", "decrypt", f"--name={CRED}", str(tmp), "-"], check=True,
                          capture_output=True).stdout
    if back != key:
        tmp.unlink()
        raise RuntimeError("the key sealed with the TPM does not give the same key back: the old one kept")
    os.chmod(tmp, 0o600)
    os.replace(tmp, cred)
    _write_private(marker, f"{cred}\nhost+tpm2\n".encode())
    os.chown(marker, svc.pw_uid, svc.pw_gid)
    return "sealed again with the TPM"


def seal_host(cfg: sys_config.Config) -> str:
    """As root (the installer): her key file becomes a systemd credential bound to this machine (and its TPM when it
    works), checked, and the file destroyed. Returns what was done."""
    keys, f = folder(cfg), folder(cfg) / "aurora.key"
    cred, marker = cred_path(cfg), folder(cfg) / "aurora.sealed"
    if os.geteuid() != 0:
        raise PermissionError("seal-host needs root")
    import pwd
    if marker.exists() and cred.exists():
        if bound(cfg) != "host+tpm2" and tpm():
            return _reseal_tpm(cfg, cred, marker, pwd.getpwnam(sys_config.service_user(cfg)))
        return f"already sealed ({bound(cfg)})"
    if not f.is_file():
        if marker.exists():
            raise RuntimeError(f"{marker} says the key is sealed, but {cred} is missing: recover it from the escrow")
        own_key(cfg)
    svc = pwd.getpwnam(sys_config.service_user(cfg))
    for x in (keys, f, keys / "aurora.escrow"):          # made here as root: still the services' account's (a seal
                                                         # that fails below leaves a key they can read)
        if x.exists():
            os.chown(x, svc.pw_uid, svc.pw_gid)
    CREDSTORE.mkdir(mode=0o700, exist_ok=True)
    tmp = cred.with_suffix(".tmp")
    with_key = "host+tpm2" if tpm() else "host"
    _encrypt(f, tmp, with_key)
    back = subprocess.run(["systemd-creds", "decrypt", f"--name={CRED}", str(tmp), "-"], check=True,
                          capture_output=True).stdout
    if back != f.read_bytes():
        tmp.unlink()
        raise RuntimeError("the sealed key does not give the same key back: nothing changed")
    os.chmod(tmp, 0o600)                                # root's: systemd reads it, nobody else
    os.replace(tmp, cred)
    _write_private(marker, f"{cred}\n{with_key}\n".encode())
    os.chown(marker, svc.pw_uid, svc.pw_gid)
    _shred(f)
    return f"sealed ({with_key})"


def forget(cfg: sys_config.Config) -> list[str]:
    """The uninstall's purge: every copy of her key destroyed (the users' data then never opens again)."""
    gone = []
    for f in (folder(cfg) / "aurora.key", cred_path(cfg), folder(cfg) / "aurora.escrow", folder(cfg) / "aurora.sealed"):
        try:
            if f.exists():
                _shred(f)
                gone.append(f.name)
        except PermissionError:                         # the sealed one is root's: the uninstall runs as root
            pass
    return gone


def main(argv: list[str]) -> int:
    cfg = sys_config.get()
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        print(where(cfg), bound(cfg) or "-", "escrow" if (folder(cfg) / "aurora.escrow").is_file() else "no escrow",
              "tpm ok" if tpm() else "no working tpm")
    elif cmd == "seal-host":
        print(seal_host(cfg))
    elif cmd == "recover":
        print(recover(cfg))
    elif cmd == "escrow":
        print("escrow written" if escrow(cfg) else "no backup key: sys_backup.py init first")
    else:
        print("usage: python -m aurora.sys_keyring status|seal-host|recover|escrow", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
