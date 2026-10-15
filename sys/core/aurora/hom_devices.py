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
# what the 🏠 page may do with a click (api/home): simple services of one entity; scripts, automations… stay in the chat
ALLOWED = {"switch": {"turn_on", "turn_off", "toggle"}, "light": {"turn_on", "turn_off", "toggle"},
           "fan": {"turn_on", "turn_off", "toggle"}, "input_boolean": {"turn_on", "turn_off", "toggle"},
           "button": {"press"}, "number": {"set_value"}, "cover": {"open_cover", "close_cover", "stop_cover"},
           "lock": {"lock", "unlock"}, "media_player": {"media_play", "media_pause", "turn_on", "turn_off"}}
SYS = """You set up a home assistant's watches for the devices of one kind just connected to Home Assistant. You get each
device (name, maker, model) and its entities (id, domain, device class, unit, state). Propose at most {n} agents that are
really useful FOR THESE DEVICES — one agent may watch them all — in Italian, as a JSON list only:
[{{"title": "emoji + short title", "icon": "one emoji", "goal": "what the agent does, step by step, naming the entity ids
and the tools", "schedule": {{"every": "hours", "hours": N}} or {{"every": "day", "at": "HH:MM"}}, "notify": "if_new" |
"if_any" | "always", "why": "one sentence for the owner"}}]
Tools of the plugin homeassistant: states(filter) the current state; history(entity_id, hours) the changes;
camera_look(entity_id, instruction) a picture of a camera described (it waits for the owner's approval every time:
only in an agent that runs at most once a day). NEVER call_service and never any change to the device: read only.
Each goal ends with: «Se non c'è niente da segnalare rispondi soltanto: NIENTE.» (with notify "if_new" or "if_any").
Good watches: something wrong or unusual (offline, error, low battery, a detection switched off, a value out of range),
a daily summary only when it says something. A state «unavailable» means the device cannot be reached now: telling when
it stays unreachable is a good watch. Examples by kind (C271: the model proposed nothing for lights and plugs):
- plugs with power/energy sensors: a weekly consumption summary (history of the energy sensor), an alert when one stays
  unreachable for hours, a plug drawing power at an unusual hour
- lights: an evening check that outdoor lights are not on in the daytime or left on all night (history), unreachable ones
- cameras: the detections still switched on, the signal, a daily look
- sensors: values out of a sensible range, a battery low, no update for hours
Reply [] only for a device with nothing that can go wrong or be worth a summary."""


def seen(cfg: sys_config.Config) -> dict:
    from . import sys_routines
    return sys_routines._load(cfg, FILE, {"devices": {}, "checked": 0})


def due(cfg: sys_config.Config, now: float | None = None) -> bool:
    if int(cfg["AURORA_HA_DEVICE_AGENTS"]) <= 0:
        return False
    return (now or time.time()) - seen(cfg).get("checked", 0) >= int(cfg["AURORA_HA_DEVICE_CHECK_MIN"]) * 60


def changes(old: dict, devices: list[dict]) -> dict:
    """What changed in devices already known (owner, 12 Oct: «verifica se quando cambio il nome dei dispositivi aurora
    si aggiorna»): {"names": [(before, now)], "entities": {old entity id: new}} — an entity id is taken as renamed when,
    in one device and one domain, exactly one id went away and exactly one came."""
    names, ids = [], {}
    for d in devices:
        was = old.get(d.get("id"))
        if not was:
            continue
        if was.get("name") and was["name"] != d.get("name"):
            names.append((was["name"], d.get("name", "")))
        if "entities" not in was:                     # recorded before entities were kept: nothing to compare yet
            continue
        now_ids = {e["entity_id"] for e in d.get("entities", [])}
        gone, came = set(was["entities"]) - now_ids, now_ids - set(was["entities"])
        for dom in {x.split(".", 1)[0] for x in gone | came}:
            g, c = [x for x in gone if x.startswith(dom + ".")], [x for x in came if x.startswith(dom + ".")]
            if len(g) == 1 and len(c) == 1:
                ids[g[0]] = c[0]
    return {"names": names, "entities": ids}


def follow(cfg: sys_config.Config, ids: dict[str, str]) -> list[str]:
    """The agents that name an entity renamed in Home Assistant, written with its new id; their titles."""
    from . import sys_routines
    done = []
    for r in sys_routines.all_routines(cfg):
        text = json.dumps({k: r.get(k) for k in ("goal", "args")}, ensure_ascii=False)
        hit = {a: b for a, b in ids.items() if re.search(rf"(?<![\w.]){re.escape(a)}(?![\w])", text)}
        if not hit:
            continue
        goal = str(r.get("goal", ""))
        for a, b in hit.items():
            goal = re.sub(rf"(?<![\w.]){re.escape(a)}(?![\w])", b, goal)
        sys_routines.update(cfg, r["id"], {"goal": goal})
        done.append(r.get("title", ""))
    return done


def new_devices(cfg: sys_config.Config, devices: list[dict], now: float | None = None) -> list[dict]:
    """The devices not seen before (those gone are forgotten); the list kept with today's names and entities."""
    data = seen(cfg)
    old = data.get("devices", {})
    fresh = [d for d in devices if d.get("id") and d["id"] not in old]
    data["devices"] = {d["id"]: {"name": d.get("name", ""), "model": d.get("model", ""),
                                 "first": (old.get(d["id"]) or {}).get("first") or now or time.time(),
                                 "entities": sorted(e["entity_id"] for e in d.get("entities", []))}
                       for d in devices if d.get("id")}
    data["checked"] = now or time.time()
    from . import sys_routines
    sys_routines._save(cfg, FILE, data)
    return fresh


def tried(cfg: sys_config.Config, now: float | None = None) -> None:
    """A look that could not read Home Assistant counts as a look: the next is at the usual interval, not the next
    minute (C339: 247 warnings in one night, one a minute, while Home Assistant's machine was down)."""
    from . import sys_routines
    data = seen(cfg)
    data["checked"] = now or time.time()
    sys_routines._save(cfg, FILE, data)


def kind_of(d: dict) -> str:
    """The kind of a device, from its entities (the same as the 🏠 page's kinds: webui home.js kindOf)."""
    has = {e.get("domain") for e in d.get("entities", [])}
    if "camera" in has:
        return "cameras"
    if "light" in has:
        return "lights"
    if has & {"switch", "fan"}:
        return "plugs"
    if has and has <= {"sensor", "binary_sensor"}:
        return "sensors"
    return "other"


def describe(d: dict) -> str:
    lines = [f"DEVICE: {d.get('name', '')} — {d.get('manufacturer', '')} {d.get('model', '')}".strip()]
    for e in d.get("entities", [])[:60]:
        extra = ", ".join(x for x in (e.get("device_class", ""), e.get("unit", "")) if x)
        lines.append(f"- {e['entity_id']} ({e.get('name', '')}{'; ' + extra if extra else ''}): {e.get('state', '')}")
    return "\n".join(lines)


def agents_in(text: str, last: bool = False) -> list:
    """The JSON list of agents in a text (the first one, or the last complete one in a thought)."""
    dec, found = json.JSONDecoder(), []
    for m in re.finditer(r"\[\s*(?:\{|\])", text):
        try:
            v, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(v, list) and all(isinstance(x, dict) for x in v):
            found.append(v)
            if not last:
                break
    return found[-1] if found else []


def proposals(llm, ds: dict | list[dict], n: int = 3) -> list[dict]:
    """The agents for one device or several of a kind, each checked as any of Aurora's proposals; none that commands
    a device. Their «why» starts with the devices' names («A, B: …»), by which the 🏠 page finds them."""
    from . import sys_routine_advice
    ds = [ds] if isinstance(ds, dict) else ds
    # with thinking (C271: without it the model answered [] for lights and plugs, with it three good agents) — rare,
    # only for new devices; if the budget ends inside the thought, its last complete list is the answer
    out_ = llm.complete(SYS.format(n=n), "\n\n".join(describe(d) for d in ds[:12]), 8000, think=True)
    items = agents_in(str(getattr(out_, "answer", out_))) or agents_in(str(getattr(out_, "thought", "") or ""), last=True)
    out = []
    for a in items[:n] if isinstance(items, list) else []:
        if not isinstance(a, dict) or "call_service" in json.dumps(a):
            continue                                     # read only: a command is the owner's, at the moment
        change = {k: a[k] for k in ("goal", "title", "schedule", "notify", "icon") if k in a}
        change["plugins"] = ["homeassistant"]
        c = sys_routine_advice._checked({"action": "new", "title": a.get("title", ""), "change": change,
                                         "why": f"{', '.join(d.get('name', '') for d in ds)}: {a.get('why', '')}"}, {})
        if c:
            c["change"]["memory"] = True                     # it tells only what is new since its last report
            c["devices"] = [d["id"] for d in ds if d.get("id")]     # found by the 🏠 page by id: a new name keeps it
            out.append(c)
    return out


def welcome(cfg: sys_config.Config, llm, devices: list[dict]) -> dict:
    """The new devices and what was done for them: proposed (level 1) or created (level 2)."""
    from . import sys_autonomy, sys_routine_advice, sys_routines
    level = int(cfg["AURORA_HA_DEVICE_AGENTS"])
    changed = changes(seen(cfg).get("devices", {}), devices)
    fresh = new_devices(cfg, devices)
    report = {"new": [d.get("name", "") for d in fresh], "proposed": 0, "created": [], "renamed": changed["names"],
              "followed": follow(cfg, changed["entities"]) if changed["entities"] else []}
    kinds: dict[str, list[dict]] = {}
    for d in fresh:                                      # seven garden lights: agents for them together, not 21
        kinds.setdefault(kind_of(d), []).append(d)
    for group in kinds.values():
        props = proposals(llm, group)
        if level >= 2:
            for p in props:
                r = sys_routines.create(cfg, {**p["change"], "by": "aurora"})
                report["created"].append(r.get("title", ""))
                sys_autonomy.log(cfg, "devices", f"{', '.join(d.get('name', '') for d in group)}: "
                                                 f"agente «{r.get('title', '')}» creato")
        elif props:
            report["proposed"] += sys_routine_advice.remember(cfg, props, reviewed=False)
    return report


def message(report: dict) -> str:
    """The owner's notification, in Italian (empty when nothing new)."""
    said = ""
    if report.get("followed"):
        said = (f"🏠 Hai cambiato l'ID di qualche entità in Home Assistant: ho aggiornato {len(report['followed'])} "
                f"agenti che la usavano ({', '.join(report['followed'][:4])}). ")
    if not report["new"]:
        return said.strip()
    names = ", ".join(f"«{n}»" for n in report["new"])
    if report["created"]:
        return said + (f"🏠 Nuovo dispositivo in Home Assistant: {names}. Ho creato {len(report['created'])} agenti per "
                f"tenerlo d'occhio: {', '.join(report['created'])} (🤖 Agenti e routine).")
    if report["proposed"]:
        return said + (f"🏠 Nuovo dispositivo in Home Assistant: {names}. Ti propongo {report['proposed']} agenti su misura "
                "nella pagina 🤖 Agenti e routine, con «Applica».")
    return said + f"🏠 Nuovo dispositivo in Home Assistant: {names}. Lo vedo; per ora non serve un controllo periodico."


def watching(devices: list[dict], routines: list[dict], advice: list[dict]) -> list[dict]:
    """Each device with the agents that name one of its entities and Aurora's open proposals made for it."""
    out = []
    for d in devices:
        ids = {e["entity_id"] for e in d.get("entities", [])}
        mine = [{"id": r["id"], "title": r.get("title", ""), "enabled": r.get("enabled", True)} for r in routines
                if any(i in json.dumps(r, ensure_ascii=False) for i in ids)]
        props = [{"id": a["id"], "title": a.get("title", "")} for a in advice if a.get("action") == "new" and (
                 d.get("id") in (a.get("devices") or [])            # by id: a device renamed keeps its proposals
                 or d.get("name", "") in str(a.get("why", "")).split(": ", 1)[0].split(", "))]
        out.append({**d, "agents": mine, "proposals": props})
    return out
