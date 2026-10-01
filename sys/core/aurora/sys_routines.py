# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Routines: the periodic checks the owner switches on, usually from a plugin's suggestions.

A routine is either
    tool   one read-only tool of a plugin, called directly (no model: fast, deterministic), e.g. weather alerts
    agent  a goal for the agent with the plugins' tools, e.g. a weekly report of the GitHub repositories
and has a schedule: {"every": "hours", "hours": n} | {"every": "day", "at": "HH:MM"} |
{"every": "week", "weekday": 0-6 (Monday 0), "at": "HH:MM"}, in local time.

Notify: always | if_any (only when there is something: a tool's output is not empty, an agent does not
answer NOTHING) | if_new (if_any, and different from the last notified text: an alert is said once) | never.

aurora-rem asks for the due routines every tick; aurora-api runs them as runs (visible in the Runs page),
stores the result here and notifies. Reading is automatic; anything else a routine's agent wants to do
waits for the owner's approval like any other agent action. Stored in <AURORA_STATUS_DIR>/routines.json.

Plugins suggest routines in their manifest ("routines": [...]) and say what they can do ("welcome");
when a plugin becomes ready, the owner is told once (ready()).
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from . import sns_clock, sys_config

NOTIFY = ("always", "if_any", "if_new", "never")
NOTHING = re.compile(r"^\s*(niente|nothing|nessuna novit|no news)", re.I)


def _file(cfg: sys_config.Config, name: str) -> Path:
    d = cfg.path("AURORA_STATUS_DIR")
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _load(cfg: sys_config.Config, name: str, default):
    try:
        return json.loads(_file(cfg, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(cfg: sys_config.Config, name: str, data) -> None:
    f = _file(cfg, name)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def all_routines(cfg: sys_config.Config) -> list[dict]:
    return _load(cfg, "routines.json", [])


def get(cfg: sys_config.Config, rid: str) -> dict | None:
    return next((r for r in all_routines(cfg) if r["id"] == rid), None)


def validate(spec: dict) -> dict:
    """The fields a routine may have, checked; raises ValueError with the reason."""
    kind = spec.get("kind")
    if kind not in ("tool", "agent"):
        raise ValueError("kind must be tool or agent")
    if kind == "tool" and not (spec.get("plugin") and spec.get("tool")):
        raise ValueError("a tool routine needs plugin and tool")
    if kind == "agent" and not str(spec.get("goal", "")).strip():
        raise ValueError("an agent routine needs a goal")
    sch = spec.get("schedule") or {}
    every = sch.get("every")
    if every == "hours":
        if not 1 <= int(sch.get("hours", 0)) <= 168:
            raise ValueError("hours between 1 and 168")
    elif every in ("day", "week"):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(sch.get("at", ""))):
            raise ValueError("at must be HH:MM")
        if every == "week" and not 0 <= int(sch.get("weekday", -1)) <= 6:
            raise ValueError("weekday between 0 (Monday) and 6")
    else:
        raise ValueError("schedule.every must be hours, day or week")
    if spec.get("notify", "always") not in NOTIFY:
        raise ValueError(f"notify must be one of {NOTIFY}")
    keep = ("title", "plugin", "kind", "tool", "args", "goal", "schedule", "notify", "event", "suggestion", "enabled")
    return {k: spec[k] for k in keep if k in spec}


def create(cfg: sys_config.Config, spec: dict) -> dict:
    r = {"id": uuid.uuid4().hex[:10], "enabled": True, "notify": "always", "args": {}, "created": time.time(),
         "last_run": None, "last_ok": None, "last_text": "", "last_notified": "", **validate(spec)}
    r.setdefault("title", r.get("goal") or f"{r.get('plugin')}.{r.get('tool')}")
    rs = all_routines(cfg)
    rs.append(r)
    _save(cfg, "routines.json", rs)
    return r


def update(cfg: sys_config.Config, rid: str, changes: dict) -> dict:
    rs = all_routines(cfg)
    r = next((x for x in rs if x["id"] == rid), None)
    if r is None:
        raise KeyError(rid)
    allowed = {k: v for k, v in changes.items() if k in ("enabled", "schedule", "notify", "title")}
    merged = {**r, **allowed}
    validate(merged)
    r.update(allowed)
    _save(cfg, "routines.json", rs)
    return r


def delete(cfg: sys_config.Config, rid: str) -> bool:
    rs = all_routines(cfg)
    keep = [r for r in rs if r["id"] != rid]
    _save(cfg, "routines.json", keep)
    return len(keep) != len(rs)


def _slot(now: datetime, sch: dict) -> datetime:
    """The latest scheduled moment not after `now` (day/week)."""
    h, m = (int(x) for x in sch["at"].split(":"))
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if sch["every"] == "day":
        return slot if slot <= now else slot - timedelta(days=1)
    slot -= timedelta(days=(now.weekday() - int(sch["weekday"])) % 7)
    return slot if slot <= now else slot - timedelta(days=7)


def is_due(r: dict, now: datetime) -> bool:
    if not r.get("enabled", True):
        return False
    sch = r["schedule"]
    last = datetime.fromtimestamp(r["last_run"], now.tzinfo) if r.get("last_run") else None
    if sch["every"] == "hours":
        return last is None or now - last >= timedelta(hours=int(sch["hours"]))
    slot = _slot(now, sch)
    created = datetime.fromtimestamp(r.get("created", 0), now.tzinfo)
    return (last is None or last < slot) and created < slot      # a new routine waits for its first slot


def due(cfg: sys_config.Config, now: datetime | None = None) -> list[dict]:
    now = now or sns_clock.now(cfg)
    return [r for r in all_routines(cfg) if is_due(r, now)]


def should_notify(r: dict, text: str, ok: bool) -> bool:
    if not ok:
        return True                                  # a broken routine is always said
    mode = r.get("notify", "always")
    empty = not text.strip() or bool(NOTHING.match(text))
    if mode == "never":
        return False
    if mode == "always":
        return True
    if mode == "if_any":
        return not empty
    return not empty and text.strip() != (r.get("last_notified") or "").strip()      # if_new


def record(cfg: sys_config.Config, rid: str, text: str, ok: bool, run_id: str | None = None,
           files: list[dict] | None = None) -> tuple[dict, bool]:
    """Store a result; (routine, notify?)."""
    rs = all_routines(cfg)
    r = next((x for x in rs if x["id"] == rid), None)
    if r is None:
        raise KeyError(rid)
    notify = should_notify(r, text, ok)
    r.update(last_run=time.time(), last_ok=ok, last_text=text[:4000], last_run_id=run_id, last_files=files or [])
    if notify and ok:
        r["last_notified"] = text[:4000]
    _save(cfg, "routines.json", rs)
    return r, notify


def mark_started(cfg: sys_config.Config, rid: str) -> None:
    """Taken now: a slow routine is not handed out twice by the next tick."""
    rs = all_routines(cfg)
    for r in rs:
        if r["id"] == rid:
            r["last_run"] = time.time()
    _save(cfg, "routines.json", rs)


# ---- plugins: suggestions and welcome ------------------------------------------------------------------

def suggestions(plugins: list, routines: list[dict]) -> list[dict]:
    """The routines that ready plugins suggest, each marked active when the owner already switched it on."""
    active = {r.get("suggestion") for r in routines}
    out = []
    for p in plugins:
        if not p.available:
            continue
        for s in p.manifest.get("routines", []):
            sid = f"{p.name}/{s['id']}"
            out.append({**s, "plugin": p.name, "suggestion": sid, "active": sid in active})
    return out


def from_suggestion(cfg: sys_config.Config, plugins: list, sid: str, lang: str = "it") -> dict:
    s = next((x for x in suggestions(plugins, all_routines(cfg)) if x["suggestion"] == sid), None)
    if s is None:
        raise KeyError(sid)
    if s["active"]:
        raise ValueError("already active")
    title = s.get("title", {})
    spec = {**{k: v for k, v in s.items() if k not in ("id", "active", "description")},
            "title": title.get(lang) or title.get("en") if isinstance(title, dict) else str(title)}
    if isinstance(spec.get("goal"), dict):
        spec["goal"] = spec["goal"].get(lang) or spec["goal"].get("en")
    return create(cfg, spec)


def newly_ready(cfg: sys_config.Config, plugins: list) -> list:
    """Plugins ready now that were not ready at the last look (their welcome is said once)."""
    known = set(_load(cfg, "plugins_ready.json", []))
    ready = {p.name for p in plugins if p.available}
    _save(cfg, "plugins_ready.json", sorted(ready))
    return [p for p in plugins if p.name in ready - known and p.manifest.get("welcome")]
