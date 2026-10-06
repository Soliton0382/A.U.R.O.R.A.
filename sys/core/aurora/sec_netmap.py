# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The network as the firewall sees it (owner, 2026-10-06: "the hosts by name with the IPs in brackets, and a map of
the network, saved and encrypted, so Aurora knows how the network managed by the firewall is made").

Read only, through the firewall's API (sec_fwapi.request, <Get>): IP hosts and their groups, interfaces with their
zones, zones, the DHCP servers with their reserved (static) addresses, the static routes. Measured on the owner's
firewall (6 October): 363 IP hosts, 15 groups, 9 interfaces, 7 zones, 4 DHCP servers; dynamic leases and the ARP table
are not in the API (529 "Input request module is Invalid"): a device that only took a dynamic address is not seen.

The map is sealed (sys_seal, its own key "network") in <STATUS>/security/netmap.sealed; the one before it is kept to
say what changed ("a new device"). names() gives "NAS (192.0.2.10)" for the incidents and the defence.
"""
from __future__ import annotations

import ipaddress
import json
import time
import xml.etree.ElementTree as ET

from . import sec_fwapi, sys_config, sys_seal

ENTITIES = ("IPHost", "IPHostGroup", "Interface", "Zone", "DHCPServer", "UnicastRoute")
_names: dict = {"at": 0.0, "map": {}}


def _dir(cfg: sys_config.Config):
    return cfg.path("AURORA_STATUS_DIR") / "security"


def _get(cfg: sys_config.Config, entity: str) -> list[ET.Element]:
    text = sec_fwapi.request(cfg, f"<Get><{entity}/></Get>")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise sec_fwapi.FirewallAPIError(f"{entity}: the answer is not XML ({e})") from None
    return [e for e in root.iter(entity) if e.find("Name") is not None or entity == "UnicastRoute"]


def _t(e: ET.Element | None, tag: str) -> str:
    x = e.find(tag) if e is not None else None
    return (x.text or "").strip() if x is not None else ""


def parse(raw: dict[str, list[ET.Element]]) -> dict:
    """The firewall's records as a plain map (also what the tests build)."""
    hosts = []
    for e in raw.get("IPHost", []):
        kind = _t(e, "HostType")
        addr = {"IP": _t(e, "IPAddress"), "Network": f"{_t(e, 'IPAddress')}/{_t(e, 'Subnet')}".rstrip("/"),
                "IPRange": f"{_t(e, 'StartIPAddress')}-{_t(e, 'EndIPAddress')}",
                "IPList": _t(e, "ListOfIPAddresses")}.get(kind, _t(e, "IPAddress"))
        groups = [g.text.strip() for g in e.iter("HostGroup") if g.text and g.text.strip()]
        hosts.append({"name": _t(e, "Name"), "type": kind, "address": addr, "groups": groups})
    groups = [{"name": _t(e, "Name"), "hosts": [h.text.strip() for h in e.iter("Host") if h.text]} for e in raw.get("IPHostGroup", [])]
    interfaces = [{"name": _t(e, "Name"), "hardware": _t(e, "Hardware"), "ip": _t(e, "IPAddress"), "netmask": _t(e, "Netmask"),
                   "zone": _t(e, "NetworkZone"), "status": _t(e, "InterfaceStatus")} for e in raw.get("Interface", [])]
    zones = [_t(e, "Name") for e in raw.get("Zone", [])]
    dhcp = []
    for e in raw.get("DHCPServer", []):
        leases = [{"host": _t(x, "HostName"), "mac": _t(x, "MACAddress"), "ip": _t(x, "IPAddress")} for x in e.iter("Lease")
                  if _t(x, "IPAddress")]
        dhcp.append({"name": _t(e, "Name"), "interface": _t(e, "Interface"), "on": _t(e, "Status") == "1",
                     "range": [_t(x, "IP") for x in e.iter("IPLease")], "static": leases})
    routes = [{"to": f"{_t(e, 'DestinationIP')}/{_t(e, 'Netmask')}", "via": _t(e, "Gateway"), "interface": _t(e, "Interface")}
              for e in raw.get("UnicastRoute", []) if _t(e, "DestinationIP")]
    return {"at": time.time(), "hosts": hosts, "groups": groups, "interfaces": interfaces, "zones": zones, "dhcp": dhcp,
            "routes": routes}


def load(cfg: sys_config.Config, which: str = "netmap") -> dict | None:
    f = _dir(cfg) / f"{which}.sealed"
    return json.loads(sys_seal.read(cfg, f, None, "network")) if f.exists() else None


def diff(old: dict | None, new: dict) -> dict:
    """What changed: devices (hosts and reserved addresses) new, gone, or with another address."""
    def devices(m):
        out = {h["name"]: h["address"] for h in (m or {}).get("hosts", []) if h["type"] == "IP"}
        out.update({f"{l['host'] or l['mac']} (DHCP)": l["ip"] for s in (m or {}).get("dhcp", []) for l in s["static"]})
        return out
    if old is None:
        return {"first": True, "new": [], "gone": [], "moved": []}
    a, b = devices(old), devices(new)
    return {"first": False, "new": sorted(f"{n} ({b[n]})" for n in b.keys() - a.keys()),
            "gone": sorted(f"{n} ({a[n]})" for n in a.keys() - b.keys()),
            "moved": sorted(f"{n}: {a[n]} → {b[n]}" for n in a.keys() & b.keys() if a[n] != b[n])}


def refresh(cfg: sys_config.Config) -> dict:
    """Read the firewall now, seal the map, keep the one before; returns the summary and what changed."""
    new = parse({e: _get(cfg, e) for e in ENTITIES})
    old = load(cfg)
    new["changes"] = diff(old, new)                     # kept with the map: the page says what the last look found
    d = _dir(cfg)
    if old is not None:
        sys_seal.write(cfg, d / "netmap.prev.sealed", json.dumps(old, ensure_ascii=False).encode(), None, "network")
    sys_seal.write(cfg, d / "netmap.sealed", json.dumps(new, ensure_ascii=False).encode(), None, "network")
    _names["at"] = 0.0
    return {**summary(new), "changes": new["changes"]}


def summary(m: dict | None) -> dict:
    if not m:
        return {"at": None}
    return {"at": m["at"], "hosts": len(m["hosts"]), "devices": sum(1 for h in m["hosts"] if h["type"] == "IP"),
            "groups": len(m["groups"]), "interfaces": len(m["interfaces"]), "zones": len(m["zones"]),
            "dhcp": len(m["dhcp"]), "reserved": sum(len(s["static"]) for s in m["dhcp"]), "routes": len(m["routes"])}


def names(cfg: sys_config.Config) -> dict[str, str]:
    """address -> name, from the hosts of one address and the reserved DHCP addresses (the map unsealed once a minute)."""
    if time.time() - _names["at"] < 60:
        return _names["map"]
    m, out = None, {}
    try:
        m = load(cfg)
    except (ValueError, OSError):
        pass
    for s in (m or {}).get("dhcp", []):
        for l in s["static"]:
            if l["host"]:
                out[l["ip"]] = l["host"]
    for h in (m or {}).get("hosts", []):                # a name given on the firewall wins over the DHCP host name
        if h["type"] == "IP" and h["address"] and not h["name"].startswith("aurora-block-"):
            out[h["address"]] = h["name"]
    _names.update(at=time.time(), map=out)
    return out


def label(cfg: sys_config.Config, ip: str) -> str:
    """ "NAS (192.0.2.10)" when the firewall knows the address, else the address."""
    n = names(cfg).get(ip)
    return f"{n} ({ip})" if n else ip


def find(m: dict, query: str) -> list[str]:
    """Lines about a name or an address (for the model: "che IP ha il NAS?", "chi è 192.0.2.10?")."""
    q = query.strip().lower()
    out = []
    for h in m.get("hosts", []):
        if q in h["name"].lower() or q in h["address"]:
            out.append(f"- {h['name']} ({h['address']}, {h['type']})" + (f", gruppi: {', '.join(h['groups'])}" if h["groups"] else ""))
    for s in m.get("dhcp", []):
        for l in s["static"]:
            if q in l["host"].lower() or q in l["ip"] or q in l["mac"].lower():
                out.append(f"- {l['host']} ({l['ip']}) — prenotazione DHCP su {s['interface']}")
    try:
        ip = ipaddress.ip_address(q)
        for i in m.get("interfaces", []):
            if i["ip"] and i["netmask"] and ip in ipaddress.ip_network(f"{i['ip']}/{i['netmask']}", strict=False):
                out.append(f"- {q} è nella rete dell'interfaccia {i['name']} ({i['ip']}/{i['netmask']}, zona {i['zone']})")
    except ValueError:
        pass
    return out[:40]


def changes_text(c: dict) -> str:
    """What a look at the network found, in words; "" when nothing changed (a routine "only if there is something")."""
    if c.get("first"):
        return "🗺️ Prima mappa della rete salvata: dal prossimo controllo ti dico cosa cambia."
    parts = ([f"🆕 Nuovi: {', '.join(c['new'])}"] if c["new"] else []) + \
            ([f"👋 Spariti: {', '.join(c['gone'])}"] if c["gone"] else []) + \
            ([f"🔀 Indirizzo cambiato: {', '.join(c['moved'])}"] if c["moved"] else [])
    return ("🗺️ La rete è cambiata.\n" + "\n".join(parts)) if parts else ""


def text(m: dict | None) -> str:
    """The map in words for the local model: interfaces and zones, DHCP, groups, how many hosts."""
    if not m:
        return "Nessuna mappa di rete: aggiornala nella pagina 🛡️ Sicurezza (serve l'API del firewall)."
    s = summary(m)
    lines = [f"Mappa del {time.strftime('%d/%m/%Y %H:%M', time.localtime(m['at']))}: {s['devices']} dispositivi con nome, "
             f"{s['hosts']} oggetti host, {s['groups']} gruppi, {s['reserved']} indirizzi riservati in DHCP."]
    lines += [f"- interfaccia {i['name']} ({i['hardware']}): {i['ip']}/{i['netmask']}, zona {i['zone']}, {i['status']}"
              for i in m["interfaces"] if i["ip"]]
    lines += [f"- DHCP {d['name']} su {d['interface']}{'' if d['on'] else ' (spento)'}: {', '.join(d['range'])}; "
              f"{len(d['static'])} prenotazioni" for d in m["dhcp"]]
    lines += [f"- gruppo {g['name']}: {len(g['hosts'])} host" for g in m["groups"]]
    lines += [f"- rotta {r['to']} via {r['via']} ({r['interface']})" for r in m["routes"]]
    return "\n".join(lines)
