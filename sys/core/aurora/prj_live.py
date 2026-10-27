# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖥️ What is happening in a project, now (owner, 23 Oct: «i terminali li reputo entità vive su ciò che sta
succedendo dentro il progetto anche se io sto solo guardando»): one look at everything that moves in it, for the page's
activity console to tell line by line what changed since its last look.

A snapshot, no history of its own: the conductor's entries (asked, drafted, started, done, failed, replied, with their
status), the conversation with the conductor (how many turns, the last ones), the project's saves (its git history),
the files written last. The page compares two looks and says what is new; the steps of a running phase come from its
run's events (followRun), as before.
"""
from __future__ import annotations

import subprocess

from . import prj_conduct, prj_run, prj_talk, sys_config
from .prj_run import GIT_SAFE

FILES = 30
COMMITS = 15


def _head(text: str, n: int = 160) -> str:
    line = next((x.strip() for x in str(text or "").splitlines() if x.strip()), "")
    line = line.lstrip("#").strip()
    return line if len(line) <= n else line[:n] + "…"


def _commits(root) -> list[dict]:
    if not (root / ".git").exists():
        return []
    try:
        out = subprocess.run(["git", *GIT_SAFE, "-C", str(root), "log", f"-n{COMMITS}", "--format=%h%x09%ct%x09%s"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[1].isdigit():
            rows.append({"hash": parts[0], "t": int(parts[1]), "msg": parts[2][:160]})
    return rows


def snapshot(cfg: sys_config.Config, project: str) -> dict:
    root = prj_conduct._project(cfg, project)            # a valid name, and the project exists
    conduct = [{"id": e.get("id"), "kind": e.get("kind"), "status": e.get("status"), "t": e.get("t"),
                "run_id": e.get("run_id"), "head": _head(e.get("text"))} for e in prj_conduct.history(cfg, project)[-40:]]
    turns = prj_talk.turns(cfg, project)
    files = sorted(prj_run.snapshot(root).items(), key=lambda kv: -kv[1][0])[:FILES]
    return {
        "conduct": conduct,
        "talk": {"n": len(turns), "last": [{"t": x.get("t"), "role": x.get("role"), "head": _head(x.get("text"))}
                                          for x in turns[-6:]]},
        "commits": _commits(root),
        "files": [{"path": p, "t": ns / 1e9, "size": size} for p, (ns, size) in files],
        "running": next((e["run_id"] for e in reversed(conduct)                 # judged: its run is still going
                         if e["status"] in ("running", "judging") and e["run_id"]), None),
    }
