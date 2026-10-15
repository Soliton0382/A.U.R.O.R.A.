# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A firewall's configuration in one neutral form, whatever its dialect (ROADMAP N8, owner, 16 Oct: «finisci le restanti
cose appese per i firewall»): what the audit (sec_audit) judges. Each dialect reads its own objects and gives this; the
first dialect's configuration (sec_fwconf, its XML) is turned into it by of_sophos, the others by their driver's
read_model. Read only.

  rules      in the order the firewall evaluates them: {name, enabled, action Accept|Drop|Reject, src_zones,
             dst_zones, src_nets, dst_nets, services, ports ["TCP 443", …], ips (the rule's IPS policy, "None" when
             it has none, None where a rule has no such field), log, to_self (towards the firewall itself), system
             (made by the firewall, not the owner)}; a zone is the interface's role in capitals: WAN, LAN…
  nat        port forwards: {name, enabled, services, ports, target, sources, outside}
  wan_admin  the firewall's administration reachable from the WAN (["HTTPS", "SSH"]); wan_services: its other services
  threat     {"what": the engine's name, "state": "on" | "log" | "off" | None (not read)}
  login      {"lockout": True | False | None, "complexity": True | False | None} — None: the dialect does not say
  syslog     [{"address", "name", "threats_off": [...]}] — where the firewall sends its log
  ips_policies  names of IPS policies that exist (a rule's fix can name one)
  block_object  the name the blocking group has on this firewall
  _errors    {part: why} for a part that could not be read (judged as unread, never as absent); the first dialect
             names its parts by its entities (error_of)
"""
from __future__ import annotations

import re

from . import sec_fwconf

ACTIONS = {"pass": "Accept", "block": "Drop", "reject": "Reject"}


def empty(kind: str) -> dict:
    return {"kind": kind, "rules": [], "nat": [], "wan_admin": [], "wan_services": [],
            "threat": {"what": "", "state": None}, "login": {"lockout": None, "complexity": None}, "syslog": [],
            "ips_policies": [], "block_object": "", "_errors": {}}


def rule(name: str, enabled: bool, action: str, **kw) -> dict:
    r = {"name": name, "enabled": enabled, "action": ACTIONS.get(action, action), "src_zones": [], "dst_zones": [],
         "src_nets": [], "dst_nets": [], "services": [], "ports": [], "ips": None, "log": False, "to_self": False,
         "system": False}
    r.update(kw)
    return r


def is_model(x: dict) -> bool:
    return isinstance(x, dict) and "rules" in x and "threat" in x


def of_sophos(conf: dict, group: str = "") -> dict:
    """The first dialect's configuration (sec_fwconf.read) in the neutral form."""
    m = empty("sophos")
    m["_errors"] = dict(conf.get("_errors") or {})
    m["block_object"] = group
    for raw in conf.get("FirewallRule", []):
        r = sec_fwconf.rule_view(raw)
        ports = [p for s in r["services"] for p in sec_fwconf.ports(conf, s)]
        m["rules"].append(rule(r["name"], r["enabled"], r["action"], src_zones=r["src_zones"], dst_zones=r["dst_zones"],
                               src_nets=r["src_nets"], dst_nets=r["dst_nets"], services=r["services"], ports=ports,
                               ips=r["ips"], log=r["log"], description=r["description"]))
    for n in conf.get("NATRule", []):
        services = sec_fwconf.listed(n.get("OriginalServices"), "Service")
        m["nat"].append({"name": str(n.get("Name", "")), "enabled": n.get("Status") == "Enable", "services": services,
                         "ports": [p for s in services for p in sec_fwconf.ports(conf, s)],
                         "target": sec_fwconf.listed(n.get("TranslatedDestination"), "Network"),
                         "sources": sec_fwconf.listed(n.get("OriginalSourceNetworks"), "Network"),
                         # the firewall's loopback/reflexive copies are not a way in from outside
                         "outside": not str(n.get("Name", "")).startswith(("Loopback_", "Reflexive_"))})
    for z in conf.get("Zone", []):
        if z.get("Type") != "WAN" and z.get("Name") != "WAN":
            continue
        acc = z.get("ApplianceAccess") or {}
        m["wan_admin"] += [k for k, v in (acc.get("AdminServices") or {}).items() if v == "Enable"]
        m["wan_services"] += [k for grp, d in acc.items() if grp != "AdminServices" and isinstance(d, dict)
                              for k, v in d.items() if v == "Enable"]
        m["wan_zone"] = z.get("Name", "WAN")
    for a in conf.get("ATP", [])[:1]:
        on = a.get("ThreatProtectionStatus") == "Enable"
        m["threat"] = {"what": "ATP", "state": ("on" if "drop" in str(a.get("Policy", "")).lower() else "log") if on else "off",
                       "policy": a.get("Policy")}
    for s in conf.get("AdminSettings", [])[:1]:
        m["login"] = {"lockout": (s.get("LoginSecurity") or {}).get("BlockLogin") == "Enable",
                      "complexity": (s.get("PasswordComplexitySettings") or {}).get("PasswordComplexityCheck") == "Enable"}
    for s in conf.get("SyslogServers", []):
        ls = s.get("LogSettings") or {}
        m["syslog"].append({"address": s.get("ServerAddress"), "name": s.get("Name"),
                            "threats_off": [f"{grp}/{k}" for grp in ("IPS", "ATP") for k, v in (ls.get(grp) or {}).items()
                                            if v != "Enable"]})
    m["ips_policies"] = [str(p.get("Name", "")) for p in conf.get("IPSPolicy", [])]
    return m


# the part of the model → the name its error has in this dialect (the first dialect's entities; the others: the part)
PART = {"sophos": {"rules": "FirewallRule", "syslog": "SyslogServers"}}


def error_of(m: dict, part: str) -> tuple[str, str | None]:
    """(the name of a part as its dialect says it, why it was not read or None)."""
    name = PART.get(m.get("kind", ""), {}).get(part, part)
    return name, (m.get("_errors") or {}).get(name)


def read(cfg) -> dict:
    """The configuration of the firewall of `cfg` (sec_firewalls.view for one of many), in the neutral form."""
    from .fw_drivers import driver
    kind = str(cfg["AURORA_FIREWALL_API_KIND"])
    group = str(cfg["AURORA_FIREWALL_BLOCK_GROUP"])
    if kind == "sophos":
        return of_sophos(sec_fwconf.read(cfg), group)
    return driver(cfg).read_model(cfg, group)


# ---- helpers for the dialects whose rules are per interface (pfSense, OPNsense) -------------------------------------
SELF = ("(self)", "This Firewall", "thisfirewall")
ADMIN_PORTS = {"22": "SSH"}


def is_self(dest: str) -> bool:
    """A destination that is the firewall itself: (self), «This Firewall», an interface's own address (wan:ip, wanip)."""
    d = str(dest or "").strip()
    return d in SELF or d.endswith(":ip") or bool(re.fullmatch(r"(wan|lan|opt\d+)ip", d))


def ports_of(protocol: str | None, port: str | None) -> list[str]:
    proto = str(protocol or "").upper().replace("/", "+")
    if not port:
        return [proto] if proto and proto not in ("ANY", "TCP+UDP", "TCP", "UDP") else []
    return [f"{p} {port}" for p in (proto.split("+") if proto and proto != "ANY" else ["TCP", "UDP"])]


def wan_access(m: dict, gui_port: str = "443") -> None:
    """The firewall's own services reachable from the WAN, read from the rules that let the WAN in towards the firewall:
    its administration (the web GUI's port, SSH, or every port) and the others (a VPN…)."""
    admin = {gui_port: "HTTPS", **ADMIN_PORTS}
    for r in m["rules"]:
        if not (r["enabled"] and r["action"] == "Accept" and "WAN" in r["src_zones"] and r["to_self"] and not r["system"]):
            continue
        if not r["ports"]:
            m["wan_admin"] += [f"ogni porta («{r['name']}»)"]
            continue
        for p in r["ports"]:
            num = p.split(" ")[-1]
            (m["wan_admin"] if num in admin else m["wan_services"]).append(admin.get(num, p))
    m["wan_admin"] = list(dict.fromkeys(m["wan_admin"]))
    m["wan_services"] = list(dict.fromkeys(m["wan_services"]))
