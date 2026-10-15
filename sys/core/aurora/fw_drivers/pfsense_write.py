# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""pfSense writes (ROADMAP N8): the neutral operations of a plan (sec_fwops) on the REST API package. Every object is
found again by its name (an alias) or its description (a rule, a port forward): the package's ids are positions that
move when an object before them is deleted, so an id is never kept. Each operation applies the filter at its end.

  put_alias {name, addresses, descr}        made, or its addresses replaced
  drop_alias {name}
  alias_add / alias_del {name, ip, desc}    one address in or out of an alias
  put_rule {descr, interfaces | floating, action, source, destination, port, protocol, log}
  drop_rule {descr}
  put_nat {descr, protocol, port, target, local_port, source}   a port forward on the WAN address, no rule of its own
                                                                (the plan's put_rule passes it, with its log)
  drop_nat {descr}
  exists {what: alias | rule | nat, name}"""
from __future__ import annotations


def _find(api, path: str, key: str, value: str) -> dict | None:
    return next((x for x in api("GET", path) or [] if x.get(key) == value), None)


def _rule_body(b: dict) -> dict:
    proto = None if str(b.get("protocol") or "any").lower() == "any" else str(b["protocol"]).lower()   # every protocol: null
    body = {"type": b.get("action", "pass"), "ipprotocol": "inet", "protocol": proto,
            "source": b.get("source") or "any", "destination": b.get("destination") or "any",
            "descr": b["descr"], "log": bool(b.get("log", True))}
    if b.get("port") and proto in ("tcp", "udp", "tcp/udp"):
        body["destination_port"] = str(b["port"])
    if b.get("floating"):
        body.update(interface=list(b.get("interfaces") or ["wan"]), floating=True, quick=True, direction="any")
    else:
        body["interface"] = list(b.get("interfaces") or ["wan"])
    return body


def do(api, b: dict) -> dict:
    op = b["op"]
    if op == "exists":
        path, key = {"alias": ("/firewall/aliases", "name"), "rule": ("/firewall/rules", "descr"),
                     "nat": ("/firewall/nat/port_forwards", "descr")}[b["what"]]
        return {"code": "200" if _find(api, path, key, b["name"]) else "404", "message": ""}
    if op == "put_alias":
        a = _find(api, "/firewall/aliases", "name", b["name"])
        body = {"name": b["name"], "type": "host", "address": list(b.get("addresses") or []),
                "detail": [""] * len(b.get("addresses") or []), "descr": b.get("descr", "")[:200]}
        api("PATCH" if a else "POST", "/firewall/alias", json={**({"id": a["id"]} if a else {}), **body})
    elif op == "drop_alias":
        a = _find(api, "/firewall/aliases", "name", b["name"])
        if not a:
            return {"code": "200", "message": "already gone"}
        api("DELETE", "/firewall/alias", params={"id": a["id"]})
    elif op in ("alias_add", "alias_del"):
        a = _find(api, "/firewall/aliases", "name", b["name"])
        if not a:
            return {"code": "404", "message": f"no alias {b['name']}"}
        address, detail = list(a.get("address") or []), list(a.get("detail") or [])
        detail += [""] * (len(address) - len(detail))
        if op == "alias_add" and b["ip"] not in address:
            address.append(b["ip"])
            detail.append(str(b.get("desc", ""))[:200])
        elif op == "alias_del" and b["ip"] in address:
            i = address.index(b["ip"])
            del address[i], detail[i]
        api("PATCH", "/firewall/alias", json={"id": a["id"], "address": address, "detail": detail})
    elif op == "put_rule":
        r = _find(api, "/firewall/rules", "descr", b["descr"])
        api("PATCH" if r else "POST", "/firewall/rule", json={**({"id": r["id"]} if r else {}), **_rule_body(b)})
    elif op == "drop_rule":
        r = _find(api, "/firewall/rules", "descr", b["descr"])
        if not r:
            return {"code": "200", "message": "already gone"}
        api("DELETE", "/firewall/rule", params={"id": r["id"]})
    elif op == "put_nat":
        n = _find(api, "/firewall/nat/port_forwards", "descr", b["descr"])
        body = {"interface": "wan", "ipprotocol": "inet", "protocol": b.get("protocol") or "tcp",
                "source": b.get("source") or "any", "destination": "wan:ip", "destination_port": str(b["port"]),
                "target": b["target"], "local_port": str(b.get("local_port") or b["port"]).split(":")[0],
                "descr": b["descr"], "associated_rule_id": ""}
        api("PATCH" if n else "POST", "/firewall/nat/port_forward", json={**({"id": n["id"]} if n else {}), **body})
    elif op == "drop_nat":
        n = _find(api, "/firewall/nat/port_forwards", "descr", b["descr"])
        if not n:
            return {"code": "200", "message": "already gone"}
        api("DELETE", "/firewall/nat/port_forward", params={"id": n["id"]})
    else:
        return {"code": "400", "message": f"unknown operation {op}"}
    api.apply()
    return {"code": "200", "message": ""}
