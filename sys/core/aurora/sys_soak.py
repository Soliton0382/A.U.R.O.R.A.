# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The soak, measured every day by itself (owner, 2026-10-05: "a week of soak" became a measure that collects
itself): once a day aurora-rem writes a snapshot — each service's memory and restarts, the logs' size, the planned
GPU swaps and the failed routines of the last 24 h, the disk's free space — to <AURORA_STATUS_DIR>/soak.jsonl.
The Status page shows the last days; a week of lines is the soak's measure.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import sys_config

SERVICES = ("aurora-api", "aurora-llm", "aurora-models", "aurora-rem", "aurora-harvester", "aurora-sentinel",
            "aurora-https")


def _unit(name: str) -> dict:
    try:
        out = subprocess.run(["systemctl", "show", name, "-p", "MemoryCurrent", "-p", "NRestarts", "-p", "ActiveState"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    v = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    mem = v.get("MemoryCurrent", "")
    return {"mem_mib": round(int(mem) / 2**20, 1) if mem.isdigit() else None,
            "restarts": int(v["NRestarts"]) if v.get("NRestarts", "").isdigit() else None, "state": v.get("ActiveState")}


def _lines_since(path: Path, since: float, *needles: str) -> int:
    """Lines of the last day holding every one of the needles."""
    if not path.is_file():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if all(w in line for w in needles):
            try:
                if datetime.fromisoformat(line[:29]).timestamp() >= since:
                    n += 1
            except ValueError:
                continue
    return n


def snapshot(cfg: sys_config.Config) -> dict:
    logs = cfg.path("AURORA_LOG_DIR")
    since = time.time() - 86400
    size = sum(f.stat().st_size for f in logs.rglob("*") if f.is_file()) if logs.is_dir() else 0
    return {"at": time.time(), "day": time.strftime("%Y-%m-%d"),
            "services": {s: _unit(s) for s in SERVICES},
            "logs_mb": round(size / 1e6, 1),
            "gpu_swaps_24h": _lines_since(logs / "image" / "image.log", since, "planned swap: stopping"),
            "routines_failed_24h": _lines_since(logs / "api" / "api.log", since, "routine ", "failed"),
            "disk_free_gb": round(shutil.disk_usage(cfg.root).free / 1e9, 1)}


def record(cfg: sys_config.Config) -> dict:
    snap = snapshot(cfg)
    f = cfg.path("AURORA_STATUS_DIR") / "soak.jsonl"
    with open(f, "a", encoding="utf-8") as h:
        h.write(json.dumps(snap) + "\n")
    return snap


def days(cfg: sys_config.Config, n: int = 14) -> list[dict]:
    f = cfg.path("AURORA_STATUS_DIR") / "soak.jsonl"
    out = []
    for line in f.read_text(encoding="utf-8").splitlines()[-n:] if f.exists() else []:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
