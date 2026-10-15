# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""pfSense read (ROADMAP N8): its configuration in the neutral form for the audit (sec_fwmodel) and its network for
the map (sec_netmap), through the REST API package's v2 endpoints. Read only. Measured on the aurora-lab pfSense
(CE 2.9.0, package 2.10.2).

The rules are evaluated floating first (a «quick» one stops there), then each interface's in order: kept in that order.
A rule is the interface it listens on: its zone is the interface's name (WAN, LAN). The firewall has no per-rule
intrusion prevention: that is Suricata's or Snort's (a package), read from the installed packages. Dynamic leases and
the ARP table are in this API: the map has them too («seen»)."""
from __future__ import annotations

import ipaddress

from .. import sec_fwmodel as M

IDS = ("pfSense-pkg-suricata", "pfSense-pkg-snort")


def _get(api, path: str, errors: dict, part: str):
    from ..sec_fwapi import FirewallAPIError
    try:
        return api("GET", path)
    except FirewallAPIError as e:
        errors.setdefault(part, str(e)[:200])
        return None


def _zones(api, errors: dict) -> dict:
    """interface id (wan, lan, opt1) → its name in capitals (the zone)."""
    return {str(i.get("id")): str(i.get("descr") or i.get("id")).upper() for i in _get(api, "/interfaces", errors, "interfaces") or []}


def _net(x) -> list[str]:
    s = str(x or "").strip()
    return [] if s in ("", "any") else [s]


def read_model(cfg, group: str) -> dict:
    from .pfsense import _API, alias_name
    api = _API(cfg)
    m = M.empty("pfsense")
    err = m["_errors"]
    zone = _zones(api, err)
    own = {str(i.get("ipaddr")) for i in _get(api, "/status/interfaces", err, "interfaces") or [] if i.get("ipaddr")}
    rules = _get(api, "/firewall/rules", err, "rules") or []
    rules = [r for r in rules if r.get("floating")] + [r for r in rules if not r.get("floating")]
    by_assoc = {}
    for r in rules:
        dest = str(r.get("destination") or "")
        to_self = M.is_self(dest) or dest in own              # an interface's own address is the firewall too
        m["rules"].append(M.rule(
            str(r.get("descr") or f"#{r.get('id')}"), not r.get("disabled"), str(r.get("type") or ""),
            src_zones=[zone.get(str(i), str(i).upper()) for i in r.get("interface") or []],
            src_nets=_net(r.get("source")), dst_nets=[] if to_self else _net(dest),
            ports=M.ports_of(r.get("protocol"), r.get("destination_port")), log=bool(r.get("log")),
            to_self=to_self, floating=bool(r.get("floating"))))
        if r.get("associated_rule_id"):
            by_assoc[r["associated_rule_id"]] = m["rules"][-1]["name"]
    for n in _get(api, "/firewall/nat/port_forwards", err, "nat") or []:
        m["nat"].append({"name": str(n.get("descr") or f"NAT {n.get('destination_port')}"), "enabled": not n.get("disabled"),
                         "services": [], "ports": M.ports_of(n.get("protocol"), n.get("destination_port")),
                         "target": _net(n.get("target")), "sources": _net(n.get("source")),
                         "outside": str(n.get("interface")) == "wan", "rule": by_assoc.get(n.get("associated_rule_id"))})
    gui = _get(api, "/system/webgui/settings", err, "webgui") or {}
    M.wan_access(m, str(gui.get("port") or ("443" if gui.get("protocol", "https") == "https" else "80")))
    pkgs = _get(api, "/system/packages", err, "threat")
    if pkgs is not None:
        have = [p.get("name") for p in pkgs if p.get("name") in IDS]
        # installed is not running in IPS mode: not read here, so not judged (state None)
        m["threat"] = {"what": "Suricata" if "pfSense-pkg-suricata" in have else ("Snort" if have else "Suricata o Snort"),
                       "state": None if have else "off"}
    logs = _get(api, "/status/logs/settings", err, "syslog")
    if logs is not None and logs.get("enableremotelogging"):
        threats_off = [] if (logs.get("logall") or logs.get("filter")) else ["filter (le regole del firewall)"]
        for k in ("remoteserver", "remoteserver2", "remoteserver3"):
            if logs.get(k):
                host = str(logs[k]).rsplit(":", 1)[0] if str(logs[k]).count(":") == 1 else str(logs[k])
                m["syslog"].append({"address": host, "name": logs[k], "threats_off": threats_off})
    m["block_object"] = alias_name(group)
    return m


def read_network(cfg) -> dict:
    """The map (sec_netmap's form): hosts from the aliases, interfaces with their addresses, DHCP with its reservations,
    the static routes; and what the firewall sees now (leases and ARP) as «seen»."""
    import time
    from ..sec_fwapi import FirewallAPIError
    from .pfsense import _API
    api = _API(cfg)
    err: dict = {}
    hosts, groups = [], []
    for a in _get(api, "/firewall/aliases", err, "aliases") or []:
        if a.get("type") not in ("host", "network"):
            continue
        names = []
        blocked = str(a.get("descr", "")).startswith("Aurora:")
        details = a.get("detail") or []
        for i, addr in enumerate(a.get("address") or []):
            try:
                one = "/" not in addr and ipaddress.ip_address(addr)
            except ValueError:
                one = False                                  # a name (FQDN) or a range
            name = f"aurora-block-{addr}" if blocked else (str(details[i]) if i < len(details) and details[i] else f"{a['name']}-{i + 1}")
            hosts.append({"name": name, "type": "IP" if one else "Network", "address": addr, "groups": [a["name"]]})
            names.append(name)
        groups.append({"name": a["name"], "hosts": names})
    zone = {}
    interfaces = []
    for i in _get(api, "/status/interfaces", err, "interfaces") or []:
        zone[str(i.get("name"))] = str(i.get("descr") or i.get("name")).upper()
        interfaces.append({"id": str(i.get("name")), "name": str(i.get("descr") or i.get("name")), "hardware": str(i.get("hwif") or ""),
                           "ip": str(i.get("ipaddr") or ""), "netmask": str(i.get("subnet") or ""),
                           "zone": zone[str(i.get("name"))], "status": str(i.get("status") or "")})
    dhcp = []
    for d in _get(api, "/services/dhcp_servers", err, "dhcp") or []:
        dhcp.append({"name": f"DHCP {zone.get(str(d.get('interface')), d.get('interface'))}",
                     "interface": zone.get(str(d.get("interface")), str(d.get("interface"))), "on": bool(d.get("enable")),
                     "range": [f"{d.get('range_from')}-{d.get('range_to')}"] if d.get("range_from") else [],
                     "static": [{"host": str(s.get("hostname") or s.get("descr") or ""), "mac": str(s.get("mac") or ""),
                                 "ip": str(s.get("ipaddr") or "")} for s in d.get("staticmap") or [] if s.get("ipaddr")]})
    routes = [{"to": str(r.get("network")), "via": str(r.get("gateway") or ""), "interface": ""}
              for r in _get(api, "/routing/static_routes", err, "routes") or [] if not r.get("disabled")]
    seen = {}
    for x in _get(api, "/diagnostics/arp_table", err, "arp") or []:
        seen[x.get("ip_address")] = {"ip": x.get("ip_address"), "mac": x.get("mac_address") or "",
                                     "host": "" if x.get("hostname") in (None, "?") else x["hostname"],
                                     "interface": str(x.get("interface") or "")}
    for x in _get(api, "/status/dhcp_server/leases", err, "leases") or []:
        if x.get("ip"):
            seen.setdefault(x["ip"], {"ip": x["ip"], "mac": x.get("mac") or "", "interface": str(x.get("if") or "")})["host"] = \
                str(x.get("hostname") or "")
    if not interfaces and err:
        raise FirewallAPIError("; ".join(f"{k}: {v}" for k, v in err.items()))
    return {"at": time.time(), "hosts": hosts, "groups": groups, "interfaces": interfaces, "zones": sorted(set(zone.values())),
            "dhcp": dhcp, "routes": routes, "seen": sorted(seen.values(), key=lambda s: str(s["ip"])), "errors": err}
