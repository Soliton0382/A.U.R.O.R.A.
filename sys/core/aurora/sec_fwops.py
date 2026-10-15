# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The plans of sec_fwwrite for the dialects that speak the neutral operations (ROADMAP N8: pfSense, OPNsense): the
same four changes — publish a server, take it back, quarantine a device, release it — as steps of operations their
driver knows (fw_drivers/<kind>_write: put_alias, alias_add, put_rule, put_nat, their drop and del). A step is the
same record as the first dialect's ({entity, name, xml: the operation, undo: its opposite, why}), so sec_fwwrite
applies, confirms and undoes it the same way.

Aurora's objects are named so they are known as hers: rules and port forwards «Aurora-<label> <proto> <port>», aliases
«Aurora_…». A port forward passes nothing by itself: the plan's rule passes it, towards the server's address, with its
log, and is placed after the blocks (they are a floating rule there, evaluated first)."""
from __future__ import annotations

import ipaddress
import json

from . import sec_fwmodel, sec_netmap, sys_config

QUARANTINE = "Aurora_Quarantine"


class OpsError(Exception):
    pass


def _op(op: str, **args) -> str:
    return json.dumps({"op": op, **args})


def _step(entity: str, name: str, body: str, undo: str, why: str) -> dict:
    return {"entity": entity, "name": name, "xml": body, "undo": undo, "why": why, "owner_object": False}


def _iface_of(net: dict, ip: str) -> dict:
    a = ipaddress.ip_address(ip)
    for i in net.get("interfaces", []):
        try:
            if i["ip"] and i["netmask"] and a in ipaddress.ip_network(f"{i['ip']}/{i['netmask']}", strict=False):
                return i
        except ValueError:
            continue
    raise OpsError(f"{ip} non è in nessuna rete del firewall")


def _wan_ip(net: dict) -> str:
    return next((i["ip"] for i in net.get("interfaces", []) if i["zone"] == "WAN" and i["ip"]), "")


def plan_publish(fw: sys_config.Config, label: str, ip: str, plist: list[tuple[str, str]], sources: list[str],
                 net: dict | None = None) -> dict:
    """A server of the house reachable from the Internet: a port forward and its rule for each port; the origin, when
    given, an alias of addresses (a name must be an alias that exists)."""
    net = net if net is not None else sec_netmap.read(fw)
    zone = _iface_of(net, ip)["zone"]
    if zone == "WAN":
        raise OpsError(f"{ip} è nella rete WAN")
    known = {g["name"] for g in net.get("groups", [])}
    addrs, names = [], []
    for s in sources:
        try:
            addrs.append(str(ipaddress.ip_network(s, strict=False)) if "/" in s else str(ipaddress.ip_address(s)))
        except ValueError:
            if s not in known:
                raise OpsError(f"origine «{s}»: su questo firewall serve un indirizzo, o un alias che esiste") from None
            names.append(s)
    if names and addrs or len(names) > 1:
        raise OpsError("origine: o indirizzi, o un solo alias che esiste")
    steps, source = [], "any"
    if addrs:
        source = f"Aurora_src_{label}"[:31].replace("-", "_").replace(".", "_")
        steps.append(_step("alias", source, _op("put_alias", name=source, addresses=addrs, descr=f"Aurora: {label}, chi può entrare"),
                           _op("drop_alias", name=source), f"l'alias {source}: {', '.join(addrs)}"))
    elif names:
        source = names[0]
    check = []
    for proto, port in plist:
        d = f"Aurora-{label} {proto} {port}"
        steps.append(_step("nat", d, _op("put_nat", descr=d, protocol=proto.lower(), port=port, target=ip, source=source),
                           _op("drop_nat", descr=d), f"il port forward {proto} {port} → {ip}"))
        steps.append(_step("rule", d, _op("put_rule", descr=d, interfaces=["wan"], action="pass", source=source,
                                          destination=ip, port=port, protocol=proto.lower(), log=True),
                           _op("drop_rule", descr=d), f"la regola che lo lascia passare, col log"))
        check += [("nat", d), ("rule", d)]
    notes = []
    wan = _wan_ip(net)
    if wan and ipaddress.ip_address(wan).is_private:
        notes.append(f"Il firewall è dietro un altro router (WAN {wan}, indirizzo privato): quel router deve inoltrare "
                     f"{', '.join(q for _, q in plist)} a {wan} (o avere il firewall in DMZ).")
    if source == "any":
        notes.append("Aperto a tutta Internet: con gli indirizzi di chi deve entrare il servizio è meno esposto.")
    return {"kind": "publish", "title": f"Pubblicare {label}: {', '.join(f'{p} {q}' for p, q in plist)} → {ip}",
            "why": f"richiesta del proprietario; zona {zone}, log attivo", "steps": steps, "notes": notes, "check": check}


def plan_unpublish(fw: sys_config.Config, label: str, model: dict | None = None) -> dict:
    model = model if model is not None else sec_fwmodel.read(fw)
    head = f"Aurora-{label.removeprefix('Aurora-')} "
    steps = [_step("nat", n["name"], _op("drop_nat", descr=n["name"]), "", f"togliere il port forward {n['name']}")
             for n in model["nat"] if n["name"].startswith(head)]
    steps += [_step("rule", r["name"], _op("drop_rule", descr=r["name"]), "", f"togliere la regola {r['name']}")
              for r in model["rules"] if r["name"].startswith(head)]
    if not steps:
        raise OpsError(f"nessuna pubblicazione «{head.strip()}» di Aurora")
    return {"kind": "unpublish", "title": f"Ritirare la pubblicazione {head.strip()}", "why": "richiesta del proprietario",
            "steps": steps, "notes": ["Chiusa da Internet: il servizio resta raggiungibile in casa."], "check": []}


def plan_quarantine(fw: sys_config.Config, ip: str, reason: str, net: dict | None = None, model: dict | None = None) -> dict:
    """A device of the house stopped at the firewall: its address in Aurora's quarantine alias, blocked by one rule on
    every inside interface (made the first time)."""
    net = net if net is not None else sec_netmap.read(fw)
    model = model if model is not None else sec_fwmodel.read(fw)
    if _iface_of(net, ip)["zone"] == "WAN":
        raise OpsError("la quarantena è per i dispositivi della casa")
    group = next((g for g in net.get("groups", []) if g["name"] == QUARANTINE), None)
    if any(h["address"] == ip and QUARANTINE in h["groups"] for h in net.get("hosts", [])):
        raise OpsError(f"{ip} è già in quarantena")
    steps = []
    if group is None:
        steps.append(_step("alias", QUARANTINE, _op("put_alias", name=QUARANTINE, addresses=[ip], descr="Aurora: dispositivi in quarantena"),
                           _op("drop_alias", name=QUARANTINE), f"l'alias {QUARANTINE} con {ip}"))
    else:
        steps.append(_step("alias", QUARANTINE, _op("alias_add", name=QUARANTINE, ip=ip, desc=reason[:120]),
                           _op("alias_del", name=QUARANTINE, ip=ip), f"{ip} nell'alias {QUARANTINE}"))
    rule = "Aurora-Quarantine"
    if not any(r["name"] == rule for r in model["rules"]):
        inside = [i.get("id") or i["name"].lower() for i in net.get("interfaces", [])
                  if i["zone"] not in ("WAN", "LOOPBACK") and i["ip"]]
        steps.append(_step("rule", rule, _op("put_rule", descr=rule, interfaces=inside, floating=True, action="block",
                                             source=QUARANTINE, destination="any", log=True),
                           _op("drop_rule", descr=rule), "la regola: i dispositivi in quarantena non passano"))
    return {"kind": "quarantine", "title": f"Quarantena di {ip}", "why": reason[:300], "steps": steps,
            "notes": ["Il firewall ferma solo il traffico che lo attraversa (Internet, altre reti): due dispositivi "
                      "sullo stesso switch possono ancora parlarsi.",
                      "Se il dispositivo prende un altro indirizzo dal DHCP esce dalla quarantena: meglio una "
                      "prenotazione DHCP."], "check": [("alias", QUARANTINE), ("rule", rule)]}


def plan_release(fw: sys_config.Config, ip: str, net: dict | None = None) -> dict:
    net = net if net is not None else sec_netmap.read(fw)
    if not any(h["address"] == ip and QUARANTINE in h["groups"] for h in net.get("hosts", [])):
        raise OpsError(f"{ip} non è in quarantena")
    return {"kind": "release", "title": f"Fine della quarantena di {ip}", "why": "richiesta del proprietario",
            "steps": [_step("alias", QUARANTINE, _op("alias_del", name=QUARANTINE, ip=ip), _op("alias_add", name=QUARANTINE, ip=ip),
                            f"{ip} fuori dall'alias {QUARANTINE}")], "notes": [], "check": []}


def exists(fw: sys_config.Config, entity: str, name: str) -> bool:
    """The read-back of an object of a change (sec_fwwrite.confirm)."""
    from . import sec_fwapi
    text = sec_fwapi.request(fw, _op("exists", what=entity, name=name))
    return json.loads(text).get("code") == "200"


def port_block_steps(fw: sys_config.Config, ip: str, plist: list[tuple[str, str]], name: str, desc: str,
                     model: dict | None = None) -> tuple[list[dict], list[tuple[str, str]]]:
    """An address dropped on some ports only (sec_fwport): one floating rule from the WAN for each port, before the
    others; (steps, what to read back)."""
    model = model if model is not None else sec_fwmodel.read(fw)
    if any(r["name"].startswith(name + " ") for r in model["rules"]):
        raise OpsError(f"{ip} è già bloccato così («{name}»)")
    steps, check = [], []
    for proto, port in plist:
        d = f"{name} {proto} {port}"
        steps.append(_step("rule", d, _op("put_rule", descr=d, interfaces=["wan"], floating=True, action="block", source=ip,
                                          destination="any", port=port, protocol=proto.lower(), log=True),
                           _op("drop_rule", descr=d), f"{ip} fermato su {proto} {port} ({desc[:80]})"))
        check.append(("rule", d))
    return steps, check
