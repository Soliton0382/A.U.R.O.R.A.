# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A user's health folder, sealed (owner, 2026-10-05): the dietitian's plans, the trainer's programmes, medical exams.

Three areas — diet, training, exams — in AURORA_HEALTH_DIR (usr/<name>/health/<area>/). A document added keeps its
original and its text (read once, at upload: PDF, image, text), both sealed (sys_seal); a note is text only. An index
per area, sealed too, holds what the page lists (title, kind, day). Nothing here ever goes to a cloud model: the
plugin's tools answer only to a local model (agt_loop, the manifest's "private").
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

from . import sys_config, sys_seal

AREAS = ("diet", "training", "exams")


def _dir(cfg: sys_config.Config, area: str) -> Path:
    if area not in AREAS:
        raise ValueError(f"area: one of {AREAS}")
    return cfg.path("AURORA_HEALTH_DIR") / area


def _index(cfg: sys_config.Config, area: str) -> list[dict]:
    f = _dir(cfg, area) / "index.sealed"
    return json.loads(sys_seal.read(cfg, f, cfg.user)) if f.exists() else []


def _save_index(cfg: sys_config.Config, area: str, items: list[dict]) -> None:
    sys_seal.write(cfg, _dir(cfg, area) / "index.sealed", json.dumps(items, ensure_ascii=False).encode(), cfg.user)


def items(cfg: sys_config.Config, area: str) -> list[dict]:
    return sorted(_index(cfg, area), key=lambda i: -i["at"])


def add_document(cfg: sys_config.Config, area: str, name: str, data: bytes, title: str = "") -> dict:
    from .kno_ingest import read_text
    if not data or len(data) > 40 * 1024 * 1024:
        raise ValueError("a document of 1 byte to 40 MB")
    try:
        text, found = read_text(name, data, cfg)
    except Exception as e:  # noqa: BLE001 — a document without readable text is kept anyway
        text, found = "", Path(name).stem
        text = f"(testo non leggibile: {type(e).__name__})"
    iid = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    ext = re.sub(r"[^a-z0-9.]", "", Path(name).suffix.lower())[:8]
    d = _dir(cfg, area)
    sys_seal.write(cfg, d / f"{iid}{ext}.sealed", data, cfg.user)
    sys_seal.write(cfg, d / f"{iid}.txt.sealed", text.encode(), cfg.user)
    item = {"id": iid, "title": (title or found or Path(name).stem)[:120], "kind": "document", "file": f"{iid}{ext}.sealed",
            "name": Path(name).name[:120], "chars": len(text), "at": time.time()}
    _save_index(cfg, area, _index(cfg, area) + [item])
    return item


def add_note(cfg: sys_config.Config, area: str, title: str, text: str) -> dict:
    """A note (a workout done, a weight, a value of an exam): text only, sealed."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("an empty note")
    iid = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    sys_seal.write(cfg, _dir(cfg, area) / f"{iid}.txt.sealed", text[:20000].encode(), cfg.user)
    item = {"id": iid, "title": (str(title).strip() or text[:60])[:120], "kind": "note", "chars": len(text), "at": time.time()}
    _save_index(cfg, area, _index(cfg, area) + [item])
    return item


def _item(cfg: sys_config.Config, area: str, iid: str) -> dict:
    it = next((i for i in _index(cfg, area) if i["id"] == iid), None)
    if it is None:
        raise KeyError(iid)
    return it


def text(cfg: sys_config.Config, area: str, iid: str) -> str:
    _item(cfg, area, iid)
    return sys_seal.read(cfg, _dir(cfg, area) / f"{iid}.txt.sealed", cfg.user).decode()


def original(cfg: sys_config.Config, area: str, iid: str) -> tuple[str, bytes]:
    it = _item(cfg, area, iid)
    if it["kind"] != "document":
        raise KeyError(iid)
    return it["name"], sys_seal.read(cfg, _dir(cfg, area) / it["file"], cfg.user)


def delete(cfg: sys_config.Config, area: str, iid: str) -> None:
    """Gone for good, not to the trash: a health document is not kept anywhere after its owner deletes it."""
    it = _item(cfg, area, iid)
    for f in [f"{iid}.txt.sealed"] + ([it["file"]] if it.get("file") else []):
        (_dir(cfg, area) / f).unlink(missing_ok=True)
    _save_index(cfg, area, [i for i in _index(cfg, area) if i["id"] != iid])


def everything(cfg: sys_config.Config, area: str, limit: int = 12000) -> str:
    """The texts of an area, newest first, cut to `limit` characters: what a local model reads to answer."""
    out, used = [], 0
    for it in items(cfg, area):
        t = text(cfg, area, it["id"])
        block = f"## {it['title']} ({time.strftime('%d/%m/%Y', time.localtime(it['at']))})\n{t}"
        if used + len(block) > limit:
            out.append(block[: max(0, limit - used)])
            break
        out.append(block)
        used += len(block)
    return "\n\n".join(out)
