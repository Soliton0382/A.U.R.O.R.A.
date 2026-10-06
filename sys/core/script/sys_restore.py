# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Restore a backup onto this installation (owner, 2026-10-06), safely and only when the formats are compatible.

    python sys/core/script/sys_restore.py                     # the snapshots, each with its compatibility
    python sys/core/script/sys_restore.py --plan  <snapshot>  # what a restore would do (changes nothing)
    python sys/core/script/sys_restore.py --apply <snapshot>  # do it: asks to type RIPRISTINA

What --apply does, in this order, and stops at the first problem:
 1. the formats (sys_formats): the same → as it is; older → the migrations; newer → refused (update Aurora first);
 2. the snapshot is written into a separate folder next to this one (<root>-restore-<time>), every file checked;
 3. Aurora stops (aurora.target);
 4. today's data is moved aside, whole, into <root>-before-restore-<time> — nothing is deleted: to go back, move it back;
 5. the restored data goes in its place; the code always wins: a built-in plugin, and the signature of the code
    (ethics/MANIFEST.json), stay this installation's — only plugins Aurora built that are missing here come back;
 6. the migrations, then the settings the code knows and the backup did not (sys_env_sync);
 7. Aurora starts again.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_backup, sys_config, sys_formats  # noqa: E402

KEEP_FROM_CODE = ("sys/core/ethics/MANIFEST.json",)       # the signature of the code here, never an old one


def listing(cfg) -> list[dict]:
    enc, _ = sys_backup._subkeys(sys_backup.load_key(cfg))
    out = []
    for p in sys_backup.snapshots(sys_backup.target(cfg)):
        s = sys_backup.read_snapshot(p, enc)
        out.append({"snapshot": p.stem, "created": s.get("created"), "host": s.get("host"), "files": len(s["files"]),
                    "bytes": sum(f[1] for f in s["files"]), "formats": s.get("formats"),
                    "compat": sys_formats.compare(s.get("formats"), sys_formats.current(cfg))})
    return out


def plan(cfg, snapshot: str) -> dict:
    snaps = {s["snapshot"]: s for s in listing(cfg)}
    s = snaps.get(snapshot) or (list(snaps.values())[-1] if snapshot == "latest" and snaps else None)
    if s is None:
        raise SystemExit(f"no snapshot {snapshot}")
    root = cfg.root.resolve()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    places = [str(cfg.path(k).resolve().relative_to(root)) for k in sys_backup.SOURCES
              if root in cfg.path(k).resolve().parents] + list(sys_backup.DIRS) + [f for f in sys_backup.FILES if f not in KEEP_FROM_CODE]
    return {**s, "restorable": s["compat"]["verdict"] != "newer", "stage": str(root.parent / f"{root.name}-restore-{stamp}"),
            "aside": str(root.parent / f"{root.name}-before-restore-{stamp}"), "places": places}


def apply(cfg, p: dict) -> None:
    root = cfg.root.resolve()
    stage, aside = Path(p["stage"]), Path(p["aside"])
    print(f"1/7 formats: {p['compat']['verdict']} {p['compat']['why']}")
    print(f"2/7 restoring {p['snapshot']} into {stage} …", flush=True)
    r = sys_backup.restore(cfg, stage, p["snapshot"])
    print(f"    {r['files']} files, {r['bytes'] / 1e9:.2f} GB, each checked")
    print("3/7 stopping Aurora …", flush=True)
    subprocess.run(["systemctl", "stop", "aurora.target", "aurora-backup.timer"], check=False, timeout=300)
    print(f"4/7 today's data aside into {aside}")
    for rel in p["places"]:
        src = root / rel
        if src.exists():
            (aside / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(aside / rel))
    print("5/7 the restored data in place")
    plugins_rel = str(cfg.path("AURORA_PLUGINS_DIR").resolve().relative_to(root))
    for rel in p["places"]:
        src = stage / rel
        if not src.exists():
            continue
        if rel == plugins_rel:                           # the code wins: built-in plugins stay; Aurora's own come back
            here = aside / rel
            shutil.copytree(here, root / rel, dirs_exist_ok=True) if here.exists() else None
            for d in src.iterdir():
                if not (root / rel / d.name).exists():
                    shutil.copytree(d, root / rel / d.name)
            continue
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(root / rel))
    print("6/7 migrations and new settings")
    for (k, n), fn in sorted(sys_formats.MIGRATE.items()):
        if k in (p.get("formats") or {}) and int(p["formats"][k]) <= n < sys_formats.FORMATS[k]:
            fn(cfg)
            print(f"    {sys_formats.MIGRATIONS[(k, n)]}")
    env_sync = Path(__file__).with_name("sys_env_sync.py")
    if subprocess.run([sys.executable, str(env_sync)], cwd=root, capture_output=True).returncode == 0 and (root / ".env.proposed").exists():
        (root / ".env.proposed").replace(root / ".env")
    print("7/7 starting Aurora …", flush=True)
    subprocess.run(["systemctl", "start", "aurora.target", "aurora-backup.timer"], check=False, timeout=300)
    print(f"✅ restored {p['snapshot']}. Today's data is in {aside}: delete it when all is well, or move it back.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", metavar="SNAPSHOT")
    ap.add_argument("--apply", metavar="SNAPSHOT")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cfg = sys_config.get()
    if not (a.plan or a.apply):
        rows = listing(cfg)
        if a.json:
            print(json.dumps(rows))
            return 0
        for s in rows:
            print(f"{s['snapshot']}  {s['files']:7d} files  {s['bytes'] / 1e9:6.2f} GB  {s['compat']['verdict']:8s} {s['compat']['why'][:90]}")
        return 0
    p = plan(cfg, a.plan or a.apply)
    if a.plan or not p["restorable"]:
        print(json.dumps(p, indent=1) if a.json else
              f"snapshot {p['snapshot']} ({p['files']} files, {p['bytes'] / 1e9:.2f} GB) · formats: {p['compat']['verdict']} "
              f"{p['compat']['why']}\n  restored into {p['stage']}, then in place of: {', '.join(p['places'])}\n"
              f"  today's data kept aside in {p['aside']}" + ("" if p["restorable"] else "\n  ⛔ NOT restorable here"))
        return 0 if p["restorable"] else 1
    if input(f"Ripristinare {p['snapshot']} al posto dei dati di oggi (messi da parte, non cancellati)? Scrivi RIPRISTINA: ").strip() != "RIPRISTINA":
        print("annullato")
        return 1
    apply(cfg, p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
