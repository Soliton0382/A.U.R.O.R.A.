# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Ideas to improve Aurora (owner, 2026-10-06: "a section with ticks and a notes field, so a request for an improvement
is written in a form we can take into consideration").

Each idea: the areas it touches (ticks), its kind (new feature, improvement, simpler, faster, a fix), a priority, a
title and the owner's words; then a state the owner and the developer move along (new → considered → planned → done,
or no, with a note why). Kept per user in their state folder (ideas.json): the owner's words never go to the repository.
as_markdown() is the request as a developer reads it.
"""
from __future__ import annotations

import json
import os
import time
import uuid

from . import sys_config

AREAS = ("chat", "knowledge", "agents", "security", "health", "voice", "interface", "phone", "plugins", "speed", "other")
KINDS = ("feature", "improve", "simpler", "faster", "fix")
PRIORITIES = ("low", "normal", "high")
STATES = ("new", "considered", "planned", "done", "no")


def _file(cfg: sys_config.Config):
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    return d / "ideas.json"


def listing(cfg: sys_config.Config) -> list[dict]:
    f = _file(cfg)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except ValueError:
        return []


def _save(cfg: sys_config.Config, items: list[dict]) -> None:
    f = _file(cfg)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def add(cfg: sys_config.Config, spec: dict) -> dict:
    areas = [a for a in spec.get("areas") or [] if a in AREAS]
    title, text = str(spec.get("title") or "").strip()[:160], str(spec.get("text") or "").strip()[:6000]
    if not (title or text):
        raise ValueError("an idea needs a title or a few words")
    idea = {"id": uuid.uuid4().hex[:8], "at": time.time(), "areas": areas or ["other"],
            "kind": spec.get("kind") if spec.get("kind") in KINDS else "improve",
            "priority": spec.get("priority") if spec.get("priority") in PRIORITIES else "normal",
            "title": title or text[:80], "text": text, "state": "new", "note": ""}
    items = listing(cfg)
    items.insert(0, idea)
    _save(cfg, items)
    return idea


def update(cfg: sys_config.Config, iid: str, changes: dict) -> dict:
    items = listing(cfg)
    it = next((x for x in items if x["id"] == iid), None)
    if it is None:
        raise KeyError(iid)
    if "state" in changes:
        if changes["state"] not in STATES:
            raise ValueError(f"state: one of {STATES}")
        it["state"] = changes["state"]
    if "note" in changes:
        it["note"] = str(changes["note"])[:2000]
    it["changed"] = time.time()
    _save(cfg, items)
    return it


def as_markdown(it: dict) -> str:
    when = time.strftime("%d/%m/%Y", time.localtime(it["at"]))
    return (f"### 💡 {it['title']}\n- tipo: {it['kind']} · priorità: {it['priority']} · aree: {', '.join(it['areas'])} · "
            f"{when} · stato: {it['state']}\n\n{it['text']}" + (f"\n\nNota: {it['note']}" if it.get("note") else ""))
