#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Download a model into sys/models/<name> once, pinned: sys/evidentia/config/models.json holds, for each model, the git
revision and every file's size and SHA-256. A pinned model is downloaded at exactly that revision and checked file by
file; a mismatch is refused (nothing is written, the folder is left for the owner to look at). A model not yet pinned
is pinned by its first download (trust on first use — the pin is then the measured value for every later run).
MODEL.json keeps what was downloaded (repo, revision, files) as before. Models are read-only after this.

The same check runs before every load (evd_embed.py: check()): a replaced or altered model is refused aloud (B30).

    python3 sys/evidentia/script/fetch_model.py google/embeddinggemma-300m
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PINS = ROOT / "sys" / "evidentia" / "config" / "models.json"
SKIP = (".cache", "MODEL.json")                   # the downloader's cache and this script's own record: not pinned


class ModelMismatch(RuntimeError):
    """The installed model is not the pinned one (a file changed, missing or added): refused."""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def listing(folder: Path) -> dict[str, dict]:
    """Every file of a model folder (but SKIP), its size and SHA-256 — measured, ~1 s for 1.26 GB (11 Nov)."""
    return {p.relative_to(folder).as_posix(): {"bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(folder.rglob("*")) if p.is_file() and not any(s in p.parts for s in SKIP)}


def pins(path: Path | None = None) -> dict:
    path = path or PINS
    if not path.exists():
        return {}
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def differences(folder: Path, pin: dict) -> list[str]:
    """What differs between a model folder and its pin: changed, missing and unexpected files, by name."""
    have, want = listing(folder), pin["files"]
    out = [f"changed: {n}" for n in sorted(want) if n in have and have[n] != want[n]]
    out += [f"missing: {n}" for n in sorted(want) if n not in have]
    out += [f"not pinned: {n}" for n in sorted(have) if n not in want]
    return out


def check(name: str, models_dir: Path, pins_path: Path | None = None) -> Path:
    """The folder of a pinned model, after its files were checked against the pin; ModelMismatch otherwise (with the
    names of the files that differ), or when the model is not pinned at all — nothing unpinned is ever loaded."""
    folder, pins_path = models_dir / name, pins_path or PINS
    pin = pins(pins_path).get(name)
    if pin is None:
        raise ModelMismatch(f"{name}: not pinned in {pins_path} — fetch it with fetch_model.py first (B30)")
    diff = differences(folder, pin)
    if diff:
        raise ModelMismatch(f"{name} in {folder} is not the pinned model (revision {pin['revision'][:12]}): "
                            + "; ".join(diff) + " — refused, nothing loaded (B30)")
    return folder


def revision(folder: Path) -> str:
    """The git revision hf wrote in its download cache (the first word of a .metadata file), or '' if none."""
    for meta in sorted((folder / ".cache" / "huggingface" / "download").rglob("*.metadata")):
        words = meta.read_text(encoding="utf-8", errors="replace").split()
        if words:
            return words[0]
    return ""


def main(repo: str) -> int:
    name = repo.split("/")[-1]
    dest = ROOT / "sys" / "models" / name
    pin = pins().get(name)
    if (dest / "MODEL.json").exists():
        if pin is None:
            print(f"{dest}: already there (MODEL.json) but not pinned: delete it (the owner) and fetch again to pin")
            return 1
        diff = differences(dest, pin)
        print(f"{dest}: already there, " + (f"NOT the pinned model: {'; '.join(diff)}" if diff else "the pinned model"))
        return 1 if diff else 0
    t0 = time.time()
    cmd = ["hf", "download", repo, "--local-dir", str(dest)] + (["--revision", pin["revision"]] if pin else [])
    r = subprocess.run(cmd, text=True)
    if r.returncode:
        print(f"download failed ({r.returncode}): a gated model needs its licence accepted on huggingface.co first")
        return r.returncode
    files, rev = listing(dest), revision(dest)
    if pin:
        diff = differences(dest, pin)
        if diff:
            print(f"{dest}: the download is NOT the pinned model, refused (MODEL.json not written): {'; '.join(diff)}")
            return 1
    else:
        all_pins = json.loads(PINS.read_text(encoding="utf-8")) if PINS.exists() else {}
        all_pins[name] = {"repo": repo, "revision": rev, "files": files}
        PINS.write_text(json.dumps(all_pins, indent=1) + "\n", encoding="utf-8")
        print(f"{name}: pinned in {PINS} (revision {rev[:12]}, {len(files)} files) — first use: check it against the hub")
    (dest / "MODEL.json").write_text(json.dumps({"repo": repo, "revision": rev, "downloaded": time.strftime("%Y-%m-%d"),
                                                 "seconds": round(time.time() - t0, 1), "files": files}, indent=1) + "\n")
    print(f"{dest}: {len(files)} files, {sum(f['bytes'] for f in files.values()) / 1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "google/embeddinggemma-300m"))
