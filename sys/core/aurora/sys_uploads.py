# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Files the owner attached in the chat, kept so that the conversation shows them again after a reload.

Saved in AURORA_UPLOADS_DIR/<yyyy-mm>/<id>-<name> with an index (index.json, 0600 like the files). A file lives as
long as the conversation turn it belongs to (memory turns are never rotated away, only reset), or until the owner
deletes it from the Files page; AURORA_UPLOADS_KEEP_DAYS > 0 also removes it after that many days. Checks and tests
(remember: false) keep nothing.

Served safely: images (but SVG), videos and audio inline; anything else only as a download, never rendered by the
WebUI's origin (an uploaded HTML or SVG must not run there).
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path

from . import sys_config

GRACE_S = 3600
INLINE = re.compile(r"^(image/(jpeg|png|webp|gif|bmp|avif)|video/[\w.+-]+|audio/[\w.+-]+)$")


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_UPLOADS_DIR")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _index(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads((_dir(cfg) / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write_index(cfg: sys_config.Config, items: list[dict]) -> None:
    f = _dir(cfg) / "index.json"
    tmp = f.with_name("index.json.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(items, h, ensure_ascii=False, indent=1)
    os.replace(tmp, f)


def safe_name(name: str) -> str:
    base = re.sub(r"[^\w.\- ]+", "_", Path(name).name).strip(" .") or "file"
    return base[-120:]


def save(cfg: sys_config.Config, run_id: str, name: str, mime: str, data: bytes, role: str = "user") -> dict:
    uid = uuid.uuid4().hex[:16]
    rel = Path(time.strftime("%Y-%m")) / f"{uid}-{safe_name(name)}"
    path = _dir(cfg) / rel
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as h:
        h.write(data)
    item = {"id": uid, "name": Path(name).name[:200], "mime": mime or mimetypes.guess_type(name)[0] or "application/octet-stream",
            "size": len(data), "run_id": run_id, "created": time.time(), "path": str(rel), "role": role}
    items = _index(cfg)
    items.append(item)
    _write_index(cfg, items)
    return item


def link(cfg: sys_config.Config, run_id: str, name: str, url: str, mime: str, role: str = "assistant") -> dict:
    """A file kept elsewhere (a document Aurora wrote) shown with its turn: only the link is indexed."""
    item = {"id": uuid.uuid4().hex[:16], "name": name[:200], "mime": mime or "application/octet-stream", "size": 0,
            "run_id": run_id, "created": time.time(), "link": url, "role": role}
    items = _index(cfg)
    items.append(item)
    _write_index(cfg, items)
    return item


def public(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("path", "link")} | {"role": item.get("role", "user"),
                                                                         "url": item.get("link") or f"/v1/aurora/uploads/{item['id']}",
                                                             "inline": bool(INLINE.match(item["mime"]))}


def all_uploads(cfg: sys_config.Config) -> list[dict]:
    return [public(i) for i in sorted(_index(cfg), key=lambda i: -i["created"])]


def by_run(cfg: sys_config.Config, run_ids: set[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for i in _index(cfg):
        if i["run_id"] in run_ids:
            out.setdefault(i["run_id"], []).append(public(i))
    return out


def get(cfg: sys_config.Config, uid: str) -> tuple[Path, dict] | None:
    item = next((i for i in _index(cfg) if i["id"] == uid), None)
    if item is None or "path" not in item:            # a link is served by its own endpoint
        return None
    path = (_dir(cfg) / item["path"]).resolve()
    if _dir(cfg).resolve() not in path.parents or not path.is_file():
        return None
    return path, item


def delete(cfg: sys_config.Config, uid: str) -> bool:
    items = _index(cfg)
    keep = [i for i in items if i["id"] != uid]
    for i in items:
        if i["id"] == uid and "path" in i:
            (_dir(cfg) / i["path"]).unlink(missing_ok=True)
    _write_index(cfg, keep)
    return len(keep) != len(items)


def purge(cfg: sys_config.Config, live_runs: set[str] | None, now: float | None = None, grace: float = GRACE_S) -> list[str]:
    """Remove the files whose conversation turn is gone (live_runs: the run ids still in memory; None = do not check)
    and, with AURORA_UPLOADS_KEEP_DAYS > 0, the older ones. Returns the removed ids."""
    now = now or time.time()
    days = cfg["AURORA_UPLOADS_KEEP_DAYS"]
    # a file is saved when the question arrives, its turn only when the answer is written: an hour of grace
    gone = [i for i in _index(cfg)
            if (live_runs is not None and i["run_id"] not in live_runs and now - i["created"] > grace)
            or (days > 0 and now - i["created"] > days * 86400)]
    for i in gone:
        delete(cfg, i["id"])
    return [i["id"] for i in gone]


def total_bytes(cfg: sys_config.Config) -> int:
    return sum(i["size"] for i in _index(cfg))
