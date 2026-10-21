# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💗 The work on the projects, read for her emotions (owner, 21 Oct: «se stiamo lavorando su di un progetto anche
quello è interazione con aurora quindi gli stati d'animo devono riflettersi anche con quelle attività»).

From the user's projects themselves, not from a log: the last time one moved (its last commit, its git index, its
open-items file), the steps saved in the last 24 h (commits), and the items still open («- [ ]» in DA_FARE.md or
docs/DA_FARE.md). kno_mood uses them: longing counts from the last of a message and a project's move, satisfaction
counts the saved steps, curiosity the open items. Read at most every 5 minutes per folder.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from . import sys_config

EVERY_S = 300
_cache: dict[str, tuple[float, dict]] = {}


def _git(p: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(p), *args], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _open_items(p: Path) -> int:
    n = 0
    for f in (p / "docs" / "DA_FARE.md", p / "DA_FARE.md"):
        try:
            n += sum(1 for line in f.read_text(encoding="utf-8", errors="replace").splitlines()
                     if line.lstrip().startswith("- [ ]"))
        except OSError:
            pass
    return n


def read(cfg: sys_config.Config, now: float | None = None) -> dict:
    """{"last_s": seconds since a project last moved or None, "last": its name, "steps_24h", "open", "by": {name: …}}."""
    try:
        base = cfg.path("AURORA_PROJECTS_DIR")
    except (KeyError, ValueError):
        return {"last_s": None, "last": None, "steps_24h": 0, "open": 0, "by": {}}
    key = str(base)
    hit = _cache.get(key)
    now = now or time.time()
    if hit and now - hit[0] < EVERY_S:
        return hit[1]
    by, newest, last = {}, 0.0, None
    for p in sorted(x for x in base.iterdir() if x.is_dir() and (x / ".git").exists()) if base.is_dir() else []:
        times = [float(t) for t in _git(p, "log", "--since=24.hours", "--format=%ct").split() if t.strip().isdigit()]
        moved = max([float(_git(p, "log", "-1", "--format=%ct").strip() or 0)]
                    + [f.stat().st_mtime for f in (p / ".git" / "index", p / "docs" / "DA_FARE.md", p / "DA_FARE.md")
                       if f.exists()])
        by[p.name] = {"steps_24h": len(times), "open": _open_items(p), "moved": moved}
        if moved > newest:
            newest, last = moved, p.name
    out = {"last_s": now - newest if newest else None, "last": last,
           "steps_24h": sum(v["steps_24h"] for v in by.values()), "open": sum(v["open"] for v in by.values()), "by": by}
    _cache[key] = (now, out)
    return out
