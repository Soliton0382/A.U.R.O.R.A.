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
from .prj_run import GIT_SAFE

EVERY_S = 300
_cache: dict[str, tuple[float, dict]] = {}


def _git(p: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *GIT_SAFE, "-C", str(p), *args], capture_output=True, text=True, timeout=10).stdout
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


def recent_steps(cfg: sys_config.Config, hours: int = 48, per: int = 4, cloud: bool = False) -> list[dict]:
    """What moved in the owner's projects (owner, 26 Oct: told of a paper published that day, she «non lo sapeva»):
    each project with a commit in the last `hours`, newest first, with its last `per` commit messages and dates.
    cloud: the answer goes to a cloud model, so a project kept «local only» (prj_policy) is left out."""
    try:
        base = cfg.path("AURORA_PROJECTS_DIR")
    except (KeyError, ValueError):
        return []
    from . import prj_policy
    out = []
    for p in sorted(x for x in base.iterdir() if x.is_dir() and (x / ".git").exists()) if base.is_dir() else []:
        if cloud and prj_policy.load(cfg, p.name)["models"] == "local":
            continue
        rows = [line.split("\t", 2) for line in _git(p, "log", f"--since={hours}.hours", f"-{per}",
                                                     "--format=%ct\t%cs\t%s").splitlines() if line.count("\t") >= 2]
        if rows:
            out.append({"project": p.name, "t": int(rows[0][0]),
                        "saved": [{"day": day, "what": what[:200]} for _, day, what in rows]})
    return [{k: v for k, v in r.items() if k != "t"} for r in sorted(out, key=lambda r: -r["t"])]

