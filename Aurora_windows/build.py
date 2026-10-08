#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Build Aurora for this port (the folder's name: Aurora_mac or Aurora_windows) from the published Linux Aurora.

    python3 build.py [--out DIR] [--test] [--suite] [--probe [--json FILE]]

One truth: the Linux code as published (the mirror this folder lives in). The port is that code plus this folder's
files (sys/...) plus REWRITES: each one changes one place of the Linux code, found by an anchor that must be there
exactly once (law 3) — when the Linux code moves, the build stops and says which rewrite to look at, never guesses.
The same script in both port folders; it refuses to build when the files the two ports share differ.
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

HERE = Path(__file__).resolve().parent
PORT = HERE.name                                          # Aurora_mac | Aurora_windows
MIRROR = HERE.parent
SIBLING = MIRROR / ("Aurora_windows" if PORT == "Aurora_mac" else "Aurora_mac")
SHARED = ["sys/core/aurora/sys_platform/__init__.py", "sys/core/aurora/sys_platform/base.py",
          "sys/core/aurora/sys_platform/linux.py", "sys/core/tests/test_platform_linux.py",
          "sys/core/tests/test_platform_residue.py", "build.py", "rewrites.py", "probe.py"]
SKIP_TOP = {".git", "Aurora_mac", "Aurora_windows"}
MARK = "BUILD.json"

sys.path.insert(0, str(HERE))
from rewrites import REWRITES  # noqa: E402 — (file, anchor, replacement, why), one area at a time


def fail(msg: str) -> None:
    print(f"ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def check_shared() -> None:
    if not SIBLING.is_dir():
        print(f"  (no {SIBLING.name} next to this folder: shared files not compared)")
        return
    differ = [f for f in SHARED if (HERE / f).read_bytes() != (SIBLING / f).read_bytes()]
    if differ:
        fail(f"shared files differ from {SIBLING.name}: {', '.join(differ)} — copy the newer one to both")


def source_files() -> list[Path]:
    out = []
    for top in sorted(MIRROR.iterdir()):
        if top.name in SKIP_TOP:
            continue
        out += [top] if top.is_file() else [p for p in sorted(top.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=MIRROR.parent / "Aurora_build" / PORT)
    ap.add_argument("--test", action="store_true", help="run the platform tests on the built tree")
    ap.add_argument("--suite", action="store_true", help="run the whole Linux suite on the built tree: the proof that "
                                                       "the rewrites keep Linux as it is")
    ap.add_argument("--probe", action="store_true", help="call the platform backend for real on THIS machine (probe.py)")
    ap.add_argument("--json", type=Path, help="--probe: also write its rows here")
    a = ap.parse_args()
    if PORT not in ("Aurora_mac", "Aurora_windows"):
        fail(f"this script lives in Aurora_mac or Aurora_windows, not in {PORT}")
    out = a.out.resolve()
    if out == MIRROR or MIRROR in out.parents or out in MIRROR.parents:
        fail(f"{out}: a build goes outside the mirror (never into what is committed), e.g. ../Aurora_build")
    print(f"== {PORT}: shared files")
    check_shared()
    if out.exists():
        if not (out / MARK).is_file():
            fail(f"{out} exists and is not a build of this script: not touched")
        shutil.rmtree(out)
    print(f"== copy the Linux code from {MIRROR}")
    files = source_files()
    for f in files:
        dst = out / f.relative_to(MIRROR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    print(f"  {len(files)} files")
    print("== this port's files")
    overlay = [p for p in sorted((HERE / "sys").rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    for f in overlay:
        dst = out / f.relative_to(HERE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        print(f"  {'replaced' if (MIRROR / f.relative_to(HERE)).exists() else 'added   '} {f.relative_to(HERE)}")
    print(f"== rewrites ({len(REWRITES)})")
    for path, anchor, new, why in REWRITES:
        p = out / path
        text = p.read_text(encoding="utf-8")
        n = text.count(anchor)
        if n != 1:
            fail(f"{path}: the anchor of «{why}» is there {n} times, not once — the Linux code moved: look at it")
        p.write_text(text.replace(anchor, new), encoding="utf-8")
        print(f"  {path}: {why}")
    (out / MARK).write_text(json.dumps({"port": PORT, "built": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                        "files": len(files), "overlay": [str(f.relative_to(HERE)) for f in overlay],
                                        "rewrites": [r[3] for r in REWRITES]}, indent=1), encoding="utf-8")
    print(f"== built: {out}")
    if a.probe:
        r = subprocess.run([sys.executable, str(HERE / "probe.py"), str(out)] + (["--json", str(a.json)] if a.json else []),
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        if r.returncode or not (a.test or a.suite):
            sys.exit(r.returncode)
    if a.test or a.suite:
        tests = (["tests", "--ignore=tests/test_models_gpu.py"] if a.suite else
                 sorted(str(p.relative_to(out / "sys" / "core")) for p in (out / "sys" / "core" / "tests").glob("test_platform_*.py")))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:warnings", *tests],
                           cwd=out / "sys" / "core", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
