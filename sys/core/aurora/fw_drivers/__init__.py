# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Firewall drivers (ROADMAP 108): the core speaks one interface, each device's dialect lives in a module of this
folder, chosen by AURORA_FIREWALL_API_KIND — the product's name only there and in the setting's value.

A driver is a module with:
  request(cfg, body) -> str               one authenticated call, the device's answer; FirewallAPIError when refused
  status(text, entity) -> (code, msg)     the result of one object in an answer ("200" = done)
  ok_codes(op) -> tuple                   the codes that mean done for "add_host" (an existing host included)
  has_group(text, name) -> bool          the answer to get_group names the group
  get_group(name) / add_group(name) / add_host(name, ip, desc, group) / ungroup_host(name, ip, group)
  remove_host(name)
  x(tag, value) / set_(entity, body, op) / remove(entity, name)
  host(name, ip, groups) / service(name, ports) / rule(...) / dnat(...) / group(name, desc) / release(name, ip)
                                          the body of one object of a plan
  get_rules() -> str / find_rule(text, name) -> str | None / harden(before, ips, log) -> str
                                          an owner's rule read, found and changed (IPS and log)
The second and third drivers (pfsense and opnsense, step 2) have the call, the answers and the blocking group; a request for a plan's objects
or an owner's rule is refused by it with the reason, never sent.
"""
from __future__ import annotations

import importlib

KINDS = ("sophos", "pfsense", "opnsense")
DEFAULT = "sophos"


def driver(cfg=None):
    """The driver of the setting (the default without a configuration); ValueError for a kind with none."""
    kind = str(cfg["AURORA_FIREWALL_API_KIND"]) if cfg is not None else DEFAULT
    if kind not in KINDS:
        raise ValueError(f"firewall API kind {kind!r}: one of {KINDS}")
    return importlib.import_module(f"{__name__}.{kind}")
