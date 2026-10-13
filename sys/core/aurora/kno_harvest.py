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
_WIKI = re.compile(r"https?://([a-z]{2,3})\.(?:m\.)?wikipedia\.org/wiki/([^\s#?]+)(?:\s+([a-z_]+))?")
MAX_BATCH = 200


def possible(arxiv_id: str, now: float | None = None) -> bool:
    """A new-style id that could exist: its YYMM a month from April 2007 (the scheme's start) to this one (13 Oct:
    «9999.99999» was asked, «not found on arXiv», and stayed on the page as if it were a count)."""
    if "/" in arxiv_id:
        return True                                   # the old scheme (hep-th/9901001): its own checks at arXiv
    yy, mm = int(arxiv_id[:2]), int(arxiv_id[2:4])
    t = time.gmtime(now or time.time())
    return 1 <= mm <= 12 and (7, 4) <= (yy, mm) <= (t.tm_year % 100, t.tm_mon)


def parse_items(text: str) -> tuple[list[str], list[str]]:
    """(items, lines not taken) from free text, one per line: arXiv ids, arXiv:ids, abs/pdf links — an id that cannot
    exist (a month 13, a date to come) is said among the lines not taken — and Wikipedia links, optionally followed by
    the domain to put the article in («https://en.wikipedia.org/wiki/Cold_fusion physics»; otherwise the harvester
    chooses it by reading the article: kno_domain)."""
    ids, unsupported = [], []
    for line in (x.strip() for x in text.splitlines()):
        if not line:
            continue
        w = _WIKI.search(line)
        if w:                                         # a Wikipedia article, in the domain written after it (general)
            from urllib.parse import unquote
            item = f"wikipedia:{w.group(1)}:{unquote(w.group(2)).replace('_', ' ')}@{w.group(3) or ''}"   # "": read
            if item not in ids:
                ids.append(item)
            continue
        found = _NEW.findall(line) or _OLD.findall(line)
        bad = [f for f in found if not possible(f)]
        if bad:
            unsupported.append(f"{line[:180]} — id impossibile: {', '.join(bad)}")
            found = [f for f in found if possible(f)]
            if not found:
                continue
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
