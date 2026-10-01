# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Download the models of sys/core/config/models.json from Hugging Face, at pinned revisions, checked.

    python sys/core/script/sys_models_fetch.py --list                 # what, how big, what is already here
    python sys/core/script/sys_models_fetch.py --required --yes       # reasoner, encoder, re-ranker
    python sys/core/script/sys_models_fetch.py --all --yes            # + dream paintings and speech to text
    python sys/core/script/sys_models_fetch.py --models llm,stt --yes
    python sys/core/script/sys_models_fetch.py --verify               # SHA-256 of every big file already here

A file already present with the size Hugging Face publishes is not downloaded again; an interrupted
download resumes. Every large (LFS) file is checked against the SHA-256 Hugging Face publishes for that
revision: a mismatch stops with an error. Nothing is written outside the model folders of the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "sys" / "core" / "config" / "models.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def remote_files(repo: str, revision: str) -> dict:
    from huggingface_hub import HfApi
    info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    return {s.rfilename: s for s in info.siblings}


def state(name: str, m: dict) -> dict:
    """What is missing locally for one model, by size against the published metadata."""
    remote = remote_files(m["repo"], m["revision"])
    folder = ROOT / m["dir"]
    missing, total, need = [], 0, 0
    for f in m["files"]:
        r = remote.get(f)
        if r is None:
            raise SystemExit(f"{name}: {f} is not in {m['repo']}@{m['revision'][:12]}")
        total += r.size or 0
        p = folder / f
        if not (p.is_file() and p.stat().st_size == r.size):
            missing.append(f)
            need += r.size or 0
    return {"remote": remote, "missing": missing, "total": total, "need": need}


def fetch(name: str, m: dict, st: dict) -> None:
    from huggingface_hub import hf_hub_download
    folder = ROOT / m["dir"]
    folder.mkdir(parents=True, exist_ok=True)
    for f in st["missing"]:
        r = st["remote"][f]
        print(f"  {name}: {f} ({(r.size or 0) / 2**20:.0f} MiB)", flush=True)
        hf_hub_download(m["repo"], f, revision=m["revision"], local_dir=folder)
        p = folder / f
        if r.lfs and p.stat().st_size > 10_000_000 and sha256(p) != r.lfs.sha256:
            raise SystemExit(f"{name}: {f} SHA-256 differs from Hugging Face's: download again")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--required", action="store_true", help="the models Aurora cannot run without")
    ap.add_argument("--all", action="store_true", help="also dreams (images) and speech to text")
    ap.add_argument("--models", default="", help="comma-separated names from the manifest")
    ap.add_argument("--verify", action="store_true", help="SHA-256 of the big files already present")
    ap.add_argument("--yes", action="store_true", help="do not ask before downloading")
    args = ap.parse_args()
    models = json.loads(MANIFEST.read_text(encoding="utf-8"))["models"]
    if args.models:
        names = [n.strip() for n in args.models.split(",") if n.strip()]
        unknown = [n for n in names if n not in models]
        if unknown:
            raise SystemExit(f"unknown models: {unknown} (manifest: {list(models)})")
    elif args.all or args.list or args.verify:
        names = list(models)
    else:
        names = [n for n, m in models.items() if m["required"]]

    states = {n: state(n, models[n]) for n in names}
    print(f"{'model':11s} {'size':>8s} {'to get':>8s}  license      purpose")
    for n in names:
        m, st = models[n], states[n]
        print(f"{n:11s} {st['total'] / 2**30:7.2f}G {st['need'] / 2**30:7.2f}G  {str(m['license']):12s} {m['purpose']}"
              f"{'' if m['required'] else ' (optional)'}")
    need = sum(st["need"] for st in states.values())
    if args.verify:
        bad = 0
        for n in names:
            for f in models[n]["files"]:
                r, p = states[n]["remote"][f], ROOT / models[n]["dir"] / f
                if p.is_file() and r.lfs and p.stat().st_size > 10_000_000:
                    ok = sha256(p) == r.lfs.sha256
                    bad += not ok
                    print(f"  {n}/{f}: {'ok' if ok else 'SHA-256 DIFFERS'}")
        return 1 if bad else 0
    if args.list or not need:
        print("nothing to download" if not need else f"to download: {need / 2**30:.2f} GB")
        return 0
    free = shutil.disk_usage(ROOT).free
    print(f"to download: {need / 2**30:.2f} GB, free on disk: {free / 2**30:.1f} GB")
    if need > free * 0.95:
        raise SystemExit("not enough disk space")
    if not args.yes and input("Download? [y/N] ").strip().lower() not in ("y", "s", "yes", "si", "sì"):
        return 1
    for n in names:
        if states[n]["missing"]:
            fetch(n, models[n], states[n])
    print("models ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
