# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Which way a command to the house goes (9 Nov, C536).

An action that RAISES the house's security (arming the alarm, locking, closing the covers) follows the owner's usual
rule for commands (AURORA_HA_COMMANDS); one that LOWERS it (disarming, unlocking, opening a door, a gate or the covers)
always waits for the owner's own yes — in a chat too, whatever words the run read — and an automation that holds one
runs only once the owner turned it on himself (hom_auto). A plugin's owner-only tools (an alarm's disarm) lower it.
"""
from __future__ import annotations

LOWERS = {"lock": {"unlock", "open"},
          "alarm_control_panel": {"alarm_disarm"},
          "cover": {"open_cover", "toggle", "set_cover_position", "open_cover_tilt", "set_cover_tilt_position",
                    "toggle_cover_tilt"}}
RAISES = {"lock": {"lock"},
          "alarm_control_panel": {"alarm_arm_away", "alarm_arm_home", "alarm_arm_night", "alarm_arm_vacation",
                                  "alarm_arm_custom_bypass"},
          "cover": {"close_cover", "close_cover_tilt", "stop_cover"}}


# C590: the services every entity answers (homeassistant.toggle on cover.garage opens it; so does the generic
# turn_on): on an entity of these kinds they lower it too — a lock and an alarm with any of them (what each one maps
# to is not ours to guess)
GENERIC = {"turn_on", "turn_off", "toggle"}
GENERIC_LOWERS = {"cover": {"turn_on", "toggle"}, "lock": GENERIC, "alarm_control_panel": GENERIC}
WIDE = ("area_id", "device_id", "label_id", "floor_id")     # targets that are not entities: what they reach is unknown


def lowers(domain: str, service: str) -> bool:
    domain, service = str(domain), str(service).rsplit(".", 1)[-1]
    return service in LOWERS.get(domain, set()) or service in GENERIC_LOWERS.get(domain, set())


def action_lowers(act: dict) -> bool:
    """An automation's action ({entity_id, service}) that lowers the house's security."""
    entity = str(act.get("entity_id", ""))
    return "." in entity and lowers(entity.split(".", 1)[0], str(act.get("service", "")))


def _targets(args: dict) -> tuple[list[str], bool]:
    """Every entity a call names — entity_id as text (one, or several with commas) or a list, at the top, in `data`
    and in a `target` — and whether it also aims at something that is not an entity (an area, a device, «all»)."""
    found, wide = [], False
    for box in (args, args.get("data"), args.get("target"), (args.get("data") or {}).get("target")
                if isinstance(args.get("data"), dict) else None):
        if not isinstance(box, dict):
            continue
        wide = wide or any(box.get(k) for k in WIDE)
        e = box.get("entity_id")
        for one in (e if isinstance(e, (list, tuple)) else [e]):
            found += [x.strip().lower() for x in str(one or "").split(",") if x.strip()]
    return found, wide or any(e == "all" or e.startswith("group.") for e in found)


def call_lowers(manifest: dict, tool: str, args: dict) -> bool:
    """A plugin's call that lowers it: an owner-only tool, or a service of the kinds above (call_service's domain and
    service, or an entity's domain with a service)."""
    if tool in (manifest.get("owner_only") or []):
        return True
    service = str(args.get("service", "")).strip().lower()
    if not service:
        return False
    domain = str(args.get("domain", "")).strip().lower()
    if "." in service and not domain:                 # «cover.open_cover» written whole
        domain = service.split(".", 1)[0]
    service = service.rsplit(".", 1)[-1]
    entities, wide = _targets(args)
    # C590: each entity's own domain, not only the one the call was given («homeassistant», toggle, cover.garage)
    if any(lowers(d, service) for d in {domain, *(e.split(".", 1)[0] for e in entities if "." in e)} if d):
        return True
    # a generic service on what cannot be told from here (an area, a group, no entity at all): it may open a door
    return domain in ("homeassistant", "group") and service in GENERIC and (wide or not entities)
