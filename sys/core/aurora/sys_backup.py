# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's data, copied every night to another disk, encrypted, deduplicated, checked.

What is copied: the vault and its index (knowledge and memory), the status folder (routines, approvals, devices,
model choices, push), the user folder (documents, uploads, images, projects), .env, the plugins (also those Aurora
built), the exemption and the code signature of this installation. Not copied: models, venv, runtime, logs,
sandboxes: they come back with the installer.

    <AURORA_BACKUP_DIR>/blobs/ab/<id>        one file's content, AES-256-GCM in 4 MiB frames; id = HMAC of the content,
                                             so a file that did not change is never written twice (25 GB once)
    <AURORA_BACKUP_DIR>/snapshots/<time>     the list of one night's files (path, size, time, mode, blob), encrypted
    <AURORA_STATUS_DIR>/backup/              last run, the cache (size+time → blob: unchanged files are not read again)

SQLite files (vault shards, registries) are copied with SQLite's own backup API: a consistent copy while Aurora writes.
The key (AURORA_BACKUP_KEY_FILE, 32 bytes) never goes into the backup: `init` makes it and shows it once as a recovery
code, to keep outside this machine (a password manager): without it a backup cannot be read, by anyone.
Retention: AURORA_BACKUP_KEEP_DAILY / _WEEKLY / _MONTHLY snapshots; blobs no snapshot uses are deleted. Every run
checks a sample of blobs by decrypting them; `verify --full` checks them all; `restore` writes into an empty folder,
never over the live installation.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import random
import socket
import sqlite3
import struct
import tempfile
import time
from datetime import datetime
from pathlib import Path

from . import sys_config, sys_log

MAGIC = b"AURB1"
FRAME = 4 * 2**20
SOURCES = ("AURORA_VAULT_DIR", "AURORA_STATUS_DIR", "AURORA_PLUGINS_DIR", "AURORA_UPLOADS_DIR", "AURORA_IMAGE_DIR",
           "AURORA_PROJECTS_DIR", "AURORA_DOCUMENTS_DIR")
DIRS = ("usr", "sys/https/cert")                        # the rest of the user folder; the owner's own certificates
FILES = (".env", "sys/core/ethics/MANIFEST.json")
SKIP_NAMES = {"gpu.lock", "heartbeat"}                  # live markers, not data
SKIP_SUFFIXES = (".db-wal", ".db-shm", ".lock", ".tmp", ".part", ".pyc")
SKIP_STATUS = ("bench", "backup")                       # in the status folder: benchmarks are rebuilt, the backup's own
                                                        # state stays local


class BackupError(RuntimeError):
    pass


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


# ---- what is copied ---------------------------------------------------------------------------------
def target(cfg: sys_config.Config) -> Path:
    raw = str(cfg["AURORA_BACKUP_DIR"] or "").strip()
    if not raw:
        raise BackupError("no backup folder: set AURORA_BACKUP_DIR (another disk, or the NAS)")
    d = Path(os.path.expanduser(raw))
    if not d.is_absolute():
        raise BackupError(f"AURORA_BACKUP_DIR must be an absolute path: {raw}")
    if d.resolve() == cfg.root.resolve() or cfg.root.resolve() in d.resolve().parents:
        raise BackupError("AURORA_BACKUP_DIR is inside Aurora's folder: a lost disk would take both")
    if not d.is_dir():
        raise BackupError(f"{d} does not exist (is the disk mounted?)")
    return d


def files(cfg: sys_config.Config):
    """(relative path, absolute path) of everything the backup keeps."""
    root = cfg.root.resolve()
    skip = {(cfg.path("AURORA_STATUS_DIR") / d).resolve() for d in SKIP_STATUS}
    seen = set()
    for base in [cfg.path(k) for k in SOURCES] + [root / d for d in DIRS]:
        if not base.exists():
            continue
        for dirpath, dirnames, names in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__" and (Path(dirpath) / d).resolve() not in skip)
            for n in sorted(names):
                p = Path(dirpath) / n
                if n in SKIP_NAMES or n.endswith(SKIP_SUFFIXES) or not p.is_file() or p.is_symlink():
                    continue
                full = p.resolve()                      # a folder set outside Aurora's root keeps its place apart
                rel = str(full.relative_to(root)) if root in full.parents else "external" + str(full)
                if rel not in seen:
                    seen.add(rel)
                    yield rel, p
    for rel in FILES + (str(cfg["AURORA_ETHICS_EXEMPTION"]),):
        p = root / rel
        if p.is_file() and rel not in seen:
            seen.add(rel)
            yield rel, p


def _is_sqlite(p: Path) -> bool:
    if p.suffix not in (".db", ".sqlite", ".sqlite3"):
        return False
    with open(p, "rb") as f:
        return f.read(16) == b"SQLite format 3\x00"


def _sqlite_copy(p: Path, tmpdir: Path) -> Path:
    """A consistent copy while Aurora writes (WAL included), with SQLite's own backup."""
    out = Path(tempfile.mkstemp(dir=tmpdir, suffix=".db")[1])
    src = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(out)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return out


def _blob_id(p: Path, idkey: bytes) -> str:
    h = hmac.new(idkey, digestmod=hashlib.sha256)
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(FRAME), b""):
            h.update(b)
    return h.hexdigest()


def _blob_path(dest: Path, bid: str) -> Path:
    return dest / "blobs" / bid[:2] / bid


def _state_dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "backup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---- snapshots ---------------------------------------------------------------------------------------
def snapshots(dest: Path) -> list[Path]:
    d = dest / "snapshots"
    return sorted(d.glob("*.snap")) if d.is_dir() else []


def read_snapshot(path: Path, enc: bytes) -> dict:
    return json.loads(_decrypt_bytes(path.read_bytes(), enc))


def keep(names: list[str], daily: int, weekly: int, monthly: int) -> set[str]:
    """Which snapshots to keep: the newest of each of the last `daily` days, `weekly` weeks, `monthly` months."""
    stamps = sorted(names, reverse=True)
    kept, days, weeks, months = set(), [], [], []
    for s in stamps:
        t = datetime.strptime(s[:15], "%Y%m%d-%H%M%S")
        for bucket, limit, key in ((days, daily, t.strftime("%Y%m%d")), (weeks, weekly, t.strftime("%G%V")),
                                   (months, monthly, t.strftime("%Y%m"))):
            if key not in bucket and len(bucket) < limit:
                bucket.append(key)
                kept.add(s)
    if stamps:
        kept.add(stamps[0])                              # never delete the newest
    return kept


def run(cfg: sys_config.Config | None = None, emit=None) -> dict:
    """One backup now. Returns the measures; raises BackupError when it cannot run."""
    cfg = cfg or sys_config.get()
    log = sys_log.get_logger("backup")
    ev = emit or (lambda e, d: None)
    dest = target(cfg)
    enc, idkey = _subkeys(load_key(cfg))
    state = _state_dir(cfg)
    lock = open(state / "run.lock", "a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise BackupError("a backup is already running") from None
    t0, stamp = time.time(), datetime.now().strftime("%Y%m%d-%H%M%S")
    cache_f = state / "cache.json"
    try:
        cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    except ValueError:
        cache = {}
    new_cache, entries = {}, []
    n_new = bytes_new = bytes_all = 0
    tmpdir = Path(tempfile.mkdtemp(prefix="aurora-backup-", dir=str(state)))
    try:
        for rel, p in files(cfg):
            st = p.stat()
            sig = f"{st.st_size}:{st.st_mtime_ns}"
            source, made = p, None
            if _is_sqlite(p):
                made = source = _sqlite_copy(p, tmpdir)  # always: a database may change without a new mtime
                bid = _blob_id(source, idkey)
            elif cache.get(rel, [None])[0] == sig and _blob_path(dest, cache[rel][1]).exists():
                bid = cache[rel][1]
            else:
                bid = _blob_id(source, idkey)
            new_cache[rel] = [sig, bid]
            size = source.stat().st_size
            bytes_all += size
            bp = _blob_path(dest, bid)
            if not bp.exists():
                bp.parent.mkdir(parents=True, exist_ok=True)
                part = bp.with_name(bp.name + ".part")
                with open(source, "rb") as src, open(part, "wb") as dst:
                    encrypt_stream(src, dst, enc)
                    dst.flush()
                    os.fsync(dst.fileno())
                os.replace(part, bp)
                n_new += 1
                bytes_new += size
            entries.append([rel, size, int(st.st_mtime), st.st_mode & 0o777, bid])
            if made:
                made.unlink()
        snap = {"version": 1, "created": stamp, "host": socket.gethostname(), "root": str(cfg.root),
                "files": entries}
        _write_atomic(dest / "snapshots" / f"{stamp}.snap", _encrypt_bytes(json.dumps(snap).encode(), enc))
        _write_atomic(cache_f, json.dumps(new_cache).encode())
    finally:
        for f in tmpdir.glob("*"):
            f.unlink()
        tmpdir.rmdir()
    pruned, freed = prune(cfg, dest, enc)
    checked = verify(cfg, sample=20)
    out = {"ok": True, "snapshot": stamp, "files": len(entries), "bytes": bytes_all, "new_blobs": n_new,
           "bytes_written": bytes_new, "pruned_snapshots": pruned, "freed_blobs": freed, "checked_blobs": checked,
           "seconds": round(time.time() - t0, 1), "dest": str(dest)}
    _write_atomic(state / "last.json", json.dumps({**out, "at": time.time()}).encode())
    log.info("backup %s: %d files, %.2f GB, %d new blobs (%.2f GB written), %d pruned, %d checked in %.1f s",
             stamp, len(entries), bytes_all / 1e9, n_new, bytes_new / 1e9, pruned, checked, out["seconds"])
    ev("backup.done", out)
    lock.close()
    return out


def prune(cfg: sys_config.Config, dest: Path, enc: bytes) -> tuple[int, int]:
    """Old snapshots out by the retention, then the blobs no snapshot uses."""
    snaps = snapshots(dest)
    kept = keep([p.stem for p in snaps], cfg["AURORA_BACKUP_KEEP_DAILY"], cfg["AURORA_BACKUP_KEEP_WEEKLY"],
                cfg["AURORA_BACKUP_KEEP_MONTHLY"])
    gone = 0
    for p in snaps:
        if p.stem not in kept:
            p.unlink()
            gone += 1
    used = set()
    for p in snapshots(dest):
        used |= {e[4] for e in read_snapshot(p, enc)["files"]}
    freed = 0
    for b in (dest / "blobs").glob("*/*"):
        if b.name.endswith(".part") or b.name not in used:
            b.unlink()
            freed += 1
    return gone, freed


def verify(cfg: sys_config.Config | None = None, sample: int | None = None) -> int:
    """Decrypt the blobs of the newest snapshot (a random sample, or all) and check their ids; raises on a bad one."""
    cfg = cfg or sys_config.get()
    dest = target(cfg)
    enc, idkey = _subkeys(load_key(cfg))
    snaps = snapshots(dest)
    if not snaps:
        raise BackupError("no snapshot yet")
    blobs = sorted({e[4] for e in read_snapshot(snaps[-1], enc)["files"]})
    if sample is not None and len(blobs) > sample:
        blobs = random.sample(blobs, sample)
    for bid in blobs:
        bp = _blob_path(dest, bid)
        if not bp.is_file():
            raise BackupError(f"blob {bid[:12]} is missing")
        h = hmac.new(idkey, digestmod=hashlib.sha256)

        class _Sink:
            def write(self, b):
                h.update(b)
        with open(bp, "rb") as f:
            decrypt_stream(f, _Sink(), enc)
        if h.hexdigest() != bid:
            raise BackupError(f"blob {bid[:12]} does not match its content")
    return len(blobs)


def restore(cfg: sys_config.Config, into: Path, snapshot: str = "latest", prefix: str = "", code: str = "") -> dict:
    """Write a snapshot's files into an empty folder (never over the live installation). `code`: the recovery code,
    when the key file is lost with the disk."""
    into = Path(into).resolve()
    if into == cfg.root.resolve() or cfg.root.resolve() in into.parents:
        raise BackupError("restore goes into a separate empty folder, never into the live installation")
    if into.exists() and any(into.iterdir()):
        raise BackupError(f"{into} is not empty")
    raw = key_from_code(code) if code else load_key(cfg)
    enc, idkey = _subkeys(raw)
    dest = target(cfg)
    snaps = snapshots(dest)
    snap = snaps[-1] if snapshot == "latest" else dest / "snapshots" / f"{snapshot}.snap"
    if not snap.is_file():
        raise BackupError(f"no snapshot {snapshot}")
    data, n, size = read_snapshot(snap, enc), 0, 0
    for rel, sz, mtime, mode, bid in data["files"]:
        if prefix and not rel.startswith(prefix):
            continue
        out = into / rel
        if into not in out.resolve().parents:
            raise BackupError(f"unsafe path in the snapshot: {rel}")
        out.parent.mkdir(parents=True, exist_ok=True)
        h = hmac.new(idkey, digestmod=hashlib.sha256)

        class _Tee:
            def __init__(self, f):
                self.f = f

            def write(self, b):
                h.update(b)
                self.f.write(b)
        with open(_blob_path(dest, bid), "rb") as src, open(out, "wb") as dst:
            decrypt_stream(src, _Tee(dst), enc)
        if h.hexdigest() != bid:
            raise BackupError(f"{rel}: restored content does not match")
        os.chmod(out, mode or 0o600)
        os.utime(out, (mtime, mtime))
        n, size = n + 1, size + sz
    return {"snapshot": snap.stem, "files": n, "bytes": size, "into": str(into)}


def status(cfg: sys_config.Config | None = None) -> dict:
    """What the Status page and the health show: configured?, last run, snapshots."""
    cfg = cfg or sys_config.get()
    out = {"configured": False, "problem": "", "last": None, "snapshots": [], "key": key_path(cfg).is_file()}
    try:
        dest = target(cfg)
        out["configured"] = out["key"]
        out["dest"] = str(dest)
        out["snapshots"] = [p.stem for p in snapshots(dest)]
        if not out["key"]:
            out["problem"] = "no backup key: sys_backup.py init"
    except BackupError as e:
        out["problem"] = str(e)
    f = _state_dir(cfg) / "last.json"
    if f.exists():
        try:
            out["last"] = json.loads(f.read_text())
        except ValueError:
            pass
    return out
