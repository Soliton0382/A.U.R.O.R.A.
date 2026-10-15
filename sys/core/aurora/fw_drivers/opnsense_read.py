# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""OPNsense read (ROADMAP N8): its configuration in the neutral form for the audit (sec_fwmodel) and its network for
the map (sec_netmap), through its own API. Read only. Measured on the aurora-lab OPNsense 26.7.

The filter's search gives every rule in the order they are evaluated (sort_order), the firewall's own automatic ones
too (marked system: the owner did not write them); a rule's zone is its interface's name (WAN, LAN). Intrusion
prevention is Suricata (Services → Intrusion Detection): on in IPS mode (netmap, divert), only detecting (pcap), or
off. The login lockout is the firewall's «sshlockout» table: its rules there, the lockout is on. DHCP is dnsmasq's (the
default since 25.x) or Kea's reservations."""
from __future__ import annotations

import time

from .. import sec_fwmodel as M


def _get(api, path: str, errors: dict, part: str):
    from ..sec_fwapi import FirewallAPIError
    try:
        return api("GET", path)
    except FirewallAPIError as e:
        errors.setdefault(part, str(e)[:200])
        return None


def _rows(d) -> list[dict]:
    return (d or {}).get("rows") or [] if isinstance(d, dict) else []


def _on(x) -> bool:
    return str(x).lower() in ("1", "true", "yes")


def _net(x) -> list[str]:
    s = str(x or "").strip()
    return [] if s in ("", "any") else [p for p in s.split(",") if p]


def _selected(opts: dict) -> str:
    return next((k for k, v in (opts or {}).items() if isinstance(v, dict) and v.get("selected")), "")


def _interfaces(api, err: dict) -> list[dict]:
    return [i for i in _rows(_get(api, "/interfaces/overview/interfaces_info", err, "interfaces")) if i.get("identifier")]


def read_model(cfg, group: str) -> dict:
    from .opnsense import _API, alias_name
    api = _API(cfg)
    m = M.empty("opnsense")
    err = m["_errors"]
    ifaces = _interfaces(api, err)
    own = {str(i.get("addr4") or "").split("/")[0] for i in ifaces if i.get("addr4")}
    rows = sorted(_rows(_get(api, "/firewall/filter/search_rule", err, "rules")), key=lambda r: str(r.get("sort_order") or ""))
    for r in rows:
        where = str(r.get("%interface") or r.get("interface") or "")
        dest = str(r.get("destination_net") or "")
        to_self = M.is_self(dest) or dest in own
        m["rules"].append(M.rule(
            str(r.get("description") or r.get("uuid")), _on(r.get("enabled")), str(r.get("action") or ""),
            src_zones=[z.strip().upper() for z in where.split(",") if z.strip()], src_nets=_net(r.get("source_net")),
            dst_nets=[] if to_self else _net(dest), ports=M.ports_of(r.get("protocol"), r.get("destination_port")),
            log=_on(r.get("log")), to_self=to_self, system=bool(r.get("is_automatic"))))
    for n in _rows(_get(api, "/firewall/d_nat/search_rule", err, "nat")):
        if n.get("is_automatic"):
            continue                                         # the anti-lockout redirect: the firewall's own
        m["nat"].append({"name": str(n.get("descr") or n.get("uuid")), "enabled": not _on(n.get("disabled")),
                         "services": [], "ports": M.ports_of(n.get("protocol"), n.get("destination.port")),
                         "target": _net(n.get("target")), "sources": _net(n.get("source.network")),
                         "outside": str(n.get("interface")) == "wan"})
    M.wan_access(m)
    ids = _get(api, "/ids/settings/get", err, "threat")
    if ids is not None:
        g = ((ids.get("ids") or {}).get("general") or {})
        mode = _selected(g.get("mode") or {})
        m["threat"] = {"what": "Suricata (Intrusion Detection)",
                       "state": ("on" if mode in ("netmap", "divert") else "log") if _on(g.get("enabled")) else "off"}
    if not err.get("rules"):
        m["login"]["lockout"] = any(r["enabled"] and "sshlockout" in r["src_nets"] for r in m["rules"])
    dest = _get(api, "/syslog/settings/search_destinations", err, "syslog")
    for s in _rows(dest):
        if not _on(s.get("enabled", "1")):
            continue
        programs = [p for p in str(s.get("program") or "").split(",") if p]
        m["syslog"].append({"address": s.get("hostname"), "name": s.get("description") or s.get("hostname"),
                            "threats_off": [] if not programs or "filterlog" in programs else ["filterlog (le regole del firewall)"]})
    m["block_object"] = alias_name(group)
    return m


def read_network(cfg) -> dict:
    """The map (sec_netmap's form): hosts from the host and network aliases, the interfaces, DHCP (dnsmasq's ranges and
    hosts, Kea's reservations), the routes; and what the firewall sees now (ARP and leases) as «seen»."""
    from ..sec_fwapi import FirewallAPIError
    from .opnsense import _API
    api = _API(cfg)
    err: dict = {}
    hosts, groups = [], []
    for a in _rows(_get(api, "/firewall/alias/search_item", err, "aliases")):
        if a.get("type") not in ("host", "network"):
            continue
        blocked = str(a.get("description", "")).startswith("Aurora:")
        names = []
        for i, addr in enumerate([x for x in str(a.get("content") or "").splitlines() if x.strip()]):
            name = f"aurora-block-{addr}" if blocked else f"{a['name']}-{i + 1}"
            hosts.append({"name": name, "type": "IP" if "/" not in addr and a["type"] == "host" else "Network",
                          "address": addr, "groups": [a["name"]]})
            names.append(name)
        groups.append({"name": a["name"], "hosts": names})
    ifaces = _interfaces(api, err)
    zone = {str(i["identifier"]): str(i.get("description") or i["identifier"]).upper() for i in ifaces}
    interfaces = []
    for i in ifaces:
        ip, _, bits = str(i.get("addr4") or "").partition("/")
        interfaces.append({"id": str(i["identifier"]), "name": str(i.get("description") or i["identifier"]),
                           "hardware": str(i.get("device") or ""),
                           "ip": ip, "netmask": bits, "zone": zone[str(i["identifier"])], "status": str(i.get("status") or "")})
    dhcp = []
    d = _get(api, "/dnsmasq/settings/get", err, "dhcp") or {}
    dm = (d.get("dnsmasq") or {}) if isinstance(d, dict) else {}
    static = [{"host": str(h.get("host") or h.get("descr") or ""), "mac": str(h.get("hwaddr") or ""), "ip": str(h.get("ip") or "")}
              for h in _rows(_get(api, "/dnsmasq/settings/search_host", err, "dhcp")) if h.get("ip")]
    static += [{"host": str(h.get("hostname") or h.get("description") or ""), "mac": str(h.get("hw_address") or ""),
                "ip": str(h.get("ip_address") or "")} for h in _rows(_get(api, "/kea/dhcpv4/search_reservation", err, "dhcp"))
               if h.get("ip_address")]
    ranges = dm.get("dhcp_ranges") or []
    if ranges or static:
        dhcp.append({"name": "DHCP", "interface": ", ".join(sorted({zone.get(str(r.get("interface")), str(r.get("interface")))
                                                                    for r in ranges if isinstance(r, dict)})),
                     "on": _on(dm.get("enable")), "static": static,
                     "range": [f"{r.get('start_addr')}-{r.get('end_addr')}" for r in ranges if isinstance(r, dict)]})
    routes = [{"to": str(r.get("network")), "via": str(r.get("gateway") or ""), "interface": ""}
              for r in _rows(_get(api, "/routes/routes/searchroute", err, "routes")) if not _on(r.get("disabled"))]
    seen = {}
    for x in _rows(_get(api, "/diagnostics/interface/search_arp", err, "arp")):
        seen[x.get("ip")] = {"ip": x.get("ip"), "mac": x.get("mac") or "", "host": x.get("hostname") or "",
                             "interface": str(x.get("intf_description") or x.get("intf") or "")}
    for x in _rows(_get(api, "/dnsmasq/leases/search", err, "leases")):
        if x.get("address"):
            seen.setdefault(x["address"], {"ip": x["address"], "mac": x.get("hwaddr") or "", "interface": ""})["host"] = \
                str(x.get("hostname") or "")
    if not interfaces and err:
        raise FirewallAPIError("; ".join(f"{k}: {v}" for k, v in err.items()))
    return {"at": time.time(), "hosts": hosts, "groups": groups, "interfaces": interfaces, "zones": sorted(set(zone.values())),
            "dhcp": dhcp, "routes": routes, "seen": sorted(seen.values(), key=lambda s: str(s["ip"])), "errors": err}
