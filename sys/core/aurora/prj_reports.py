# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's reports on a project (owner, 2026-10-05): every agent run that worked on a project leaves its final report
with that project, shown in the project's page beside the alerts and the chat. Kept per user in their state folder
(<AURORA_STATUS_DIR>/users/<name>/projects/<project>/reports.jsonl), never inside the project's own repository."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import sys_config, sys_users_layout as L

NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def _file(cfg: sys_config.Config, project: str) -> Path:
    if not NAME.fullmatch(project or ""):
        raise ValueError("a project's name")
    return L.place(cfg, "state", cfg.user) / "projects" / project / "reports.jsonl"


def add(cfg: sys_config.Config, project: str, report: dict) -> None:
    f = _file(cfg, project)
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(f, "a", encoding="utf-8") as h:
        h.write(json.dumps({"at": time.time(), **report}, ensure_ascii=False) + "\n")


def all_of(cfg: sys_config.Config, project: str) -> list[dict]:
    f = _file(cfg, project)
    out = []
    for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[::-1]
