# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "homeassistant": the owner's home automation (REST API; HTTPS recommended).

Every device Home Assistant knows is a set of entities and services, whatever its brand: the tools here are the same
for all of them — what devices there are (devices), their state (states), what they did (history), what a camera
sees (camera_look, described by Aurora's own vision, nothing leaves the machine) and a command (call_service: done when
the owner asks for it, waiting for the owner when a run decides it — AURORA_HA_COMMANDS). A new device gets its agents from Aurora (hom_devices), not new code.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

URL = os.environ.get("AURORA_HA_URL", "").rstrip("/")
TOKEN = os.environ.get("AURORA_HA_TOKEN", "")
server = MCPServer("homeassistant", version="1.2")


# one line per entity of a real device (Home Assistant's own services — the sun, the backup, the forecast — left out)
DEVICES = ("{%- for s in states -%}{%- set d = device_id(s.entity_id) -%}"
           "{%- if d and device_attr(d, 'entry_type') != 'service' -%}"
           "{{ s.entity_id }}\t{{ d }}\t{{ device_attr(d, 'name_by_user') or device_attr(d, 'name') or '' }}\t"
           "{{ device_attr(d, 'manufacturer') or '' }}\t{{ device_attr(d, 'model') or '' }}\t"
           "{{ s.attributes.device_class or '' }}\t{{ s.attributes.unit_of_measurement or '' }}\t"
           "{{ s.attributes.friendly_name or '' }}\t{{ s.state }}\t{{ s.attributes.brightness or '' }}\n"
           "{% endif -%}{%- endfor -%}")


def _call(method: str, path: str, **kw) -> httpx.Response:
    if not URL or not TOKEN:
        raise ToolError("AURORA_HA_URL and AURORA_HA_TOKEN are needed")
    try:
        r = httpx.request(method, f"{URL}/api{path}", headers={"Authorization": f"Bearer {TOKEN}"},
                          timeout=httpx.Timeout(30, connect=5), **kw)
    except httpx.TransportError as e:
        # C352: the server off (a NAS that sleeps at night) said as such — before, «Error executing tool» and nothing
        # more, and a night routine tried four times and wrote a report of failures about the devices
        raise ToolError(f"UNREACHABLE: Home Assistant does not answer ({type(e).__name__}): the server is off or out of "
                        "the network. This says nothing about the devices: do not retry, report only that it was "
                        "unreachable.") from None
    if r.status_code >= 400:
        raise ToolError(f"Home Assistant {r.status_code}: {r.text[:200]}")
    return r


def _api(method: str, path: str, **kw):
    return _call(method, path, **kw).json()


def grouped(text: str) -> list[dict]:
    """The template's lines → one record a device, with its entities."""
    out: dict[str, dict] = {}
    for line in text.splitlines():
        f = line.split("\t")
        if len(f) < 9 or not f[0].strip():
            continue
        eid, did, name, maker, model, dclass, unit, friendly, state = (x.strip() for x in f[:9])
        d = out.setdefault(did, {"id": did, "name": name, "manufacturer": maker, "model": model, "entities": []})
        e = {"entity_id": eid, "domain": eid.split(".", 1)[0], "device_class": dclass, "unit": unit, "name": friendly,
             "state": state}
        if len(f) > 9 and f[9].strip().isdigit():          # a light's brightness, 0-255
            e["brightness"] = int(f[9].strip())
        d["entities"].append(e)
    return list(out.values())


@server.tool()
def devices() -> str:
    """The devices connected to Home Assistant (name, maker, model) with their entities, as JSON."""
    return json.dumps(grouped(_call("POST", "/template", json={"template": DEVICES}).text), ensure_ascii=False)


@server.tool()
def history(entity_id: str, hours: int = 24) -> str:
    """What an entity did in the last hours (each change of state with its time)."""
    hours = max(1, min(int(hours), 24 * 14))
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = _api("GET", f"/history/period/{since}", params={"filter_entity_id": entity_id, "minimal_response": "",
                                                            "no_attributes": ""})
    changes = rows[0] if rows else []
    if not changes:
        return f"{entity_id}: no change in {hours} h"
    return "\n".join(f"{c.get('last_changed', '')[:19]} {c.get('state')}" for c in changes[-200:])


@server.tool()
def camera_look(entity_id: str, instruction: str = "Descrivi in italiano cosa vedi, in modo preciso e breve.") -> str:
    """One picture from a camera of Home Assistant, described by Aurora's own vision (local: nothing leaves)."""
    if not entity_id.startswith("camera."):
        raise ToolError("a camera entity is needed (camera.…): see devices")
    jpeg = _call("GET", f"/camera_proxy/{entity_id}").content
    from aurora import sys_config
    from aurora.mdl_llm import LLM
    return LLM(sys_config.get()).see(jpeg, instruction)


def words(filter: str) -> list[str]:
    """The filter's words: one, or several separated by commas or spaces — a list written as text too (C275: an agent
    asked «entity_id in [a, b, c]» and got «no entity»)."""
    return [w for w in re.split(r"[\s,;\[\]()'\"]+", filter.lower()) if w and w not in ("in", "entity_id", "or", "and")]


@server.tool()
def states(filter: str = "", limit: int = 60) -> str:
    """Devices and sensors with their state; `filter`: one word or several separated by commas — the entities whose id
    or name contains any of them."""
    rows, want = [], words(filter)
    for s in _api("GET", "/states"):
        name = s.get("attributes", {}).get("friendly_name", "")
        if want and not any(w in s["entity_id"].lower() or w in name.lower() for w in want):
            continue
        unit = s.get("attributes", {}).get("unit_of_measurement", "")
        rows.append(f"{s['entity_id']} ({name}): {s['state']} {unit}".strip())
    return "\n".join(rows[:max(1, min(limit, 500))]) or "no entity"


@server.tool()
def call_service(domain: str, service: str, entity_id: str, data: dict | None = None) -> str:
    """Run a service: light.turn_on on light.kitchen (data e.g. {"brightness_pct": 60, "hs_color": [0, 100]}),
    switch.turn_off, scene.turn_on on scene.x, script.turn_on on script.x. Scenes and scripts belong to no device: find
    them with states(filter="scene") or states(filter="script"). Done at once when the owner asked for it in the chat;
    decided by an agent or a routine, it waits for the owner (AURORA_HA_COMMANDS)."""
    out = _api("POST", f"/services/{domain}/{service}", json={"entity_id": entity_id, **(data or {})})
    return f"{domain}.{service} on {entity_id}: {len(out)} states changed"


if __name__ == "__main__":
    server.run("stdio")
