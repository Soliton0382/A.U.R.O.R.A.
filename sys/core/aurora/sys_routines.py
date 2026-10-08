# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Routines: the periodic checks the owner switches on, usually from a plugin's suggestions.

A routine is either
    tool   one read-only tool of a plugin, called directly (no model: fast, deterministic), e.g. weather alerts
    agent  a goal for the agent with the plugins' tools, e.g. a weekly report of the GitHub repositories
    story  Aurora's narrated videos on a schedule (kno_story_auto): "action" make (at night) or publish (by day)
and has a schedule: {"every": "hours", "hours": n} | {"every": "day", "at": "HH:MM"} |
{"every": "week", "weekday": 0-6 (Monday 0), "at": "HH:MM"} |
{"every": "custom", "times": ["HH:MM", ...], "days": [0-6, ...] or "group": all | weekdays | weekend | workdays |
holidays} (owner, 2026-10-04: several times, days or groups of days, like a calendar's recurrence), in local time.
workdays: Monday to Friday but not the Italian public holidays; holidays: Saturday, Sunday and those holidays.

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
from datetime import date, datetime, timedelta
from pathlib import Path

from . import sns_clock, sys_config

NOTIFY = ("always", "if_any", "if_new", "never")
NOTHING = re.compile(r"^\s*(niente|nothing|nessuna novit|no news)", re.I)


def _file(cfg: sys_config.Config, name: str) -> Path:
    from . import sys_users_layout                      # the user's routines (the admin's after the migration: U3)
    d = sys_users_layout.place(cfg, "state", cfg.user)
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
    if kind not in ("tool", "agent", "story"):
        raise ValueError("kind must be tool, agent or story")
    if kind == "story" and spec.get("action", "make") not in ("make", "publish"):
        raise ValueError("a story routine makes a video or publishes the one ready (action: make or publish)")
    if "format" in spec and spec["format"] not in ("", "reel", "post", "story"):
        raise ValueError("format: reel, post or story")
    if kind == "tool" and not (spec.get("plugin") and spec.get("tool")):
        raise ValueError("a tool routine needs plugin and tool")
    if kind == "agent" and not str(spec.get("goal", "")).strip():
        raise ValueError("an agent routine needs a goal")
    sch = spec.get("schedule") or {}
    every = sch.get("every")
    if every == "hours":
        if not 1 <= int(sch.get("hours", 0)) <= 168:
            raise ValueError("hours between 1 and 168")
    elif every == "custom":
        times = sch.get("times")
        if not isinstance(times, list) or not 1 <= len(times) <= 12 or \
                not all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(x)) for x in times):
            raise ValueError("times: 1 to 12 of HH:MM")
        if "group" in sch:
            if sch["group"] not in GROUPS:
                raise ValueError(f"group must be one of {GROUPS}")
        elif not isinstance(sch.get("days"), list) or not sch["days"] or \
                not all(isinstance(d, int) and 0 <= d <= 6 for d in sch["days"]):
            raise ValueError("days: a list of 0 (Monday) to 6, or a group")
    elif every in ("day", "week"):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(sch.get("at", ""))):
            raise ValueError("at must be HH:MM")
        if every == "week" and not 0 <= int(sch.get("weekday", -1)) <= 6:
            raise ValueError("weekday between 0 (Monday) and 6")
    else:
        raise ValueError("schedule.every must be hours, day, week or custom")
    if spec.get("notify", "always") not in NOTIFY:
        raise ValueError(f"notify must be one of {NOTIFY}")
    if "propose" in spec and not isinstance(spec["propose"], bool):
        raise ValueError("propose must be true or false")
    # a personal agent (owner, 2026-10-06): an icon, the plugins it may use, memory of its last report, a budget
    if "icon" in spec and (not isinstance(spec["icon"], str) or len(spec["icon"]) > 8):
        raise ValueError("icon: one emoji")
    if "plugins" in spec and (not isinstance(spec["plugins"], list) or len(spec["plugins"]) > 30
                              or not all(isinstance(x, str) and re.fullmatch(r"[a-z0-9_-]{1,40}", x) for x in spec["plugins"])):
        raise ValueError("plugins: a list of plugin names")
    if "memory" in spec and not isinstance(spec["memory"], bool):
        raise ValueError("memory must be true or false")
    if "steps" in spec and not (isinstance(spec["steps"], int) and 3 <= spec["steps"] <= 60):
        raise ValueError("steps between 3 and 60")
    if "minutes" in spec and not (isinstance(spec["minutes"], int) and 1 <= spec["minutes"] <= 60):
        raise ValueError("minutes between 1 and 60")
    if "by" in spec and not (isinstance(spec["by"], str) and re.fullmatch(r"(aurora|template:[a-z0-9_-]{1,30})", spec["by"])):
        raise ValueError("by: aurora or template:<name>")      # who proposed it (the owner's click made it)
    # propose: an agent routine may propose actions that write or publish; each still waits for the owner's approval
    keep = ("title", "plugin", "kind", "tool", "args", "goal", "schedule", "notify", "event", "suggestion", "enabled",
            "propose", "icon", "plugins", "memory", "steps", "minutes", "action", "format", "by")
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
    allowed = {k: v for k, v in changes.items() if k in ("enabled", "schedule", "notify", "title", "propose", "icon",
                                                          "plugins", "memory", "steps", "minutes", "format")
               or k == "goal" and r.get("kind") == "agent"}
    merged = {**r, **allowed}
    validate(merged)
    r.update(allowed)
    r["changed"] = time.time()                           # the owner's fresh choice: Aurora's advice leaves it alone
    _save(cfg, "routines.json", rs)
    return r


def clone(cfg: sys_config.Config, rid: str) -> dict:
    """A copy to change (owner, 2026-10-06): paused, so that it never runs twice before the owner edits it."""
    r = get(cfg, rid)
    if r is None:
        raise KeyError(rid)
    spec = {k: v for k, v in r.items() if k in ("title", "plugin", "kind", "tool", "args", "goal", "schedule", "notify",
                                                "event", "propose", "icon", "plugins", "memory", "steps", "minutes", "action",
                                                "format")}
    spec["title"] = f"{r.get('title', '')[:70]} (copia)"
    return create(cfg, {**spec, "enabled": False})


def delete(cfg: sys_config.Config, rid: str) -> bool:
    rs = all_routines(cfg)
    keep = [r for r in rs if r["id"] != rid]
    _save(cfg, "routines.json", keep)
    return len(keep) != len(rs)


GROUPS = ("all", "weekdays", "weekend", "workdays", "holidays")


def easter(year: int) -> date:
    """Easter Sunday (Gregorian, the anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    return date(year, month, (h + l_ - 7 * m + 114) % 31 + 1)


def holiday_it(d: date) -> bool:
    """An Italian national public holiday (the fixed ones and Easter Monday)."""
    fixed = {(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)}
    return (d.month, d.day) in fixed or d == easter(d.year) + timedelta(days=1)


def day_ok(sch: dict, d: date) -> bool:
    """Whether a custom schedule runs on day d."""
    g = sch.get("group")
    if g is None:
        return d.weekday() in sch["days"]
    return {"all": True, "weekdays": d.weekday() < 5, "weekend": d.weekday() >= 5,
            "workdays": d.weekday() < 5 and not holiday_it(d),
            "holidays": d.weekday() >= 5 or holiday_it(d)}[g]


def _slot(now: datetime, sch: dict) -> datetime:
    """The latest scheduled moment not after `now` (day/week/custom)."""
    if sch["every"] == "custom":
        for back in range(0, 15):                    # a group always has a day within two weeks
            d = (now - timedelta(days=back)).date()
            if not day_ok(sch, d):
                continue
            slots = [now.replace(year=d.year, month=d.month, day=d.day, hour=int(x[:2]), minute=int(x[3:]), second=0,
                                 microsecond=0) for x in sch["times"]]
            past = [s for s in slots if s <= now]
            if past:
                return max(past)
        return now - timedelta(days=15)
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


def person_first(runs: list[dict], now: float, quiet: float, since: list[float], people: tuple) -> str | None:
    """Why the routines wait now, or None: a person's run going on or started in the last `quiet` seconds (C187);
    never more than 15 minutes in a row (`since` keeps when the waiting began); a routine due is never lost."""
    busy = [r for r in runs if r["origin"] in people and (not r["done"] or now - r["started"] < quiet)]
    if not quiet or not busy:
        since.clear()
        return None
    if not since:
        since.append(now)
    if now - since[0] > 900:
        since.clear()
        return None
    return f"a person is using Aurora ({len(busy)} question(s) in the last {quiet:g} s)"


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
    if ok and text.strip() and not NOTHING.match(text):     # an agent's memory: its last real report, not "nothing new"
        r["memory_text"], r["memory_at"] = text[:4000], time.time()
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


def report_pdf(cfg: sys_config.Config, r: dict, text: str, run_id: str, emit, log) -> list[dict]:
    """A routine's report is also a PDF the owner can download (card, conversation, Files page), with the AI
    disclosure; a failure here never fails the routine."""
    from datetime import date
    from . import doc_pdf, sys_uploads
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    try:
        p = doc_pdf.create(f"{(r.get('title') or 'Routine')[:60]} — {date.today().isoformat()}", text, lang, cfg)
    except Exception as e:                               # noqa: BLE001 - the text report stays, the PDF is said missing
        log.warning("routine %s: report PDF not made: %s", r["id"], e)
        emit("routine.pdf", {"routine": r["id"], "ok": False, "error": str(e)[:200]})
        return []
    f = {"name": p.name, "url": f"/v1/aurora/documents/{p.name}", "mime": "application/pdf"}
    sys_uploads.link(cfg, run_id, f["name"], f["url"], f["mime"])
    emit("routine.pdf", {"routine": r["id"], "ok": True, "name": p.name})
    return [f]
