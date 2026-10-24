# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📱 Aurora's phone app offered by the WebUI (api/phone_app): built and signed on this machine, outside the repository
(its own project), and put in <AURORA_STATUS_DIR>/app as aurora-app-<version>.apk; the newest one is offered."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import sys_config

NAME = re.compile(r"aurora-app-(\d+)\.(\d+)\.(\d+)\.apk")
_sums: dict[tuple[str, float], str] = {}


def newest(cfg: sys_config.Config) -> Path | None:
    d = cfg.path("AURORA_STATUS_DIR") / "app"
    found = [(tuple(int(x) for x in m.groups()), f) for f in (d.iterdir() if d.is_dir() else [])
             if (m := NAME.fullmatch(f.name)) and f.is_file()]
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
