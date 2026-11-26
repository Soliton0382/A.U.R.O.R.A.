# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's own backup (owner, 27 Nov: «un backup apposito per evidentia così resta una cosa separata… va nel medesimo
percorso impostato per i backup di aurora, usa la stessa metodologia ma è una cosa a sé»).

The same method as Aurora's (aurora/sys_backup: AES-256-GCM in 4 MiB frames, blobs named by an HMAC of their content
so an unchanged file is never written twice, SQLite copied with its own backup API, daily/weekly/monthly retention, a
sample of blobs decrypted after every run, restore only into an empty folder), but its own: its key
(/etc/aurora/evidentia-backup.key, root's; a recovery code shown once at install), its folder
(<Aurora's backup destination>/evidentia), its state (/var/lib/evidentia-backup), its unit and timer. Run by root from
root's signed copy: the destination may be the NAS mounted for Aurora, where only Aurora's user may write; the archive
is read only. Aurora sees the status only (/var/lib/evidentia-api/backup.json: when, how many, ok), never a file name.

    evd_backup.py run | verify [--full] | status | restore <empty folder> [snapshot] | apply <snapshot>
                  (restore and apply: [--user NAME]… [--owner] — only those archives, R15)

`apply` (owner, 27 Nov: a restore from the WebUI too) puts a snapshot in place of the live archive: restored beside it,
Evidentia's service stopped, today's archive moved aside (<archive>.before-restore-<time>, never deleted), the restored
one in its place with the archive's owner and group, the service started again; a failure puts all back."""
from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

LIB = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(LIB / "sys" / "core"))
from aurora import sys_backup as B  # noqa: E402 — the engine's pieces (pure functions; Aurora's own backup untouched)
from aurora.sys_backup_crypto import _decrypt_bytes, _encrypt_bytes, _subkeys, decrypt_stream  # noqa: E402

ENV = Path(os.environ.get("EVD_BACKUP_ENV") or "/etc/aurora/evidentia.env")
STATE = Path(os.environ.get("EVD_BACKUP_STATE") or "/var/lib/evidentia-backup")
STATUS = Path(os.environ.get("EVD_BACKUP_STATUS") or "/var/lib/evidentia-api/backup.json")


class Log:
    def info(self, *a): print(a[0] % a[1:] if len(a) > 1 else a[0], flush=True)
    warning = info


def settings() -> dict:
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def key(s: dict) -> bytes:
    raw = Path(s["EVD_BACKUP_KEY_FILE"]).read_bytes()
    if len(raw) != 32:
        raise SystemExit("evidentia backup: the key is not 32 bytes")
    return raw


def dest(s: dict) -> Path:
    d = Path(s["EVD_BACKUP_DIR"])
    if not d.parent.is_dir():
        raise SystemExit(f"evidentia backup: {d.parent} is not there (the NAS asleep, the disk not mounted): next run")
    d.mkdir(mode=0o700, exist_ok=True)
    return d


USERS = "_users"                 # R15: the other users' archives inside a snapshot, _users/<user>/<their files>


def files(data: Path):
    for p in sorted(data.rglob("*")):
        if p.is_file() and not p.is_symlink() and not p.name.endswith((".lock", "-shm", "-wal", ".tmp", ".part")):
            yield str(p.relative_to(data)), p


def archives(s: dict) -> Path:
    return Path(s.get("EVD_ARCHIVE_DIR") or "/var/lib/evidentia")


def all_files(s: dict):
    """The owner's archive as before (its files at the snapshot's top), then each other user's under _users/<user>/."""
    import re
    data = Path(s["EVD_DATA_DIR"])
    yield from files(data)
    root = archives(s)
    if not root.is_dir():
        return
    for u in sorted(root.iterdir()):
        d = u / "data"
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", u.name) and d.is_dir() and not d.is_symlink() \
                and d.resolve() != data.resolve():
            for rel, p in files(d):
                yield f"{USERS}/{u.name}/{rel}", p


def _wanted(rel: str, users) -> bool:
    """users None: all; else the names wanted, «» for the owner's archive."""
    if users is None:
        return True
    parts = rel.split("/")
    return parts[1] in users if parts[0] == USERS and len(parts) > 2 else "" in users


def _snapshot_names() -> list[str]:
    """The copies kept, newest first (their times only): Aurora cannot list the backup's folder, root's alone."""
    try:
        return [p.stem for p in reversed(B.snapshots(Path(settings()["EVD_BACKUP_DIR"])))]
    except (OSError, KeyError):
        return []


def _status(out: dict) -> None:
    STATUS.parent.mkdir(exist_ok=True)
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: out.get(k) for k in ("ok", "snapshot", "files", "bytes", "new_blobs", "bytes_written",
                                                       "pruned_snapshots", "checked_blobs", "seconds", "error")}
                              | {"at": time.time(), "snapshots": _snapshot_names()}))
    os.chmod(tmp, 0o640)
    try:
        import grp
        os.chown(tmp, 0, grp.getgrnam("evidentia-api").gr_gid)
    except (KeyError, PermissionError):
        pass
    tmp.replace(STATUS)


def run() -> dict:
    s = settings()
    data, d = Path(s["EVD_DATA_DIR"]), dest(s)
    enc, idkey = _subkeys(key(s))
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = open(STATE / "run.lock", "a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("evidentia backup: already running") from None
    t0, stamp = time.time(), datetime.now().strftime("%Y%m%d-%H%M%S")
    cache_f = STATE / "cache.json"
    try:
        cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    except ValueError:
        cache = {}
    new_cache, entries, n_new, bytes_new, bytes_all = {}, [], 0, 0, 0
    tmpdir = Path(tempfile.mkdtemp(prefix="evd-backup-", dir=str(STATE)))
    log = Log()
    try:
        for rel, p in all_files(s):
            st = p.stat()
            sig = f"{st.st_size}:{st.st_mtime_ns}"
            source, made = p, None
            wal = p.with_name(p.name + "-wal")
            if wal.exists():                            # a write lands in the journal first: its size and time too
                w = wal.stat()
                sig += f":{w.st_size}:{w.st_mtime_ns}"
            # the corpus is ~10 GB and changes only when a collection is read in: copied and hashed every night for
            # nothing. An unchanged database (file and journal) keeps its blob, as any other file.
            if cache.get(rel, [None])[0] == sig and B._blob_path(d, cache[rel][1]).exists():
                bid = cache[rel][1]
            elif B._is_sqlite(p):
                made = source = B._sqlite_copy(p, tmpdir)
                bid = B._blob_id(source, idkey)
            else:
                bid = B._blob_id(source, idkey)
            new_cache[rel] = [sig, bid]
            size = source.stat().st_size
            bytes_all += size
            bp = B._blob_path(d, bid)
            if not bp.exists():
                bp.parent.mkdir(parents=True, exist_ok=True)
                B._write_blob(source, bp, enc, log)
                n_new, bytes_new = n_new + 1, bytes_new + size
            entries.append([rel, size, int(st.st_mtime), st.st_mode & 0o777, bid])
            if made:
                made.unlink()
        snap = {"version": 1, "created": stamp, "kind": "evidentia", "root": str(data), "files": entries}
        B._write_atomic(d / "snapshots" / f"{stamp}.snap", _encrypt_bytes(json.dumps(snap).encode(), enc))
        B._write_atomic(cache_f, json.dumps(new_cache).encode())
        from aurora.sys_backup_crypto import _layer    # the installation's own layer, beside the snapshots, as Aurora's
        layer = _layer()
        if layer is not None and hasattr(layer, "export"):
            layer.export(d)
    finally:
        for f in tmpdir.glob("*"):
            f.unlink()
        tmpdir.rmdir()
    pruned, freed = prune(s, d, enc)
    checked = verify(sample=20)
    out = {"ok": True, "snapshot": stamp, "files": len(entries), "bytes": bytes_all, "new_blobs": n_new,
           "bytes_written": bytes_new, "pruned_snapshots": pruned, "freed_blobs": freed, "checked_blobs": checked,
           "seconds": round(time.time() - t0, 1)}
    _status(out)
    lock.close()
    return out


def prune(s: dict, d: Path, enc: bytes) -> tuple[int, int]:
    snaps = B.snapshots(d)
    kept = B.keep([p.stem for p in snaps], int(s.get("EVD_BACKUP_KEEP_DAILY", 7)), int(s.get("EVD_BACKUP_KEEP_WEEKLY", 4)),
                  int(s.get("EVD_BACKUP_KEEP_MONTHLY", 6)))
    gone = 0
    for p in snaps:
        if p.stem not in kept:
            p.unlink()
            gone += 1
    used = set()
    for p in B.snapshots(d):
        used |= {e[4] for e in B.read_snapshot(p, enc)["files"]}
    freed = 0
    for b in (d / "blobs").glob("*/*"):
        if b.name.endswith(".part") or b.name not in used:
            try:
                b.unlink()
                freed += 1
            except OSError:
                pass
    return gone, freed


def verify(sample: int | None = 20) -> int:
    """Decrypt blobs (a sample, or all with --full): a damaged one fails the run."""
    import io
    import random
    s = settings()
    d = Path(s["EVD_BACKUP_DIR"])
    enc, _ = _subkeys(key(s))
    blobs = [b for b in (d / "blobs").glob("*/*") if not b.name.endswith(".part")]
    pick = blobs if sample is None else random.sample(blobs, min(sample, len(blobs)))
    for b in pick:
        with open(b, "rb") as src:
            decrypt_stream(src, io.BytesIO(), enc)
    return len(pick)


def restore(into: Path, snapshot: str = "latest", users=None) -> dict:
    """Into an EMPTY folder only, never over the live archive; each file decrypted and checked."""
    s = settings()
    d = Path(s["EVD_BACKUP_DIR"])
    enc, _ = _subkeys(key(s))
    if into.exists() and any(into.iterdir()):
        raise SystemExit(f"evidentia restore: {into} is not empty")
    if into.resolve() == Path(s["EVD_DATA_DIR"]).resolve():
        raise SystemExit("evidentia restore: never over the live archive")
    snaps = B.snapshots(d)
    if not snaps:
        raise SystemExit("evidentia restore: no snapshot")
    path = snaps[-1] if snapshot == "latest" else d / "snapshots" / f"{snapshot}.snap"
    snap = json.loads(_decrypt_bytes(path.read_bytes(), enc))
    into.mkdir(mode=0o700, parents=True, exist_ok=True)
    n = 0
    for rel, size, mtime, mode, bid in snap["files"]:
        if not _wanted(rel, users):
            continue
        target = (into / rel).resolve()
        if into.resolve() not in target.parents:
            raise SystemExit(f"evidentia restore: a path outside the folder in the snapshot: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(B._blob_path(d, bid), "rb") as src, open(target, "wb") as dst:
            decrypt_stream(src, dst, enc)
        os.chmod(target, mode & 0o770)
        os.utime(target, (mtime, mtime))
        n += 1
    return {"snapshot": snap["created"], "files": n, "into": str(into)}


def apply(snapshot: str, run=None, users=None) -> dict:
    """The snapshot in place of the live archives (see the module's text): all of them, or only the users named
    («» the owner's). As root only."""
    import shutil
    import subprocess
    run = run or subprocess.run
    if not (snapshot == "latest" or (len(snapshot) == 15 and snapshot[8] == "-" and snapshot.replace("-", "").isdigit())):
        raise SystemExit(f"evidentia apply: {snapshot!r} is not a snapshot's name")
    s = settings()
    data = Path(s["EVD_DATA_DIR"]).resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stage, aside = data.with_name(f".{data.name}.restore-{stamp}"), data.with_name(f"{data.name}.before-restore-{stamp}")
    st = data.stat()
    out = restore(stage, snapshot, users)
    for p in [stage, *stage.rglob("*")]:            # the archive's owner and group, as before
        os.chown(p, st.st_uid, st.st_gid, follow_symlinks=False)
    os.chmod(stage, st.st_mode & 0o7777)
    theirs = stage / USERS                          # the other users' archives: set apart before the owner's swap
    others = stage.with_name(stage.name + ".users")
    if theirs.is_dir():
        theirs.rename(others)
    owner_back = users is None or "" in users
    swapped, asides = [], []
    run(["systemctl", "stop", "evidentia-api.service"], check=False)
    try:
        if owner_back:
            data.rename(aside)
            swapped.append((aside, data))
            stage.rename(data)
            asides.append(str(aside))
        if others.is_dir():
            root = archives(settings())
            for u in sorted(others.iterdir()):
                live, old = root / u.name / "data", root / u.name / f"data.before-restore-{stamp}"
                (root / u.name).mkdir(mode=0o2770, exist_ok=True)
                os.chown(root / u.name, st.st_uid, st.st_gid)
                if live.exists():
                    live.rename(old)
                    swapped.append((old, live))
                    asides.append(str(old))
                (u / "data").rename(live) if (u / "data").is_dir() else u.rename(live)
    except OSError:
        for old, live in reversed(swapped):         # all put back as it was
            if old.exists() and not live.exists():
                old.rename(live)
        run(["systemctl", "start", "evidentia-api.service"], check=False)
        raise
    run(["systemctl", "start", "evidentia-api.service"], check=False)
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(others, ignore_errors=True)
    return {**out, "into": str(data), "aside": ", ".join(asides)}


def _users_of(argv: list[str]):
    """--user NAME (repeatable) and --owner: only those archives; neither: all of them."""
    names = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--user"] + ([""] if "--owner" in argv else [])
    return set(names) if names else None


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "run":
            out = run()
        elif cmd == "verify":
            out = {"checked_blobs": verify(None if "--full" in argv else 20)}
        elif cmd == "status":
            out = json.loads(STATUS.read_text()) if STATUS.exists() else {"ok": None}
        elif cmd == "apply" and len(argv) > 2:
            out = apply(argv[2], users=_users_of(argv))
        elif cmd == "restore" and len(argv) > 2:
            out = restore(Path(argv[2]), argv[3] if len(argv) > 3 and not argv[3].startswith("--") else "latest",
                          users=_users_of(argv))
        else:
            print(__doc__)
            return 2
    except SystemExit as e:
        if cmd == "run":
            _status({"ok": False, "error": str(e)})
        raise
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
