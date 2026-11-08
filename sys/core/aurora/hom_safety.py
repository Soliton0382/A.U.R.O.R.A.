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


def lowers(domain: str, service: str) -> bool:
    return str(service) in LOWERS.get(str(domain), set())


def action_lowers(act: dict) -> bool:
    """An automation's action ({entity_id, service}) that lowers the house's security."""
    entity = str(act.get("entity_id", ""))
    return "." in entity and lowers(entity.split(".", 1)[0], str(act.get("service", "")))


def call_lowers(manifest: dict, tool: str, args: dict) -> bool:
    """A plugin's call that lowers it: an owner-only tool, or a service of the kinds above (call_service's domain and
    service, or an entity's domain with a service)."""
    if tool in (manifest.get("owner_only") or []):
        return True
    service = str(args.get("service", ""))
    domain = str(args.get("domain", "") or str(args.get("entity_id", "")).split(".", 1)[0])
    return bool(service) and lowers(domain, service)
