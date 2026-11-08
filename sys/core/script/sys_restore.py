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
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
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

    def move(src: Path, dst: Path) -> None:
        made = next(x for x in (dst.parent, *dst.parent.parents) if x.exists())
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        done.append((src, dst))
        if dst.is_relative_to(root) and not dst.is_relative_to(aside):
            like(dst, made)

    def like(path: Path, folder: Path) -> None:
        """As root: the file and the folders made for it belong to who owns the folder they went in."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            st = folder.stat()
            for x in (path, *[d for d in path.parents if folder in d.parents]):
                os.chown(x, st.st_uid, st.st_gid)
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
        for src in sorted(x for x in stage.rglob("*") if x.is_file()):
            rel = str(src.relative_to(stage))
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
                mode = (root / ".env").stat().st_mode & 0o777
                (root / ".env.proposed").replace(root / ".env")
                os.chmod(root / ".env", mode)
                like(root / ".env", root)
    except Exception as e:                               # noqa: BLE001 - whatever it is: back as it was, and said
        print(f"⛔ stopped: {type(e).__name__}: {e}\n   everything put back as it was", flush=True)
        for src, dst in reversed(done):
            shutil.move(str(dst), str(src))
        raise SystemExit(1) from None
    finally:
        print("6/6 starting Aurora …", flush=True)
        subprocess.run(["systemctl", "start", "aurora-backup.timer"], check=False, timeout=60)
        subprocess.run(["systemctl", "start", "aurora.target", "aurora-api"], check=False, timeout=300)
    for folder in (stage, aside):                        # what stays there is for Aurora's account to clear
        if folder.exists():
            shutil.chown(folder, cfg.path("AURORA_STATUS_DIR").stat().st_uid) if hasattr(os, "geteuid") and os.geteuid() == 0 else None
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
