# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎄 Light scenes Aurora keeps herself (owner, 2026-10-12: «Aurora deve essere smart… o legge queste cose o le crea nel
suo sistema, non mi metto a fare configurazioni»).

The scenes and automations of a vendor's app (Smart Life's, for one) never reach Home Assistant, and its bulbs
show no effects there, only colour and white. So a scene is Aurora's own: some lights, some colours, how often they
change, for how long. Saved per user; while one runs, a thread asks Home Assistant for each light's next colour —
«chase» gives the lights different colours that move along, «together» the same colour at once. It stops when asked,
when its minutes end, or when Home Assistant cannot be reached three times in a row. A scene that was running when the
API stopped starts again at the next tick, if its time is not over.
"""
from __future__ import annotations

import re
import threading
import time

import httpx

from . import sys_context, sys_routines

FILE = "home_scenes.json"
MIN_EVERY_S, MAX_LIGHTS = 3, 12                 # a cloud bulb (Tuya) behind each call: not faster than this
# colour names → Home Assistant's hs_color [hue 0-360, saturation 0-100]; white is the bulb's own white (color_temp)
COLOURS = {
    "rosso": (0, 100), "red": (0, 100), "verde": (120, 100), "green": (120, 100), "blu": (240, 100), "blue": (240, 100),
    "oro": (42, 85), "gold": (42, 85), "giallo": (55, 100), "yellow": (55, 100), "arancione": (25, 100),
    "orange": (25, 100), "viola": (280, 90), "purple": (280, 90), "rosa": (330, 60), "pink": (330, 60),
    "ciano": (185, 100), "cyan": (185, 100), "azzurro": (200, 70), "magenta": (300, 100), "bianco": "white",
    "white": "white", "bianco caldo": "warm", "warm white": "warm",
}
ENTITY = re.compile(r"light\.[a-z0-9_]{1,120}")
SWITCH = re.compile(r"(switch|input_boolean|fan)\.[a-z0-9_]{1,120}")     # switched on with the scene, off with it
_running: dict[tuple[str, str], threading.Event] = {}     # (user, scene) → its stop
_lock = threading.Lock()


class SceneError(ValueError):
    pass


def load(cfg) -> dict:
    return sys_routines._load(cfg, FILE, {"scenes": {}, "running": {}})


def _save(cfg, data: dict) -> None:
    sys_routines._save(cfg, FILE, data)


FILLER = {"scenario", "scena", "scene", "lo", "la", "il", "di", "del", "della", "lights", "luci", "scene:"}


def key(name: str) -> str:
    """«lo scenario di Natale» and «Natale» are one scene."""
    return " ".join(w for w in str(name).lower().split() if w not in FILLER)


def colour(c) -> tuple | str:
    """A name («rosso», «gold»), [hue, saturation] or «#rrggbb»."""
    if isinstance(c, (list, tuple)) and len(c) == 2:
        return (max(0, min(360, float(c[0]))), max(0, min(100, float(c[1]))))
    s = str(c).strip().lower()
    if s in COLOURS:
        return COLOURS[s]
    if re.fullmatch(r"#[0-9a-f]{6}", s):
        import colorsys
        r, g, b = (int(s[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, _l, sat = colorsys.rgb_to_hls(r, g, b)
        return (round(h * 360), round(sat * 100))
    raise SceneError(f"colour not known: {c!r} (a name like rosso/verde/oro/bianco, [hue, saturation] or #rrggbb)")


def save(cfg, name: str, lights: list, colours: list, every_s: float = 5, mode: str = "chase",
         brightness: int = 80, minutes: float = 0, switches: list | None = None) -> dict:
    """Any user's scene: the lights they chose (their colours change) and plugs or switches (on with the scene)."""
    k = key(name)
    lights = [str(x).strip() for x in lights or []]
    switches = [str(x).strip() for x in switches or []]
    if not k:
        raise SceneError("a scene needs a name")
    if not lights and not switches or len(lights) + len(switches) > MAX_LIGHTS:
        raise SceneError(f"1 to {MAX_LIGHTS} devices")
    if not all(ENTITY.fullmatch(x) for x in lights) or not all(SWITCH.fullmatch(x) for x in switches):
        raise SceneError("lights as light.… entity ids; plugs and switches as switch.…, fan.…, input_boolean.…")
    cols = [colour(c) for c in colours or []]
    if lights and not cols:
        raise SceneError("at least one colour for the lights")
    scene = {"name": str(name).strip(), "lights": lights, "switches": switches,
             "colours": [list(c) if isinstance(c, tuple) else c for c in cols],
             "every_s": max(MIN_EVERY_S, min(3600, float(every_s or 5))), "mode": "together" if mode == "together" else "chase",
             "brightness": max(1, min(100, int(brightness or 80))), "minutes": max(0, float(minutes or 0)),
             "saved": time.time()}
    data = load(cfg)
    data["scenes"][k] = scene
    _save(cfg, data)
    return scene


def find(cfg, name: str) -> tuple[str, dict]:
    data, k = load(cfg), key(name)
    if k in data["scenes"]:
        return k, data["scenes"][k]
    near = [x for x in data["scenes"] if k and (k in x or x in k)]
    if len(near) == 1:
        return near[0], data["scenes"][near[0]]
    raise SceneError(f"no scene {name!r}; saved: {', '.join(data['scenes']) or 'none'}")


def step(scene: dict, n: int) -> list[tuple[str, dict]]:
    """The service data of each light at step n."""
    cols, out = scene["colours"], []
    for i, light in enumerate(scene["lights"]):
        c = cols[(n + (0 if scene["mode"] == "together" else i)) % len(cols)]
        data = {"brightness_pct": scene["brightness"]}
        if c == "white":
            data["color_temp_kelvin"] = 5000
        elif c == "warm":
            data["color_temp_kelvin"] = 2700
        else:
            data["hs_color"] = list(c)
        out.append((light, data))
    return out


def _ha(cfg, path: str, body: dict) -> None:
    url, token = str(cfg["AURORA_HA_URL"]).rstrip("/"), str(cfg["AURORA_HA_TOKEN"])
    r = httpx.post(f"{url}/api/services/{path}", headers={"Authorization": f"Bearer {token}"}, json=body, timeout=15)
    r.raise_for_status()


def _run(cfg, user: str, k: str, scene: dict, stop: threading.Event, until: float, log) -> None:
    n, errors = 0, 0
    try:
        for sw in scene.get("switches", []):
            try:
                _ha(cfg, f"{sw.split('.')[0]}/turn_on", {"entity_id": sw})
            except httpx.HTTPError as e:
                if log:
                    log.warning("scene %s: %s not reached: %s", k, sw, e)
        while scene["lights"] and not stop.is_set() and (not until or time.time() < until):
            for light, data in step(scene, n):
                try:
                    _ha(cfg, "light/turn_on", {"entity_id": light, **data})
                    errors = 0
                except httpx.HTTPError as e:
                    errors += 1
                    if log:
                        log.warning("scene %s: %s not reached: %s", k, light, e)
            if errors >= 3 * max(1, len(scene["lights"])):
                break
            n += 1
            stop.wait(scene["every_s"])
    finally:
        with _lock:
            if _running.get((user, k)) is stop:
                _running.pop((user, k), None)
                data = load(cfg)
                data["running"].pop(k, None)
                _save(cfg, data)


def start(cfg, name: str, user: str = "", minutes: float | None = None, log=None) -> dict:
    k, scene = find(cfg, name)
    stop_scene(cfg, k, user)
    mins = scene["minutes"] if minutes is None else max(0, float(minutes))
    until = time.time() + mins * 60 if mins else 0
    ev = threading.Event()
    with _lock:
        _running[(user, k)] = ev
        data = load(cfg)
        data["running"][k] = {"since": time.time(), "until": until}
        _save(cfg, data)
    sys_context.start(_run, cfg, user, k, scene, ev, until, log, name=f"scene-{k}"[:15])
    return {"scene": scene["name"], "lights": scene["lights"], "switches": scene.get("switches", []), "until": until}


def stop_scene(cfg, name: str, user: str = "", off: bool = False) -> bool:
    k = key(name)
    with _lock:
        ev = _running.pop((user, k), None)
        data = load(cfg)
        was = data["running"].pop(k, None)
        _save(cfg, data)
    if ev:
        ev.set()
    if off and k in load(cfg)["scenes"]:
        sc = load(cfg)["scenes"][k]
        if sc["lights"]:
            _ha(cfg, "light/turn_off", {"entity_id": sc["lights"]})
        for sw in sc.get("switches", []):
            _ha(cfg, f"{sw.split('.')[0]}/turn_off", {"entity_id": sw})
    return bool(ev or was)


def running(user: str = "") -> list[str]:
    return sorted(k for (u, k) in _running if u == user)


def resume(cfg, user: str = "", log=None) -> list[str]:
    """The scenes that were running when the API stopped, with time left: started again (the routines' tick)."""
    data, out = load(cfg), []
    for k, r in list(data["running"].items()):
        if (user, k) in _running or k not in data["scenes"]:
            continue
        left = (r.get("until") or 0) - time.time()
        if r.get("until") and left <= 0:
            data["running"].pop(k, None)
            _save(cfg, data)
            continue
        start(cfg, k, user, left / 60 if r.get("until") else 0, log)
        out.append(k)
    return out


# the agent's tool (agt_loop): shown only while the homeassistant plugin is on
TOOL = {"name": "home_scene", "description": "Aurora's own light scenes on the home's Home Assistant lights (a vendor "
        "app's scenes, e.g. Smart Life's, cannot be read). action=list: the saved ones and those running. action=save: "
        "make one — name, lights (light.… entity ids from homeassistant devices), colours (names: rosso, verde, oro, "
        "bianco, blu, viola, arancione, rosa, ciano, bianco caldo; or [hue, saturation]), every_s (seconds between "
        "changes, ≥3), mode chase (lights in different colours that move along) or together, brightness 1-100, "
        "minutes (0 = until stopped), switches (switch.… plugs switched on with the scene). When the owner asks for a scene that does not exist, make it with fitting "
        "colours (Christmas: rosso, verde, oro, bianco caldo) on the lights the name suggests (all the lights when "
        "unsure), save it, then start it. action=start / stop: name; stop with off=true also switches the lights off.",
        "input_schema": {"type": "object", "properties": {
            "action": {"enum": ["list", "save", "start", "stop"]}, "name": {"type": "string"},
            "lights": {"type": "array", "items": {"type": "string"}}, "colours": {"type": "array"},
            "switches": {"type": "array", "items": {"type": "string"}},
            "every_s": {"type": "number"}, "mode": {"enum": ["chase", "together"]},
            "brightness": {"type": "integer"}, "minutes": {"type": "number"}, "off": {"type": "boolean"}},
            "required": ["action"]}}


def tool(cfg, args: dict, may_command: bool, log=None) -> str:
    """The agent's call. Saving is Aurora's own note; starting and stopping act on the lights: `may_command` is the
    owner's AURORA_HA_COMMANDS for this run (asked in the chat, or level 2)."""
    user = sys_context.user() or ""
    action, name = str(args.get("action", "")), str(args.get("name", ""))
    try:
        if action == "list":
            data = load(cfg)
            on = set(running(user))
            return "\n".join(f"{s['name']}{' ▶ running' if k in on else ''}: {', '.join(s['lights'] + s.get('switches', []))}; colours "
                             f"{s['colours']}; every {s['every_s']} s, {s['mode']}" for k, s in data["scenes"].items()) \
                or "No scene saved yet."
        if action == "save":
            s = save(cfg, name, args.get("lights") or [], args.get("colours") or [], args.get("every_s", 5),
                     str(args.get("mode", "chase")), args.get("brightness", 80), args.get("minutes", 0),
                     args.get("switches") or [])
            return (f"SAVED scene «{s['name']}»: {len(s['lights'])} lights, {len(s['switches'])} plugs/switches, "
                    f"{len(s['colours'])} colours, every {s['every_s']} s.")
        if action in ("start", "stop") and not may_command:
            return ("REFUSED: a command to the home's lights that the owner did not ask for (AURORA_HA_COMMANDS: "
                    "🎚️ Autonomia → Comandi di casa). Say what you would do.")
        if action == "start":
            r = start(cfg, name, user, args.get("minutes"), log)
            return f"STARTED «{r['scene']}» on {', '.join(r['lights'] + r['switches'])}" + (
                f" until {time.strftime('%H:%M', time.localtime(r['until']))}." if r["until"] else ", until stopped.")
        if action == "stop":
            return "STOPPED." if stop_scene(cfg, name, user, bool(args.get("off"))) else f"«{name}» was not running."
    except SceneError as e:
        return f"ERROR: {e}"
    except httpx.HTTPError as e:
        return f"ERROR: Home Assistant: {e}"
    return "ERROR: action is list, save, start or stop"
