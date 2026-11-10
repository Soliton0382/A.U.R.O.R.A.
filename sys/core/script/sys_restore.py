# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Restore a backup onto this installation (owner, 2026-10-06), safely and only when the formats are compatible.

    python sys/core/script/sys_restore.py                     # the snapshots, each with its compatibility
    python sys/core/script/sys_restore.py --plan  <snapshot>  # what a restore would do (changes nothing)
    python sys/core/script/sys_restore.py --apply <snapshot>  # do it: asks to type RIPRISTINA
    python sys/core/script/sys_restore.py --apply <snapshot> --parts config,memory    # only these (sys_backup_parts)

What --apply does, in this order, as root where Aurora has her own account (only root can stop her units and write
every folder; each file ends with the owner of the folder it goes in), and a failure puts everything back as it was:
 1. the formats (sys_formats): the same → as it is; older → the migrations; newer → refused (update Aurora first);
 2. the chosen parts of the snapshot (all, by default) are written into <status>/backup/restore-<time>, every file checked;
 3. Aurora stops (aurora.target);
 4. what those parts hold today is moved aside into <status>/backup/before-restore-<time> — nothing is deleted;
 5. the restored data goes in its place; the code always wins: a built-in plugin, and the signature of the code
    (ethics/MANIFEST.json), stay this installation's — only plugins Aurora built that are missing here come back;
 6. the migrations, then the settings the code knows and the backup did not (sys_env_sync);
 7. Aurora starts again.
Every write of steps 4–6 goes through directory fds opened with O_NOFOLLOW from the installation's root (rename on
fds, fchown/fchmod on the open file): a symbolic link planted anywhere on the way is refused, and all is put back (C557).
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_backup, sys_backup_parts, sys_config, sys_formats, sys_seal  # noqa: E402

KEEP_FROM_CODE = ("sys/core/ethics/MANIFEST.json",)       # the signature of the code here, never an old one
UNITS = ("aurora-api", "aurora-rem", "aurora-sentinel", "aurora-models", "aurora-harvester", "aurora-llm")


def listing(cfg) -> list[dict]:
    enc, _ = sys_backup._subkeys(sys_backup.load_key(cfg))
    out = []
    for p in sys_backup.snapshots(sys_backup.target(cfg)):
        s = sys_backup.read_snapshot(p, enc)
        out.append({"snapshot": p.stem, "created": s.get("created"), "host": s.get("host"), "files": len(s["files"]),
                    "bytes": sum(f[1] for f in s["files"]), "formats": s.get("formats"),
                    "parts": sys_backup_parts.sizes(cfg, s["files"]),
                    "compat": sys_formats.compare(s.get("formats"), sys_formats.current(cfg))})
    return out


def plan(cfg, snapshot: str) -> dict:
    snaps = {s["snapshot"]: s for s in listing(cfg)}
    s = snaps.get(snapshot) or (list(snaps.values())[-1] if snapshot == "latest" and snaps else None)
    if s is None:
        raise SystemExit(f"no snapshot {snapshot}")
    stamp, here = time.strftime("%Y%m%d-%H%M%S"), cfg.path("AURORA_STATUS_DIR") / "backup"     # never backed up nor restored
    return {**s, "restorable": s["compat"]["verdict"] != "newer", "stage": str(here / f"restore-{stamp}"),
            "aside": str(here / f"before-restore-{stamp}")}


_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _as_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


class Linked(OSError):
    """A symbolic link where root was about to write (C557): refused, said with its path; the caller puts all back."""

    def __init__(self, where) -> None:
        super().__init__(f"a symbolic link at {where}: nothing is written through a link")


def _relocate(sfd: int, sname: str, dfd: int, dname: str) -> None:
    """One file from a directory fd to another: rename; on another disk, copied through fds and the source removed."""
    try:
        os.rename(sname, dname, src_dir_fd=sfd, dst_dir_fd=dfd)
        return
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
    src = os.open(sname, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=sfd)
    try:
        st = os.fstat(src)
        if not stat.S_ISREG(st.st_mode):
            raise OSError(f"{sname}: not a regular file")
        dst = os.open(dname, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        try:
            with os.fdopen(src, "rb", closefd=False) as a, os.fdopen(dst, "wb", closefd=False) as b:
                shutil.copyfileobj(a, b)
            os.fchmod(dst, stat.S_IMODE(st.st_mode))
            os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))
        finally:
            os.close(dst)
    finally:
        os.close(src)
    os.unlink(sname, dir_fd=sfd)


class _Trees:
    """Where the restore writes, reached only through directory fds (C557: as root, under folders the service account
    can write, shutil followed a planted link — root's writes and a chown went elsewhere). Every folder is opened from
    a trusted top — the installation's root for what is inside it, / for the rest — one component at a time with
    O_NOFOLLOW; files move with rename on those fds; owner and mode are set on the open file. A link anywhere on the
    way raises Linked, and nothing is written."""

    def __init__(self, root: Path, aside: Path) -> None:
        self.root, self.aside = Path(os.path.abspath(root)), Path(os.path.abspath(aside))
        self.rootfd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)     # the owner's folder: trusted as given
        self.slashfd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)

    def close(self) -> None:
        os.close(self.rootfd)
        os.close(self.slashfd)

    def folder(self, path: Path, make: bool = False, own: bool = False) -> int:
        """`path` as a directory fd, no link on the way down from the trusted top. `make`: the folders missing are
        created; `own`: as root they belong to who owns the folder they went in. The caller closes the fd."""
        path = Path(os.path.abspath(path))
        top = self.root if path.is_relative_to(self.root) else Path("/")
        parts = path.relative_to(top).parts
        fd = os.dup(self.rootfd if top == self.root else self.slashfd)
        try:
            for i, part in enumerate(parts):
                try:
                    nxt = os.open(part, _DIR, dir_fd=fd)
                except FileNotFoundError:
                    if not make:
                        raise
                    parent = os.fstat(fd)
                    os.mkdir(part, 0o777, dir_fd=fd)
                    nxt = os.open(part, _DIR, dir_fd=fd)
                    if own and _as_root():
                        os.fchown(nxt, parent.st_uid, parent.st_gid)
                except OSError as e:
                    if e.errno == errno.ELOOP:
                        raise Linked(top.joinpath(*parts[:i + 1])) from None
                    raise
                os.close(fd)
                fd = nxt
            return fd
        except BaseException:
            os.close(fd)
            raise

    def files(self, top: Path) -> list[str]:
        """Every regular file under `top`, relative to it, met through fds; a link anywhere below: Linked."""
        out: list[str] = []

        def walk(fd: int, rel: str) -> None:
            with os.scandir(fd) as it:
                entries = list(it)
            for e in entries:
                if e.is_symlink():
                    raise Linked(top / (rel + e.name))
                if e.is_dir(follow_symlinks=False):
                    try:
                        sub = os.open(e.name, _DIR, dir_fd=fd)
                    except OSError as x:
                        if x.errno == errno.ELOOP:
                            raise Linked(top / (rel + e.name)) from None
                        raise
                    try:
                        walk(sub, f"{rel}{e.name}/")
                    finally:
                        os.close(sub)
                elif e.is_file(follow_symlinks=False):
                    out.append(rel + e.name)
        fd = self.folder(top)
        try:
            walk(fd, "")
        finally:
            os.close(fd)
        return sorted(out)

    def move(self, src: Path, dst: Path, own: bool | None = None) -> None:
        """src → dst, regular files reached through fds, dst's folders made. As root, what lands inside the
        installation (not aside) belongs to who owns the folder it went in: fchown on the open file."""
        if own is None:
            own = dst.is_relative_to(self.root) and not dst.is_relative_to(self.aside)
        sfd = self.folder(src.parent)
        try:
            dfd = self.folder(dst.parent, make=True, own=own)
            try:
                if stat.S_ISLNK(os.lstat(src.name, dir_fd=sfd).st_mode):
                    raise Linked(src)
                try:
                    if stat.S_ISLNK(os.lstat(dst.name, dir_fd=dfd).st_mode):
                        raise Linked(dst)                # a link at the name: never replaced in silence
                except FileNotFoundError:
                    pass
                _relocate(sfd, src.name, dfd, dst.name)
                try:
                    if stat.S_ISLNK(os.lstat(dst.name, dir_fd=dfd).st_mode):
                        raise Linked(dst)                # swapped for a link while moving: back where it was
                    if own and _as_root():
                        parent = os.fstat(dfd)
                        f = os.open(dst.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
                        try:
                            os.fchown(f, parent.st_uid, parent.st_gid)
                        finally:
                            os.close(f)
                except BaseException:
                    _relocate(dfd, dst.name, sfd, src.name)
                    raise
            finally:
                os.close(dfd)
        finally:
            os.close(sfd)

    def swap_env(self) -> None:
        """.env.proposed → .env in the root through its fd: the mode kept, root's chown on the open file (C557)."""
        fd = self.rootfd
        for name in (".env", ".env.proposed"):
            if stat.S_ISLNK(os.lstat(name, dir_fd=fd).st_mode):
                raise Linked(self.root / name)
        mode = stat.S_IMODE(os.lstat(".env", dir_fd=fd).st_mode)
        os.rename(".env.proposed", ".env", src_dir_fd=fd, dst_dir_fd=fd)
        f = os.open(".env", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            os.fchmod(f, mode)
            if _as_root():
                owner = os.fstat(fd)
                os.fchown(f, owner.st_uid, owner.st_gid)
        finally:
            os.close(f)


def apply_parts(cfg, p: dict, parts: tuple[str, ...]) -> None:
    """Only some parts back; the rest of this installation is not touched. File by file: what a part holds here today
    goes aside, whole, so that a shard of today never stays next to a registry of the backup. Any failure puts all back
    as it was, and Aurora starts again either way."""
    root = cfg.root.resolve()
    stage, aside = Path(p["stage"]), Path(p["aside"])
    print(f"1/6 formats: {p['compat']['verdict']} {p['compat']['why']}")
    print(f"2/6 restoring {', '.join(parts)} of {p['snapshot']} into {stage} …", flush=True)
    r = sys_backup.restore(cfg, stage, p["snapshot"], parts=parts)
    print(f"    {r['files']} files, {r['bytes'] / 1e9:.2f} GB, each checked")
    print("3/6 stopping Aurora …", flush=True)
    # the units too: an inactive target stops nothing, and they run on (found on a real restore: old memory served after it)
    subprocess.run(["systemctl", "stop", "aurora.target", *UNITS], check=False, timeout=300)   # a unit not here: said, no harm
    subprocess.run(["systemctl", "stop", "aurora-backup.timer"], check=False, timeout=60)      # none before a backup is set
    running = subprocess.run(["systemctl", "is-active", "aurora-api"], check=False, capture_output=True, text=True, timeout=30)
    if running.stdout.strip() == "active":               # never under a running Aurora
        subprocess.run(["systemctl", "start", "aurora.target"], check=False, timeout=300)
        raise SystemExit(f"⛔ Aurora could not be stopped: nothing changed (the snapshot is in {stage})")
    done: list[tuple[Path, Path]] = []
    T = _Trees(root, aside)                              # C557: every write below through directory fds, no link followed

    def move(src: Path, dst: Path) -> None:
        T.move(src, dst)
        done.append((src, dst))
    changed = "config" in parts and other_keys(cfg, stage)
    try:
        print(f"4/6 today's {', '.join(parts)} aside into {aside}")
        plugins_rel = str(cfg.path("AURORA_PLUGINS_DIR").resolve().relative_to(root))
        for rel, path in list(sys_backup.files(cfg)):
            if rel in KEEP_FROM_CODE or rel.startswith(plugins_rel + "/") or sys_backup_parts.part_of(cfg, rel) not in parts:
                continue
            for src in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
                if src.exists():
                    move(src, (aside / rel).with_name(src.name))
        if changed:
            left = out_of_reach(cfg, parts)
            print(f"    the backup's keys are not today's: {len(left)} files sealed with today's go aside too, they would not open")
            for rel, path in left:
                move(path, aside / rel)
        print("5/6 the restored parts in place")
        folder = root / plugins_rel
        plugins_here = {d.name for d in folder.iterdir()} if folder.is_dir() else set()
        for rel in T.files(stage):                       # a link in the stage (the service account's folder): refused
            src = stage / rel
            if rel in KEEP_FROM_CODE:
                continue
            if rel.startswith("external/"):              # a folder outside Aurora's root: left in the stage, said
                print(f"    left in {stage}: {rel}")
                continue
            # the code wins: only the plugins Aurora built that are missing here
            if rel.startswith(plugins_rel + "/") and Path(rel).parts[len(Path(plugins_rel).parts)] in plugins_here:
                continue
            move(src, root / rel)
        for (k, n), fn in sorted(sys_formats.MIGRATE.items()):
            if k in (p.get("formats") or {}) and int(p["formats"][k]) <= n < sys_formats.FORMATS[k]:
                fn(cfg)
                print(f"    {sys_formats.MIGRATIONS[(k, n)]}")
        if "config" in parts:
            env_sync = Path(__file__).with_name("sys_env_sync.py")
            if subprocess.run([sys.executable, str(env_sync)], cwd=root, capture_output=True).returncode == 0 and (root / ".env.proposed").exists():
                T.swap_env()
        if _as_root():                                   # what stays there is for Aurora's account to clear
            uid = cfg.path("AURORA_STATUS_DIR").stat().st_uid
            for folder in (stage, aside):
                try:
                    fd = T.folder(folder)
                except FileNotFoundError:
                    continue
                try:
                    os.fchown(fd, uid, -1)
                finally:
                    os.close(fd)
    except Exception as e:                               # noqa: BLE001 - whatever it is: back as it was, and said
        print(f"⛔ stopped: {type(e).__name__}: {e}\n   everything put back as it was", flush=True)
        for src, dst in reversed(done):
            T.move(dst, src, own=False)
        raise SystemExit(1) from None
    finally:
        T.close()
        print("6/6 starting Aurora …", flush=True)
        subprocess.run(["systemctl", "start", "aurora-backup.timer"], check=False, timeout=60)
        subprocess.run(["systemctl", "start", "aurora.target", "aurora-api"], check=False, timeout=300)
    print(f"✅ restored {', '.join(parts)} of {p['snapshot']}. Today's are in {aside}: delete them when all is well, or move them back.")
    print(notes(parts))


def needs_root(cfg) -> bool:
    """Aurora on her own account: only root stops her units and writes every folder (C491: as the owner it stopped half
    way on the service's own folders, as the service it could not stop the units)."""
    try:
        return cfg.path("AURORA_STATUS_DIR").stat().st_uid != cfg.root.stat().st_uid
    except OSError:
        return False


def other_keys(cfg, stage: Path) -> bool:
    """The users' keys of the backup differ from today's: a new installation, or keys made anew (C493). What today's keys
    sealed would not open under them."""
    status = cfg.path("AURORA_STATUS_DIR")
    for new in (stage / status.relative_to(cfg.root) / "users").glob("*/keys/*.key"):
        here = status / new.relative_to(stage / status.relative_to(cfg.root))
        if here.is_file() and here.read_bytes() != new.read_bytes():
            return True
    return False


def out_of_reach(cfg, parts: tuple[str, ...]) -> list:
    """What today's keys sealed, in the parts not asked for: the memory whole (sealed row by row), any other sealed file."""
    out = []
    for rel, path in sys_backup.files(cfg):
        part = sys_backup_parts.part_of(cfg, rel)
        if part in parts or part in ("vault", "plugins"):
            continue
        try:
            with open(path, "rb") as f:
                sealed = f.read(len(sys_seal.MAGIC)) == sys_seal.MAGIC
        except OSError:
            sealed = False
        if part == "memory" or sealed:
            out.append((rel, path))
    return out


def notes(parts: tuple[str, ...]) -> str:
    """What a choice leaves to do: said in the plan and at the end."""
    out = []
    if "config" not in parts and ("memory" in parts or "files" in parts):
        out.append("without the config: the backup's users and keys stay out, so what is sealed with them opens only "
                   "after their key is recovered (sys_key_recovery recover, sys_keyring recover)")
    if "config" in parts:
        out.append("the config brings the backup's settings and keys: on a new machine bring back Aurora's key "
                   "(sudo -u aurora .venv/bin/python -m aurora.sys_keyring recover, from sys/core) and the backup's "
                   "(sudo -u aurora .venv/bin/python sys/core/script/svc_backup.py init --code), then run ./install.sh again; "
                   "what today's keys sealed goes aside; folders and GPUs set for the old machine may need changing")
    return "\n".join(f"  ℹ️ {x}" for x in out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", metavar="SNAPSHOT")
    ap.add_argument("--apply", metavar="SNAPSHOT")
    ap.add_argument("--parts", default="", help="only these parts: " + ",".join(sys_backup_parts.PARTS))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--code", action="store_true", help="ask the backup's recovery code (its key is sealed for "
                    "Aurora's services, C461)")
    a = ap.parse_args()
    cfg = sys_config.get()
    if a.code:
        import getpass
        sys_backup.use_code(getpass.getpass("Backup recovery code: "))
    if not (a.plan or a.apply):
        rows = listing(cfg)
        if a.json:
            print(json.dumps(rows))
            return 0
        for s in rows:
            print(f"{s['snapshot']}  {s['files']:7d} files  {s['bytes'] / 1e9:6.2f} GB  {s['compat']['verdict']:8s} {s['compat']['why'][:90]}")
        return 0
    p = plan(cfg, a.plan or a.apply)
    parts = sys_backup_parts.chosen(a.parts) if a.parts else ()
    if a.plan or not p["restorable"]:
        print(json.dumps(p, indent=1) if a.json else
              f"snapshot {p['snapshot']} ({p['files']} files, {p['bytes'] / 1e9:.2f} GB) · formats: {p['compat']['verdict']} "
              f"{p['compat']['why']}\n" + "".join(f"  {'→' if n in parts else ' '} {n}: {v['files']} files, {v['bytes'] / 1e9:.2f} GB\n"
                                                   for n, v in p["parts"].items()) +
              f"  restored into {p['stage']}, then in place of {'those parts' if parts else 'all of it'}\n{notes(parts or sys_backup_parts.PARTS)}\n" +
              f"  today's data kept aside in {p['aside']}" + ("" if p["restorable"] else "\n  ⛔ NOT restorable here"))
        return 0 if p["restorable"] else 1
    if needs_root(cfg) and os.geteuid() != 0:
        print("⛔ Aurora has her own account: as root, through root's own copy: sudo aurora-root restore …")
        return 1
    what = f"{', '.join(parts)} di " if parts else ""
    if input(f"Ripristinare {what}{p['snapshot']} al posto dei dati di oggi (messi da parte, non cancellati)? Scrivi RIPRISTINA: ").strip() != "RIPRISTINA":
        print("annullato")
        return 1
    apply_parts(cfg, p, parts or sys_backup_parts.PARTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
