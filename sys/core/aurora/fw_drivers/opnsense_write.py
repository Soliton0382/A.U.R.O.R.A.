# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""OPNsense writes (ROADMAP N8): the neutral operations of a plan (sec_fwops; the same names as pfsense_write) on its
own API. An object is found again by its name (an alias) or its description (a filter rule, a port forward), its
uuid read at that moment; each operation applies its part (aliases reconfigured, the filter or the NAT applied).
Measured on the aurora-lab OPNsense 26.7: a port forward is the d_nat model ({source, destination}: network, port)."""
from __future__ import annotations


def _rows(api, path: str) -> list[dict]:
    return (api("GET", path) or {}).get("rows") or []


def _find(api, path: str, key: str, value: str) -> dict | None:
    return next((x for x in _rows(api, path) if x.get(key) == value), None)


def _alias(api, name: str) -> dict | None:
    return _find(api, "/firewall/alias/search_item", "name", name)


def _set_alias(api, a: dict | None, name: str, content: list[str], descr: str = "") -> None:
    body = {"alias": {"enabled": "1", "name": name, "type": "host", "content": "\n".join(content),
                      **({"description": descr[:200]} if descr or not a else {})}}
    api("POST", f"/firewall/alias/set_item/{a['uuid']}" if a else "/firewall/alias/add_item", body)
    api("POST", "/firewall/alias/reconfigure")


def do(api, b: dict) -> dict:
    op = b["op"]
    if op == "exists":
        found = {"alias": lambda: _alias(api, b["name"]),
                 "rule": lambda: _find(api, "/firewall/filter/search_rule", "description", b["name"]),
                 "nat": lambda: _find(api, "/firewall/d_nat/search_rule", "descr", b["name"])}[b["what"]]()
        return {"code": "200" if found else "404", "message": ""}
    if op == "put_alias":
        _set_alias(api, _alias(api, b["name"]), b["name"], list(b.get("addresses") or []), b.get("descr", ""))
    elif op == "drop_alias":
        a = _alias(api, b["name"])
        if not a:
            return {"code": "200", "message": "already gone"}
        api("POST", f"/firewall/alias/del_item/{a['uuid']}")
        api("POST", "/firewall/alias/reconfigure")
    elif op in ("alias_add", "alias_del"):
        a = _alias(api, b["name"])
        if not a:
            return {"code": "404", "message": f"no alias {b['name']}"}
        now = api.content(a["uuid"])
        if op == "alias_add" and b["ip"] not in now:
            now.append(b["ip"])
        elif op == "alias_del" and b["ip"] in now:
            now.remove(b["ip"])
        _set_alias(api, a, b["name"], now)
    elif op == "put_rule":
        r = _find(api, "/firewall/filter/search_rule", "description", b["descr"])
        proto = b.get("protocol") or "any"
        rule = {"enabled": "1", "action": b.get("action", "pass"), "quick": "1",
                "interface": ",".join(b.get("interfaces") or ["wan"]), "direction": "in", "ipprotocol": "inet",
                "protocol": proto, "source_net": b.get("source") or "any", "destination_net": b.get("destination") or "any",
                "destination_port": str(b["port"]).replace(":", "-") if b.get("port") and proto in ("tcp", "udp", "tcp/udp") else "",
                "log": "1" if b.get("log", True) else "0", "description": b["descr"]}
        api("POST", f"/firewall/filter/set_rule/{r['uuid']}" if r else "/firewall/filter/add_rule", {"rule": rule})
        api("POST", "/firewall/filter/apply")
    elif op == "drop_rule":
        r = _find(api, "/firewall/filter/search_rule", "description", b["descr"])
        if not r:
            return {"code": "200", "message": "already gone"}
        api("POST", f"/firewall/filter/del_rule/{r['uuid']}")
        api("POST", "/firewall/filter/apply")
    elif op == "put_nat":
        n = _find(api, "/firewall/d_nat/search_rule", "descr", b["descr"])
        rule = {"disabled": "0", "interface": "wan", "ipprotocol": "inet", "protocol": b.get("protocol") or "tcp",
                "source": {"network": b.get("source") or "any"},
                "destination": {"network": "wanip", "port": str(b["port"]).replace(":", "-")}, "target": b["target"],
                "local-port": str(b.get("local_port") or b["port"]).split(":")[0], "descr": b["descr"], "log": "1"}
        api("POST", f"/firewall/d_nat/set_rule/{n['uuid']}" if n else "/firewall/d_nat/add_rule", {"rule": rule})
        api("POST", "/firewall/d_nat/apply")
    elif op == "drop_nat":
        n = _find(api, "/firewall/d_nat/search_rule", "descr", b["descr"])
        if not n:
            return {"code": "200", "message": "already gone"}
        api("POST", f"/firewall/d_nat/del_rule/{n['uuid']}")
        api("POST", "/firewall/d_nat/apply")
    else:
        return {"code": "400", "message": f"unknown operation {op}"}
    return {"code": "200", "message": ""}
