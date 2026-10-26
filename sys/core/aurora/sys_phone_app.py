# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📱 Aurora's phone app offered by the WebUI (api/phone_app): its sources are sys/app; an APK built and signed on this
machine is put in <AURORA_STATUS_DIR>/app as aurora-app-<version>.apk (sys/app/build.py --to), the one published with
the code is in sys/app/dist; the newest of them is offered."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import sys_config

DIST = Path(__file__).resolve().parents[2] / "app" / "dist"
NAME = re.compile(r"aurora-app-(\d+)\.(\d+)\.(\d+)\.apk")
_sums: dict[tuple[str, float], str] = {}


def newest(cfg: sys_config.Config) -> Path | None:
    found = [(tuple(int(x) for x in m.groups()), f) for d in (cfg.path("AURORA_STATUS_DIR") / "app", DIST)
             for f in (d.iterdir() if d.is_dir() else []) if (m := NAME.fullmatch(f.name)) and f.is_file()]
    return max(found)[1] if found else None


def info(cfg: sys_config.Config) -> dict:
    """{"available", "version", "size", "sha256", "name"}: the app offered on the page."""
    f = newest(cfg)
    if f is None:
        return {"available": False}
    key = (str(f), f.stat().st_mtime)
    if key not in _sums:
        _sums[key] = hashlib.sha256(f.read_bytes()).hexdigest()
    return {"available": True, "name": f.name, "version": NAME.fullmatch(f.name).expand(r"\1.\2.\3"),
            "size": f.stat().st_size, "sha256": _sums[key]}
