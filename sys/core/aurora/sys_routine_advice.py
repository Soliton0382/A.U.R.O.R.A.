# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's advice on the agents and routines, each with its «Applica» (owner, 2026-10-08: «i suggerimenti di Aurora mi
passano quasi in sordina! Magari i suggerimenti delle routine nella scheda routine con relativo tasto applica… la
stessa cosa anche per gli agenti»).

Two sources, one list per user (<the user's state>/routine_advice.json):
 code    checks that need no model, made again at every look: two routines doing the same thing at the same time
         (pause one), three or more starting in the same minute (spread them), a routine whose last run failed (run
         it again now), a routine of a plugin that is not ready (pause it)
 aurora  the local model reads the routines with their last results and the plugins ready, and proposes changes,
         pauses and new agents (a goal, the plugins, a time) — at most once a day by itself, or when asked
Every proposal is checked by sys_routines.validate before it is shown: what is shown can be applied. Applying is the
owner's click (the same as switching on a plugin's suggestion); a new agent proposed by Aurora is created with
"by": "aurora". A dismissed proposal is never proposed again.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from . import sys_config, sys_routines

FILE = "routine_advice.json"
DAY_S = 86400
STOP = {"di", "del", "della", "dei", "il", "la", "le", "e", "a", "da", "in", "per", "ogni", "un", "una", "the", "of"}


def _load(cfg: sys_config.Config) -> dict:
    return sys_routines._load(cfg, FILE, {"items": [], "reviewed": 0})


def _save(cfg: sys_config.Config, data: dict) -> None:
    sys_routines._save(cfg, FILE, data)


def _key(a: dict) -> str:
    raw = json.dumps([a["action"], a.get("routine"), a.get("change")], sort_keys=True, ensure_ascii=False)
    return hashlib.blake2b(raw.encode(), digest_size=6).hexdigest()


def _first(sch: dict) -> str:
    if sch.get("every") in ("day", "week"):
        return sch.get("at", "")
    return (sch.get("times") or [""])[0] if sch.get("every") == "custom" else ""


def _days(sch: dict) -> str:
    if sch.get("every") == "week":
        return f"w{sch.get('weekday')}"
    if sch.get("every") == "custom":
        return str(sch.get("group") or sorted(sch.get("days") or []))
    return "all"


def _words(r: dict) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ù]{4,}", f"{r.get('title', '')}".lower()) if w not in STOP}


def _later(at: str, minutes: int) -> str:
    h, m = map(int, at.split(":"))
    t = min(h * 60 + m + minutes, 23 * 60 + 59)
    return f"{t // 60:02d}:{t % 60:02d}"


def _shifted(sch: dict, minutes: int) -> dict:
    if sch["every"] in ("day", "week"):
        return {**sch, "at": _later(sch["at"], minutes)}
    return {**sch, "times": [_later(x, minutes) for x in sch["times"]]}


def checks(routines: list[dict], ready: set[str]) -> list[dict]:
    """The advice that needs no model."""
    out = []
    on = [r for r in routines if r.get("enabled", True)]
    for r in on:                                              # a plugin switched off or not configured
        if r.get("plugin") and r.get("kind") == "tool" and r["plugin"] not in ready:
            out.append({"action": "pause", "routine": r["id"], "title": f"Metti in pausa «{r['title']}»",
                        "why": f"Il plugin {r['plugin']} non è pronto: la routine fallirebbe a ogni giro."})
    for i, a in enumerate(on):                                # the same job twice
        for b in on[i + 1:]:
            same_tool = a.get("kind") == b.get("kind") == "tool" and (a.get("plugin"), a.get("tool")) == (b.get("plugin"), b.get("tool"))
            same_subject = _first(a["schedule"]) and _first(a["schedule"]) == _first(b["schedule"]) \
                and _days(a["schedule"]) == _days(b["schedule"]) and len(_words(a) & _words(b)) >= 2
            if same_tool or same_subject:
                drop = b if same_tool or b.get("kind") == "tool" else a        # keep the agent: it says more
                keep = a if drop is b else b
                out.append({"action": "pause", "routine": drop["id"], "title": f"Metti in pausa «{drop['title']}»",
                            "why": f"Fa lo stesso lavoro di «{keep['title']}», alla stessa ora: un doppione."})
    slots: dict[tuple, list[dict]] = {}                       # three or more in the same minute
    for r in on:
        if (first := _first(r["schedule"])):
            slots.setdefault((first, _days(r["schedule"])), []).append(r)
    for (at, _), rs in slots.items():
        if len(rs) >= 3:
            for n, r in enumerate(rs[1:], 1):
                out.append({"action": "change", "routine": r["id"], "title": f"Sposta «{r['title']}» di {30 * n} minuti",
                            "why": f"{len(rs)} routine partono alle {at}: si mettono in coda e l'ultima finisce tardi.",
                            "change": {"schedule": _shifted(r["schedule"], 30 * n)}})
    for r in on:                                              # the last run failed
        if r.get("last_ok") is False:
            out.append({"action": "run", "routine": r["id"], "title": f"Riprova «{r['title']}»",
                        "why": "L'ultimo giro è fallito: " + (r.get("last_text") or "")[:220]})
    return out


SYS_REVIEW = (
    "You review the owner's periodic agents and routines (Aurora's own work schedule). Read them with their last result "
    "and the plugins that are ready, and propose at most {n} concrete improvements: a goal that contradicts what really "
    "happens, a result that keeps reporting a problem the routine could avoid, a routine that is useless or too frequent, "
    "a time that collides, and NEW agents the owner is missing given the plugins ready and how the owner works. Never propose "
    "something already done by another routine or by the system (listed), nothing about a routine the owner paused (they "
    "paused it on purpose), never to pause or move one set_by_the_owner_recently (their fresh choice), never a change "
    "to a tool routine's tool; in a new agent's goal name only tools listed. "
    "Reply ONLY with a JSON list of "
    "objects: {{\"action\": \"change\"|\"pause\"|\"new\", \"routine\": the id (change, pause) or null (new), \"title\": a short "
    "Italian title, \"why\": one or two Italian sentences, \"change\": for change only the fields to change among goal, "
    "schedule, notify, title; for new {{\"goal\", \"title\", \"plugins\": [names], \"schedule\", \"notify\", \"icon\"}}}}. "
    "schedule is {{\"every\": \"custom\", \"times\": [\"HH:MM\"], \"group\": \"all\"|\"weekdays\"|\"workdays\"}} or "
    "{{\"every\": \"hours\", \"hours\": n}}. notify: always | if_any | if_new | never. An empty list when all is fine.")


def _summary(routines: list[dict]) -> str:
    rows = []
    for r in routines:
        rows.append(json.dumps({"id": r["id"], "title": r.get("title"), "kind": r.get("kind"), "enabled": r.get("enabled", True),
                                "schedule": r.get("schedule"), "notify": r.get("notify"),
                                "goal": (r.get("goal") or f"{r.get('plugin')}.{r.get('tool')}")[:400],
                                "last_ok": r.get("last_ok"), "last_result": (r.get("last_text") or "")[:500],
                                "set_by_the_owner_recently": time.time() - max(float(r.get("created") or 0),
                                                                                   float(r.get("changed") or 0)) < 3 * DAY_S},
                               ensure_ascii=False))
    return "\n".join(rows)


def _checked(a: dict, by_id: dict) -> dict | None:
    """The proposal made applicable, or None (an unknown routine, a spec validate refuses, a kind not allowed)."""
    act, rid = a.get("action"), a.get("routine")
    if act not in ("change", "pause", "new") or not str(a.get("title", "")).strip():
        return None
    out = {"action": act, "routine": rid, "title": str(a["title"])[:120], "why": str(a.get("why", ""))[:400]}
    try:
        if act in ("change", "pause"):
            r = by_id.get(rid)
            if r is None:
                return None
            if act == "change":
                change = {k: v for k, v in (a.get("change") or {}).items()
                          if k in ("schedule", "notify", "title") or k == "goal" and r.get("kind") == "agent"}
                if not change:
                    return None
                sys_routines.validate({**r, **change})
                out["change"] = change
        else:
            spec = {k: v for k, v in (a.get("change") or {}).items()
                    if k in ("goal", "title", "plugins", "schedule", "notify", "icon")}
            out["change"] = {"kind": "agent", "event": "routine.done", **sys_routines.validate({"kind": "agent", **spec})}
    except (ValueError, TypeError):
        return None
    return out


def review(llm, routines: list[dict], plugins: list[dict], system: list[str] = (), n: int = 6) -> list[dict]:
    """Aurora's proposals, each one checked. plugins: [{"name", "description", "tools"}]; system: what the machine does
    by itself outside the routines (the backup timer, the night's dreams and study…)."""
    ready = "\n".join(f"- {p['name']}: {str(p.get('description', ''))[:160]} — tools: {', '.join(p.get('tools', [])[:20])}"
                      for p in plugins)
    on = [r for r in routines if r.get("enabled", True)]
    paused = ", ".join(f"«{r.get('title')}»" for r in routines if not r.get("enabled", True)) or "none"
    raw = llm.complete(SYS_REVIEW.format(n=n), f"ROUTINES:\n{_summary(on)}\n\nPAUSED BY THE OWNER (leave them): {paused}\n\n"
                       f"DONE BY THE SYSTEM ALREADY:\n" + "\n".join(f"- {x}" for x in system) + f"\n\nPLUGINS READY:\n{ready}",
                       2500, think=False)
    raw = str(getattr(raw, "answer", raw))
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    by_id = {r["id"]: r for r in on}
    return [c for c in (_checked(a, by_id) for a in items if isinstance(a, dict)) if c][:n]


def current(cfg: sys_config.Config, ready: set[str]) -> dict:
    """{"items": the open advice (code's made now, Aurora's kept), "reviewed": when Aurora last looked}."""
    data = _load(cfg)
    closed = {a["key"] for a in data["items"] if a.get("status") in ("applied", "dismissed")}
    code = []
    for a in checks(sys_routines.all_routines(cfg), ready):
        a = {**a, "by": "code", "key": _key(a)}
        if a["key"] not in closed:
            code.append({**a, "id": a["key"], "status": "open"})
    kept = [a for a in data["items"] if a.get("by") == "aurora" and a.get("status") == "open"]
    live = {r["id"] for r in sys_routines.all_routines(cfg)}
    kept = [a for a in kept if a["action"] == "new" or a.get("routine") in live]
    return {"items": code + kept, "reviewed": data.get("reviewed", 0)}


def due(cfg: sys_config.Config, now: float | None = None) -> bool:
    return (now or time.time()) - _load(cfg).get("reviewed", 0) >= DAY_S


def remember(cfg: sys_config.Config, fresh: list[dict]) -> int:
    """Aurora's new proposals kept (not those already open, applied or dismissed); how many are new."""
    data = _load(cfg)
    known = {a["key"] for a in data["items"]}
    added = 0
    for a in fresh:
        k = _key(a)
        if k not in known:
            data["items"].append({**a, "by": "aurora", "key": k, "id": k, "status": "open", "at": time.time()})
            added += 1
    data["reviewed"] = time.time()
    data["items"] = data["items"][-200:]
    _save(cfg, data)
    return added


def _close(cfg: sys_config.Config, a: dict, status: str) -> None:
    data = _load(cfg)
    for x in data["items"]:
        if x["key"] == a["key"]:
            x["status"], x["closed"] = status, time.time()
            break
    else:
        data["items"].append({**a, "status": status, "closed": time.time()})
    _save(cfg, data)


def find(cfg: sys_config.Config, aid: str, ready: set[str]) -> dict:
    a = next((x for x in current(cfg, ready)["items"] if x["id"] == aid), None)
    if a is None:
        raise KeyError(aid)
    return a


def apply(cfg: sys_config.Config, aid: str, ready: set[str]) -> dict:
    """The owner's click: the change made. {"advice", "routine"} — and "run" when the routine must run now."""
    a = find(cfg, aid, ready)
    out = {"advice": a["id"]}
    if a["action"] == "pause":
        out["routine"] = sys_routines.update(cfg, a["routine"], {"enabled": False})
    elif a["action"] == "change":
        out["routine"] = sys_routines.update(cfg, a["routine"], a["change"])
    elif a["action"] == "new":
        out["routine"] = sys_routines.create(cfg, {**a["change"], "by": "aurora"})
    elif a["action"] == "run":
        out["run"] = a["routine"]
    if a["action"] != "run":                                 # a run again leaves the check to the next result
        _close(cfg, a, "applied")
    return out


def dismiss(cfg: sys_config.Config, aid: str, ready: set[str]) -> None:
    _close(cfg, find(cfg, aid, ready), "dismissed")
