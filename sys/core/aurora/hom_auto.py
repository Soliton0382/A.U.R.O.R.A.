# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🪄 Aurora's own automations on every device of the home (owner, 2026-10-20: «su smartlife ho gli automatismi… creando
una sezione apposita di scene/automatismi che prenda in considerazione di gestire tutti i device in generale,
telecamere, luci, prese»).

A vendor app's automations never reach Home Assistant (measured on the owner's: the Tuya integration is there, with no
scene, script or automation entity — Smart Life gives Home Assistant only its «tap-to-run» scenes, and there were
none), so they are kept here, per user:
    {"id", "name", "enabled", "when": {"type": "manual" | "time" | "sunrise" | "sunset", "at": "HH:MM",
     "offset_min": ±minutes from the sun, "days": [0-6, Monday 0]}, "actions": [...]}
an action is {"entity_id", "service"} on a device (a light, a plug, a camera's switch, a button: the services the 🏠
page allows, hom_devices.ALLOWED), optionally {"data"} (a light's brightness_pct 1-100 and color_temp_kelvin
2000-6500: a vendor app's «white» with its warmth), or {"scene": name} (one of hom_scenes' light scenes, started;
with "stop": true, stopped — a bulb's own «scene» mode, which Home Assistant cannot set, becomes one of Aurora's). The routines' tick (every minute) runs an automation once a day at its time —
up to WINDOW_S late (an API restart, a tick deferred), never twice; «manual» ones only by ▶.
The sun's times come from Home Assistant's own sun.sun (the home's coordinates stay there).
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

import httpx

from . import hom_devices, hom_scenes, sns_clock, sys_routines

FILE = "home_automations.json"
WINDOW_S = 15 * 60                                  # a time missed by this much still runs, later never
TYPES = ("manual", "time", "sunrise", "sunset")
ENTITY = re.compile(r"[a-z_]{2,20}\.[a-z0-9_]{1,120}")
MAX_ACTIONS = 30


class AutoError(ValueError):
    pass


def load(cfg) -> dict:
    return sys_routines._load(cfg, FILE, {"automations": []})


def _save(cfg, data: dict) -> None:
    sys_routines._save(cfg, FILE, data)


def _when(w: dict) -> dict:
    t = str((w or {}).get("type", "manual"))
    if t not in TYPES:
        raise AutoError(f"when: one of {', '.join(TYPES)}")
    out = {"type": t, "days": sorted({int(d) for d in (w.get("days") or range(7)) if 0 <= int(d) <= 6}) or list(range(7))}
    if t == "time":
        at = str(w.get("at", ""))
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
            raise AutoError("at: HH:MM")
        out["at"] = at
    elif t in ("sunrise", "sunset"):
        out["offset_min"] = max(-240, min(240, int(w.get("offset_min") or 0)))
    return out


def _action(a: dict) -> dict:
    if a.get("scene"):
        return {"scene": str(a["scene"])[:80], **({"stop": True} if a.get("stop") else {})}
    eid, service = str(a.get("entity_id", "")), str(a.get("service", ""))
    domain = eid.split(".", 1)[0]
    if domain == "light" and service == "scene" and ENTITY.fullmatch(eid) and a.get("scene_name"):
        return {"entity_id": eid, "service": "scene", "scene_name": str(a["scene_name"])[:80]}   # a scene on this light
    if not ENTITY.fullmatch(eid) or service not in hom_devices.ALLOWED.get(domain, ()):
        raise AutoError(f"action not allowed: {domain}.{service}")
    out = {"entity_id": eid, "service": service}
    data = a.get("data") or {}
    if domain == "light" and service == "turn_on":
        light = {}
        if data.get("brightness_pct") is not None:
            light["brightness_pct"] = max(1, min(100, int(data["brightness_pct"])))
        if data.get("color_temp_kelvin") is not None:
            light["color_temp_kelvin"] = max(2000, min(6500, int(data["color_temp_kelvin"])))
        if light:
            out["data"] = light
    if domain == "number" and data.get("value") is not None:
        out["data"] = {"value": float(data["value"])}
    return out


def save(cfg, spec: dict) -> dict:
    """A new automation, or the one with spec["id"] changed."""
    name = str(spec.get("name", "")).strip()[:80]
    if not name:
        raise AutoError("name: required")
    actions = [_action(a) for a in (spec.get("actions") or [])][:MAX_ACTIONS]
    if not actions:
        raise AutoError("actions: at least one")
    data = load(cfg)
    old = next((x for x in data["automations"] if x["id"] == spec.get("id")), None)
    a = {"id": old["id"] if old else secrets.token_hex(5), "name": name, "enabled": bool(spec.get("enabled", True)),
         "when": _when(spec.get("when") or {}), "actions": actions,
         "last": (old or {}).get("last"), "last_ok": (old or {}).get("last_ok"), "last_text": (old or {}).get("last_text", "")}
    data["automations"] = [a if x is old else x for x in data["automations"]] if old else data["automations"] + [a]
    _save(cfg, data)
    return a


def delete(cfg, aid: str) -> bool:
    data = load(cfg)
    n = len(data["automations"])
    data["automations"] = [x for x in data["automations"] if x["id"] != aid]
    _save(cfg, data)
    return len(data["automations"]) < n


def _sun(cfg) -> dict:
    """{"sunrise", "sunset"}: today's, from Home Assistant's sun.sun (its next ones, a day back when already past)."""
    url, token = str(cfg["AURORA_HA_URL"]).rstrip("/"), str(cfg["AURORA_HA_TOKEN"])
    r = httpx.get(f"{url}/api/states/sun.sun", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    attrs, today, out = r.json().get("attributes", {}), sns_clock.now(cfg), {}
    for k, attr in (("sunrise", "next_rising"), ("sunset", "next_setting")):
        nxt = datetime.fromisoformat(attrs[attr]).astimezone(today.tzinfo)
        out[k] = nxt if nxt.date() == today.date() else nxt - timedelta(days=(nxt.date() - today.date()).days)
    return out


def at_today(cfg, a: dict, sun: dict | None = None) -> datetime | None:
    """When the automation runs today, or None (manual, or not one of its days)."""
    w, today = a["when"], sns_clock.now(cfg)
    if w["type"] == "manual" or today.weekday() not in w.get("days", range(7)):
        return None
    if w["type"] == "time":
        h, m = map(int, w["at"].split(":"))
        return today.replace(hour=h, minute=m, second=0, microsecond=0)
    sun = sun or _sun(cfg)
    return sun[w["type"]] + timedelta(minutes=w.get("offset_min", 0))


def run(cfg, a: dict, user: str = "", log=None, now: datetime | None = None) -> dict:
    """Every action in order; one that fails does not stop the others. The result kept with the automation. The
    lights given one scene start it together, at the first of them; a light switched off stops a scene it was in."""
    done, failed, grouped = [], [], {}
    for act in a["actions"]:
        if act.get("service") == "scene":
            grouped.setdefault(act["scene_name"], []).append(act["entity_id"])
    for act in a["actions"]:
        try:
            if act.get("service") == "scene":
                lights = grouped.pop(act["scene_name"], None)
                if lights:                              # the first light of this scene: all of them at once
                    hom_scenes.start(cfg, act["scene_name"], user, log=log, lights=lights)
                    done.append(f"{act['scene_name']} on {', '.join(lights)}")
                continue
            if act.get("service") == "turn_off" and act.get("entity_id", "").startswith("light."):
                hom_scenes.stop_on(cfg, [act["entity_id"]], user)
            if act.get("scene") and act.get("stop"):
                hom_scenes.stop_scene(cfg, act["scene"], user)
            elif act.get("scene"):
                hom_scenes.start(cfg, act["scene"], user, log=log)
            else:
                domain = act["entity_id"].split(".", 1)[0]
                hom_scenes._ha(cfg, f"{domain}/{act['service']}", {"entity_id": act["entity_id"], **(act.get("data") or {})})
            done.append(f"{act['scene']}{' stop' if act.get('stop') else ''}" if act.get("scene") else f"{act['entity_id']} {act['service']}")
        except (httpx.HTTPError, hom_scenes.SceneError, OSError) as e:
            failed.append(f"{act.get('scene') or act['entity_id']}: {type(e).__name__}")
    data = load(cfg)
    for x in data["automations"]:
        if x["id"] == a["id"]:
            x.update(last=(now or sns_clock.now(cfg)).timestamp(), last_ok=not failed,
                     last_text=(f"{len(done)} azioni fatte" + (f"; non riuscite: {', '.join(failed)}" if failed else "")))
    _save(cfg, data)
    if log:
        log.info("automation %s ran: %d done, %d failed", a["name"], len(done), len(failed))
    return {"done": done, "failed": failed}


def due(cfg, now: datetime | None = None) -> list[dict]:
    """The automations whose time today has come (within WINDOW_S) and that have not run since it."""
    now = now or sns_clock.now(cfg)
    autos = [a for a in load(cfg)["automations"] if a.get("enabled") and a["when"]["type"] != "manual"]
    sun = None
    if any(a["when"]["type"] in ("sunrise", "sunset") for a in autos):
        try:
            sun = _sun(cfg)
        except (httpx.HTTPError, KeyError, ValueError):     # Home Assistant away a moment: the sun's wait, the clock's go
            autos = [a for a in autos if a["when"]["type"] == "time"]
    out = []
    for a in autos:
        at = at_today(cfg, a, sun)
        if at and 0 <= (now - at).total_seconds() <= WINDOW_S and (a.get("last") or 0) < at.timestamp():
            out.append(a)
    return out


def tick(cfg, user: str = "", log=None) -> list[str]:
    """The routines' tick: what is due, run."""
    ran = []
    for a in due(cfg):
        run(cfg, a, user, log)
        ran.append(a["name"])
    return ran


# the agent's tool (agt_loop): shown only while the homeassistant plugin is on — the way a vendor app's automations
# come in: the owner describes them, or sends the app's screenshots, and Aurora writes them here
TOOL = {"name": "home_automation", "description": "Aurora's own automations on the home's Home Assistant devices "
        "(lights, plugs, a camera's switches, buttons; a vendor app's automations, e.g. Smart Life's, cannot be read: "
        "the owner describes them or sends screenshots, and you write them here). action=list: the saved ones. "
        "action=save: name, when {type: time (at HH:MM) | sunset | sunrise (offset_min, minutes before < 0 or after > 0) "
        "| manual, days [0-6, Monday 0; all when omitted]}, actions [{entity_id (from homeassistant devices), service "
        "turn_on | turn_off | toggle | press, data {brightness_pct, color_temp_kelvin} for a light; or service scene "
        "with scene_name: that home_scene on this light only} or {scene: a "
        "home_scene's name, stop: true to stop it}]; a bulb's own «scene» mode cannot be set: use a home_scene; "
        "id to change one. action=run: id, now. action=delete: id.",
        "input_schema": {"type": "object", "properties": {
            "action": {"enum": ["list", "save", "run", "delete"]}, "id": {"type": "string"}, "name": {"type": "string"},
            "when": {"type": "object"}, "actions": {"type": "array", "items": {"type": "object"}},
            "enabled": {"type": "boolean"}}, "required": ["action"]}}


def tool(cfg, args: dict, may_command: bool, log=None) -> str:
    """The agent's call. Saving is Aurora's own note; running acts on the devices: `may_command` is the owner's
    AURORA_HA_COMMANDS for this run, as for the scenes."""
    from . import sys_context
    action = str(args.get("action", ""))
    try:
        if action == "list":
            return "\n".join(f"{a['id']} «{a['name']}» {'on' if a['enabled'] else 'off'}: {a['when']}; "
                             f"{len(a['actions'])} actions {a['actions']}" for a in load(cfg)["automations"]) \
                or "No automation saved yet."
        if action == "save":
            a = save(cfg, {k: args[k] for k in ("id", "name", "when", "actions", "enabled") if k in args})
            return f"SAVED automation «{a['name']}» ({a['id']}): {a['when']}, {len(a['actions'])} actions."
        found = next((a for a in load(cfg)["automations"] if a["id"] == str(args.get("id", ""))), None)
        if found is None:
            return "ERROR: unknown id (action=list gives them)"
        if action == "delete":
            delete(cfg, found["id"])
            return f"DELETED «{found['name']}»."
        if action == "run" and not may_command:
            return ("REFUSED: a command to the home's devices that the owner did not ask for (AURORA_HA_COMMANDS: "
                    "🎚️ Autonomia → Comandi di casa). Say what you would do.")
        if action == "run":
            r = run(cfg, found, sys_context.user() or "", log)
            return f"RAN «{found['name']}»: done {r['done']}" + (f"; failed {r['failed']}" if r["failed"] else "")
    except AutoError as e:
        return f"ERROR: {e}"
    return "ERROR: action is list, save, run or delete"
