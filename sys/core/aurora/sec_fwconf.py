# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The firewall's configuration, read through its API (<Get>) and turned into plain dicts: what the audit judges
(sec_audit) and what the writer starts from (sec_fwwrite). Read only.

An element becomes a dict of its children: a leaf is its text, a repeated tag a list, a container a dict; e.g. a
FirewallRule → {"Name": …, "Status": "Enable", "NetworkPolicy": {"Action": "Accept", "SourceZones": {"Zone": ["WAN"]}…}}.
The firewall's answer is XML from the owner's own appliance; a DOCTYPE or an ENTITY is refused before parsing all
the same (no entity expansion: xml.etree would expand an internal one).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import sec_fwapi, sys_config

ENTITIES = ("FirewallRule", "NATRule", "Services", "ServiceGroup", "Zone", "IPHost", "IPHostGroup", "AdminSettings",
            "LocalServiceACL", "IPSPolicy", "ATP", "SyslogServers", "Interface")


class ConfigError(Exception):
    pass


def _value(el: ET.Element):
    kids = list(el)
    if not kids:
        return (el.text or "").strip()
    out: dict = {}
    for k in kids:
        v = _value(k)
        if k.tag in out:
            out[k.tag] = out[k.tag] if isinstance(out[k.tag], list) else [out[k.tag]]
            out[k.tag].append(v)
        else:
            out[k.tag] = v
    return out


def parse(text: str, entity: str) -> list[dict]:
    """Every <entity> of an API answer, as dicts (the answer's <Login> and <Status> are not entities)."""
    if re.search(r"<!(DOCTYPE|ENTITY)", text, re.I):
        raise ConfigError("the firewall's answer holds a DOCTYPE or an ENTITY: not parsed")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ConfigError(f"the firewall's answer is not XML: {e}") from None
    items = [_value(el) for el in root.iter(entity) if isinstance(_value(el), dict)]
    refused = [i for i in items if set(i) == {"Status"}]
    if refused and len(refused) == len(items):        # «529 Input request module is Invalid»: not an item (C193)
        raise ConfigError(f"{entity}: {refused[0]['Status']}")
    return [i for i in items if set(i) != {"Status"}]


def listed(value, key: str | None = None) -> list[str]:
    """A field that may be absent, one value or many: always a list of strings (`key` the inner tag, e.g. "Zone")."""
    if value in (None, ""):
        return []
    if key and isinstance(value, dict):
        value = value.get(key)
    if value in (None, ""):
        return []
    return [str(v) for v in (value if isinstance(value, list) else [value]) if not isinstance(v, dict)]


def get(cfg: sys_config.Config, entity: str) -> list[dict]:
    return parse(sec_fwapi.request(cfg, f"<Get><{entity}/></Get>"), entity)


def read(cfg: sys_config.Config, entities: tuple[str, ...] = ENTITIES) -> dict[str, list[dict]]:
    """The configuration the audit needs: {entity: [items]}, one request per entity (one request with every entity
    was followed by four minutes of a silent firewall: C192). An entity refused is an empty list with its error under
    "_errors" (an older firmware may not know it); once the firewall stops answering, the rest is not asked — a
    firewall in trouble is not hammered."""
    out: dict = {"_errors": {}}
    silent = ""
    for e in entities:
        if silent:
            out[e], out["_errors"][e] = [], silent
            continue
        try:
            out[e] = get(cfg, e)
        except (sec_fwapi.FirewallAPIError, ConfigError) as err:
            out[e] = []
            out["_errors"][e] = str(err)[:200]
            if "does not answer" in str(err):
                silent = str(err)[:200]
    return out


def ports(conf: dict, service: str) -> list[str]:
    """The destination ports of a service or service group by name ("TNas_Plex" → ["TCP 32400", "UDP 32400"])."""
    for s in conf.get("Services", []):
        if s.get("Name") == service:
            details = (s.get("ServiceDetails") or {}).get("ServiceDetail") or []
            details = details if isinstance(details, list) else [details]
            return [f"{d.get('Protocol', '')} {d.get('DestinationPort', '')}".strip() for d in details if isinstance(d, dict)]
    for g in conf.get("ServiceGroup", []):
        if g.get("Name") == service:
            return [p for s in listed(g.get("ServiceList"), "Service") for p in ports(conf, s)]
    return []


def rule_view(rule: dict) -> dict:
    """The fields of a firewall rule that matter, flat: name, enabled, action, zones, networks, services, IPS, log."""
    pol = rule.get("NetworkPolicy") or rule.get("UserPolicy") or {}
    return {"name": rule.get("Name", ""), "enabled": rule.get("Status") == "Enable", "action": pol.get("Action", ""),
            "src_zones": listed(pol.get("SourceZones"), "Zone"), "dst_zones": listed(pol.get("DestinationZones"), "Zone"),
            "src_nets": listed(pol.get("SourceNetworks"), "Network"), "dst_nets": listed(pol.get("DestinationNetworks"), "Network"),
            "services": listed(pol.get("Services"), "Service"), "ips": pol.get("IntrusionPrevention") or "None",
            "log": pol.get("LogTraffic") == "Enable", "web_filter": pol.get("WebFilter") or "None",
            "description": rule.get("Description") or ""}
