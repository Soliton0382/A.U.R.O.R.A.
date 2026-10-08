# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A version's section of CHANGELOG.md, from the published history (the mirror's git log since the last tag).

    python dev_changelog.py MIRROR VERSION "message of the commit about to be made"

Writes the section on top of CHANGELOG.md (this installation's, published with it) and sets pyproject.toml's version.
Refuses a version not above the current one, or a tag already in the mirror. The commit subjects are the owner's
words of each publication: what the release notes say, nothing written by hand afterwards."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HEAD = ("# Changelog\n\nEach version is a signed tag; its notes are the publications since the one before (newest first). "
        "Numbers and proofs: docs/MEASUREMENTS.md, docs/BUGS.md.\n")


def _git(mirror: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(mirror), *args], capture_output=True, text=True, check=True).stdout


def _ver(v: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        raise SystemExit(f"version {v!r}: X.Y.Z")
    return tuple(int(x) for x in v.split("."))


def main() -> int:
    mirror, version, message = Path(sys.argv[1]).resolve(), sys.argv[2].removeprefix("v"), sys.argv[3]
    py = ROOT / "pyproject.toml"
    text = py.read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"$', text, re.M)
    if not m or text.count(m.group(0)) != 1:
        raise SystemExit("pyproject.toml: no single version line")
    if _ver(version) <= _ver(m.group(1)):
        raise SystemExit(f"version {version} is not above {m.group(1)}")
    if f"v{version}" in _git(mirror, "tag").split():
        raise SystemExit(f"tag v{version} is already in the mirror")
    tags = [t for t in _git(mirror, "tag", "--sort=-creatordate").split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    since = f"{tags[0]}..HEAD" if tags else "HEAD"
    log = _git(mirror, "log", "--format=%ad\x1f%s", "--date=short", since).splitlines()
    rows = [f"- {time.strftime('%Y-%m-%d')} {message}"] + [f"- {d} {s}" for d, s in (l.split("\x1f", 1) for l in log)]
    title = f"## v{version} — {time.strftime('%Y-%m-%d')}"
    intro = (f"{len(rows)} publications since {tags[0]}." if tags else
             f"The first tagged version: {len(rows)} publications since the first public one (0.1.0, untagged).")
    cl = ROOT / "CHANGELOG.md"
    old = cl.read_text(encoding="utf-8") if cl.exists() else HEAD
    body = old[len(HEAD):] if old.startswith(HEAD) else old
    cl.write_text(HEAD + f"\n{title}\n\n{intro}\n\n" + "\n".join(rows) + "\n" + body, encoding="utf-8")
    py.write_text(text.replace(m.group(0), f'version = "{version}"'), encoding="utf-8")
    print(f"CHANGELOG.md: {title} ({len(rows)} lines); pyproject.toml {m.group(1)} -> {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
