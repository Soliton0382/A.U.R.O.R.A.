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
from .sys_lang import say as _t   # each sentence in the reader's language (C526)

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
    raise OpsError(_t(f"{ip} non è in nessuna rete del firewall", f"{ip} is in none of the firewall's networks"))


def _wan_ip(net: dict) -> str:
    return next((i["ip"] for i in net.get("interfaces", []) if i["zone"] == "WAN" and i["ip"]), "")


def plan_publish(fw: sys_config.Config, label: str, ip: str, plist: list[tuple[str, str]], sources: list[str],
                 net: dict | None = None) -> dict:
    """A server of the house reachable from the Internet: a port forward and its rule for each port; the origin, when
    given, an alias of addresses (a name must be an alias that exists)."""
    net = net if net is not None else sec_netmap.read(fw)
    zone = _iface_of(net, ip)["zone"]
    if zone == "WAN":
        raise OpsError(_t(f"{ip} è nella rete WAN", f"{ip} is in the WAN network"))
    known = {g["name"] for g in net.get("groups", [])}
    addrs, names = [], []
    for s in sources:
        try:
            addrs.append(str(ipaddress.ip_network(s, strict=False)) if "/" in s else str(ipaddress.ip_address(s)))
        except ValueError:
            if s not in known:
                raise OpsError(_t(f"origine «{s}»: su questo firewall serve un indirizzo, o un alias che esiste", f"source «{s}»: this firewall needs an address, or an alias that exists")) from None
            names.append(s)
    if names and addrs or len(names) > 1:
        raise OpsError(_t("origine: o indirizzi, o un solo alias che esiste", "source: either addresses, or one alias that exists"))
    steps, source = [], "any"
    if addrs:
        source = f"Aurora_src_{label}"[:31].replace("-", "_").replace(".", "_")
        steps.append(_step("alias", source, _op("put_alias", name=source, addresses=addrs, descr=f"Aurora: {label}, chi può entrare"),
                           _op("drop_alias", name=source), _t(f"l'alias {source}: {', '.join(addrs)}", f"the alias {source}: {', '.join(addrs)}")))
    elif names:
        source = names[0]
    check = []
    for proto, port in plist:
        d = f"Aurora-{label} {proto} {port}"
        steps.append(_step("nat", d, _op("put_nat", descr=d, protocol=proto.lower(), port=port, target=ip, source=source),
                           _op("drop_nat", descr=d), _t(f"il port forward {proto} {port} → {ip}", f"the port forward {proto} {port} → {ip}")))
        steps.append(_step("rule", d, _op("put_rule", descr=d, interfaces=["wan"], action="pass", source=source,
                                          destination=ip, port=port, protocol=proto.lower(), log=True),
                           _op("drop_rule", descr=d), _t(f"la regola che lo lascia passare, col log", "the rule that lets it through, with the log")))
        check += [("nat", d), ("rule", d)]
    notes = []
    wan = _wan_ip(net)
    if wan and ipaddress.ip_address(wan).is_private:
        notes.append(_t(f"Il firewall è dietro un altro router (WAN {wan}, indirizzo privato): quel router deve inoltrare "
                     f"{', '.join(q for _, q in plist)} a {wan} (o avere il firewall in DMZ).", f"The firewall is behind another router (WAN {wan}, a private address): that router must forward "
                     f"{', '.join(q for _, q in plist)} to {wan} (or have the firewall in its DMZ)."))
    if source == "any":
        notes.append(_t("Aperto a tutta Internet: con gli indirizzi di chi deve entrare il servizio è meno esposto.", "Open to the whole Internet: with the addresses of who must come in, the service is less exposed."))
    return {"kind": "publish", "title": _t(f"Pubblicare {label}: {', '.join(f'{p} {q}' for p, q in plist)} → {ip}", f"Publish {label}: {', '.join(f'{p} {q}' for p, q in plist)} → {ip}"),
            "why": _t(f"richiesta del proprietario; zona {zone}, log attivo", f"the owner's request; zone {zone}, log on"), "steps": steps, "notes": notes, "check": check}


def plan_unpublish(fw: sys_config.Config, label: str, model: dict | None = None) -> dict:
    model = model if model is not None else sec_fwmodel.read(fw)
    head = f"Aurora-{label.removeprefix('Aurora-')} "
    steps = [_step("nat", n["name"], _op("drop_nat", descr=n["name"]), "", _t(f"togliere il port forward {n['name']}", f"remove the port forward {n['name']}"))
             for n in model["nat"] if n["name"].startswith(head)]
    steps += [_step("rule", r["name"], _op("drop_rule", descr=r["name"]), "", _t(f"togliere la regola {r['name']}", f"remove the rule {r['name']}"))
              for r in model["rules"] if r["name"].startswith(head)]
    if not steps:
        raise OpsError(_t(f"nessuna pubblicazione «{head.strip()}» di Aurora", f"no publication «{head.strip()}» of Aurora's"))
    return {"kind": "unpublish", "title": _t(f"Ritirare la pubblicazione {head.strip()}", f"Withdraw the publication {head.strip()}"), "why": _t("richiesta del proprietario", "the owner's request"),
            "steps": steps, "notes": [_t("Chiusa da Internet: il servizio resta raggiungibile in casa.", "Closed from the Internet: the service can still be reached at home.")], "check": []}


def plan_quarantine(fw: sys_config.Config, ip: str, reason: str, net: dict | None = None, model: dict | None = None) -> dict:
    """A device of the house stopped at the firewall: its address in Aurora's quarantine alias, blocked by one rule on
    every inside interface (made the first time)."""
    net = net if net is not None else sec_netmap.read(fw)
    model = model if model is not None else sec_fwmodel.read(fw)
    if _iface_of(net, ip)["zone"] == "WAN":
        raise OpsError(_t("la quarantena è per i dispositivi della casa", "the quarantine is for the devices of the house"))
    group = next((g for g in net.get("groups", []) if g["name"] == QUARANTINE), None)
    if any(h["address"] == ip and QUARANTINE in h["groups"] for h in net.get("hosts", [])):
        raise OpsError(_t(f"{ip} è già in quarantena", f"{ip} is already in quarantine"))
    steps = []
    if group is None:
        steps.append(_step("alias", QUARANTINE, _op("put_alias", name=QUARANTINE, addresses=[ip], descr="Aurora: dispositivi in quarantena"),
                           _op("drop_alias", name=QUARANTINE), _t(f"l'alias {QUARANTINE} con {ip}", f"the alias {QUARANTINE} with {ip}")))
    else:
        steps.append(_step("alias", QUARANTINE, _op("alias_add", name=QUARANTINE, ip=ip, desc=reason[:120]),
                           _op("alias_del", name=QUARANTINE, ip=ip), _t(f"{ip} nell'alias {QUARANTINE}", f"{ip} in the alias {QUARANTINE}")))
    rule = "Aurora-Quarantine"
    if not any(r["name"] == rule for r in model["rules"]):
        inside = [i.get("id") or i["name"].lower() for i in net.get("interfaces", [])
                  if i["zone"] not in ("WAN", "LOOPBACK") and i["ip"]]
        steps.append(_step("rule", rule, _op("put_rule", descr=rule, interfaces=inside, floating=True, action="block",
                                             source=QUARANTINE, destination="any", log=True),
                           _op("drop_rule", descr=rule), _t("la regola: i dispositivi in quarantena non passano", "the rule: the devices in quarantine do not pass")))
    return {"kind": "quarantine", "title": _t(f"Quarantena di {ip}", f"Quarantine of {ip}"), "why": reason[:300], "steps": steps,
            "notes": [_t("Il firewall ferma solo il traffico che lo attraversa (Internet, altre reti): due dispositivi "
                      "sullo stesso switch possono ancora parlarsi.", "The firewall stops only the traffic that crosses it (Internet, other networks): two devices "
                      "on the same switch can still talk to each other."),
                      _t("Se il dispositivo prende un altro indirizzo dal DHCP esce dalla quarantena: meglio una "
                      "prenotazione DHCP.", "If the device gets another address from the DHCP it leaves the quarantine: better a "
                      "DHCP reservation.")], "check": [("alias", QUARANTINE), ("rule", rule)]}


def plan_release(fw: sys_config.Config, ip: str, net: dict | None = None) -> dict:
    net = net if net is not None else sec_netmap.read(fw)
    if not any(h["address"] == ip and QUARANTINE in h["groups"] for h in net.get("hosts", [])):
        raise OpsError(_t(f"{ip} non è in quarantena", f"{ip} is not in quarantine"))
    return {"kind": "release", "title": _t(f"Fine della quarantena di {ip}", f"End of the quarantine of {ip}"), "why": _t("richiesta del proprietario", "the owner's request"),
            "steps": [_step("alias", QUARANTINE, _op("alias_del", name=QUARANTINE, ip=ip), _op("alias_add", name=QUARANTINE, ip=ip),
                            _t(f"{ip} fuori dall'alias {QUARANTINE}", f"{ip} out of the alias {QUARANTINE}"))], "notes": [], "check": []}


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
        raise OpsError(_t(f"{ip} è già bloccato così («{name}»)", f"{ip} is already blocked this way («{name}»)"))
    steps, check = [], []
    for proto, port in plist:
        d = f"{name} {proto} {port}"
        steps.append(_step("rule", d, _op("put_rule", descr=d, interfaces=["wan"], floating=True, action="block", source=ip,
                                          destination="any", port=port, protocol=proto.lower(), log=True),
                           _op("drop_rule", descr=d), _t(f"{ip} fermato su {proto} {port} ({desc[:80]})", f"{ip} stopped on {proto} {port} ({desc[:80]})")))
        check.append(("rule", d))
    return steps, check
