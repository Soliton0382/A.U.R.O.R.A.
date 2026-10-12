# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A new device in Home Assistant gets its agents (owner, 2026-10-12: «rendiamola indipendente nel generarsi gli
agenti/tools necessari quando si collega un device nuovo in base al device in questione»).

No new code a device: Home Assistant shows every device, whatever its brand, as entities and services, and the
homeassistant plugin's tools are the same for all (devices, states, history, camera_look, call_service). What a device
needs is agents that use them for it: a camera, a printer, a thermometer, a plug each want different watches.

Every AURORA_HA_DEVICE_CHECK_MIN minutes (aurora-rem's tick) the devices are read (the plugin's `devices`) and compared
with those already seen (the user's state, ha_devices.json: the token, and so the house, is each user's own). For each new one the local model reads its entities and writes up
to three agents for it (a goal with the plugin's tools, a time, when to tell); each is checked as any proposal of
Aurora (sys_routine_advice) and never commands a device — a command stays the owner's approval at the moment.
AURORA_HA_DEVICE_AGENTS: 0 nothing; 1 the agents proposed in 🤖 Agenti e routine with «Applica» (the default); 2 created
by Aurora herself (🧭 Autonomy, area «devices»), written in the ledger.
A device that leaves is forgotten: if it comes back, it is new again.
"""
from __future__ import annotations

import json
import re
import time

from . import sys_config

FILE = "ha_devices.json"
SYS = """You set up a home assistant's watches for ONE device just connected to Home Assistant. You get the device (name,
maker, model) and its entities (id, domain, device class, unit, state). Propose at most {n} agents that are really useful
FOR THIS DEVICE, in Italian, as a JSON list only:
[{{"title": "emoji + short title", "icon": "one emoji", "goal": "what the agent does, step by step, naming the entity ids
and the tools", "schedule": {{"every": "hours", "hours": N}} or {{"every": "day", "at": "HH:MM"}}, "notify": "if_new" |
"if_any" | "always", "why": "one sentence for the owner"}}]
Tools of the plugin homeassistant: states(filter) the current state; history(entity_id, hours) the changes;
camera_look(entity_id, instruction) a picture of a camera described (it waits for the owner's approval every time:
only in an agent that runs at most once a day). NEVER call_service and never any change to the device: read only.
Each goal ends with: «Se non c'è niente da segnalare rispondi soltanto: NIENTE.» (with notify "if_new" or "if_any").
Good watches: something wrong or unusual (offline, error, low battery, a detection switched off, a value out of range),
a daily summary only when it says something. No agent that only repeats a state that never changes. If the device
needs no watch, reply []."""


def seen(cfg: sys_config.Config) -> dict:
    from . import sys_routines
    return sys_routines._load(cfg, FILE, {"devices": {}, "checked": 0})


def due(cfg: sys_config.Config, now: float | None = None) -> bool:
    if int(cfg["AURORA_HA_DEVICE_AGENTS"]) <= 0:
        return False
    return (now or time.time()) - seen(cfg).get("checked", 0) >= int(cfg["AURORA_HA_DEVICE_CHECK_MIN"]) * 60


def new_devices(cfg: sys_config.Config, devices: list[dict], now: float | None = None) -> list[dict]:
    """The devices not seen before (those gone are forgotten); the list kept."""
    data = seen(cfg)
    old = data.get("devices", {})
    fresh = [d for d in devices if d.get("id") and d["id"] not in old]
    data["devices"] = {d["id"]: old.get(d["id"]) or {"name": d.get("name", ""), "model": d.get("model", ""),
                                                     "first": now or time.time()} for d in devices if d.get("id")}
    data["checked"] = now or time.time()
    from . import sys_routines
    sys_routines._save(cfg, FILE, data)
    return fresh


def describe(d: dict) -> str:
    lines = [f"DEVICE: {d.get('name', '')} — {d.get('manufacturer', '')} {d.get('model', '')}".strip()]
    for e in d.get("entities", [])[:60]:
        extra = ", ".join(x for x in (e.get("device_class", ""), e.get("unit", "")) if x)
        lines.append(f"- {e['entity_id']} ({e.get('name', '')}{'; ' + extra if extra else ''}): {e.get('state', '')}")
    return "\n".join(lines)


def proposals(llm, d: dict, n: int = 3) -> list[dict]:
    """The agents for one device, each checked as any of Aurora's proposals; none that commands the device."""
    from . import sys_routine_advice
    raw = llm.complete(SYS.format(n=n), describe(d), 1500, think=False)
    raw = str(getattr(raw, "answer", raw))
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    out = []
    for a in items[:n] if isinstance(items, list) else []:
        if not isinstance(a, dict) or "call_service" in json.dumps(a):
            continue                                     # read only: a command is the owner's, at the moment
        change = {k: a[k] for k in ("goal", "title", "schedule", "notify", "icon") if k in a}
        change["plugins"] = ["homeassistant"]
        c = sys_routine_advice._checked({"action": "new", "title": a.get("title", ""), "change": change,
                                         "why": f"{d.get('name', '')}: {a.get('why', '')}"}, {})
        if c:
            c["change"]["memory"] = True                     # it tells only what is new since its last report
            out.append(c)
    return out


def welcome(cfg: sys_config.Config, llm, devices: list[dict]) -> dict:
    """The new devices and what was done for them: proposed (level 1) or created (level 2)."""
    from . import sys_autonomy, sys_routine_advice, sys_routines
    level = int(cfg["AURORA_HA_DEVICE_AGENTS"])
    fresh = new_devices(cfg, devices)
    report = {"new": [d.get("name", "") for d in fresh], "proposed": 0, "created": []}
    for d in fresh:
        props = proposals(llm, d)
        if level >= 2:
            for p in props:
                r = sys_routines.create(cfg, {**p["change"], "by": "aurora"})
                report["created"].append(r.get("title", ""))
                sys_autonomy.log(cfg, "devices", f"{d.get('name', '')}: agente «{r.get('title', '')}» creato")
        elif props:
            report["proposed"] += sys_routine_advice.remember(cfg, props, reviewed=False)
    return report


def message(report: dict) -> str:
    """The owner's notification, in Italian (empty when nothing new)."""
    if not report["new"]:
        return ""
    names = ", ".join(f"«{n}»" for n in report["new"])
    if report["created"]:
        return (f"🏠 Nuovo dispositivo in Home Assistant: {names}. Ho creato {len(report['created'])} agenti per "
                f"tenerlo d'occhio: {', '.join(report['created'])} (🤖 Agenti e routine).")
    if report["proposed"]:
        return (f"🏠 Nuovo dispositivo in Home Assistant: {names}. Ti propongo {report['proposed']} agenti su misura "
                "nella pagina 🤖 Agenti e routine, con «Applica».")
    return f"🏠 Nuovo dispositivo in Home Assistant: {names}. Lo vedo; per ora non serve un controllo periodico."
