# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner steers the harvester from the WebUI: shared by aurora-api and aurora-harvester.

Commands travel as files in <AURORA_STATUS_DIR>/harvest/commands/ (written atomically by the API,
taken by the harvester within seconds, even while it sleeps); the harvester reports its state in
<AURORA_STATUS_DIR>/harvest/status.json. A batch is a list of arXiv ids or links: each paper goes
to the domain of its primary category, as in the regular rounds.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

from . import sys_config

_NEW = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\d])")
_OLD = re.compile(r"\b([a-z][a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b")
MAX_BATCH = 200


def parse_items(text: str) -> tuple[list[str], list[str]]:
    """(arXiv ids, lines that are not arXiv) from free text: ids, arXiv:ids, abs/pdf links, one per line."""
    ids, unsupported = [], []
    for line in (x.strip() for x in text.splitlines()):
        if not line:
            continue
        found = _NEW.findall(line) or _OLD.findall(line)
        if found and ("arxiv" in line.lower() or re.fullmatch(r"[\w:./\-\s,;]+", line)):
            ids += [f for f in found if f not in ids]
        else:
            unsupported.append(line[:200])
    return ids[:MAX_BATCH], unsupported


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "harvest"
    (d / "commands").mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def send(cfg: sys_config.Config, cmd: str, **args) -> dict:
    item = {"id": uuid.uuid4().hex[:10], "cmd": cmd, "at": time.time(), **args}
    _write(_dir(cfg) / "commands" / f"{time.time_ns()}-{item['id']}.json", item)
    return item


def take(cfg: sys_config.Config) -> list[dict]:
    """The pending commands, oldest first, removed from the queue."""
    out = []
    for f in sorted((_dir(cfg) / "commands").glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            pass
        f.unlink(missing_ok=True)
    return out


def pending(cfg: sys_config.Config) -> int:
    return len(list((_dir(cfg) / "commands").glob("*.json")))


def status(cfg: sys_config.Config) -> dict:
    f = _dir(cfg) / "status.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "unknown"}


def set_status(cfg: sys_config.Config, **fields) -> dict:
    st = {**status(cfg), **fields, "updated": time.time()}
    _write(_dir(cfg) / "status.json", st)
    return st
