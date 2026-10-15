# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The pfSense dialect (ROADMAP 108, step 2): the REST API of the pfSense-pkg-RESTAPI package (v2,
<AURORA_FIREWALL_API_URL>/api/v2/..., basic authentication), measured on pfSense CE 2.9.0 with the package 2.10.2 in
an aurora-lab VM. pfSense has no API of its own: the owner installs the package (System → Package Manager, or
`pkg-static add` of its release for the firewall's version) and gives Aurora's user the privileges on aliases, rules
and apply.

The blocking group is a host alias (pfSense allows letters, digits and _ in a name, 31 at most: the group's name is
made so) and one floating «quick» block rule on the WAN with the alias as source, made with the alias: an address in
the alias is dropped before any other rule. An address has no object of its own: «add a host» is a line in the alias
(its description in the line's detail), «remove a host» nothing more than taking it out.

What the core asks of the other dialect for a plan, the audit and the network map (objects written as XML: x, set_,
rule, dnat, get_rules, harden…) has no pfSense form yet: a request of that kind is refused with a FirewallAPIError
that says so, never sent."""
from __future__ import annotations

import json
import re

import httpx

RULE = "Aurora: addresses the owner blocked"
# the official guides (sec_fwdocs), used while the owner has not pasted others: the manual (its sitemap), the REST
# API package's OpenAPI for this release, the filter log's format
DOCS = {"manual": "https://docs.netgate.com/pfsense/en/latest/",
        "api": "https://github.com/pfrest/pfSense-pkg-RESTAPI/releases/download/v2.10.2/openapi.json",
        "syslog": "https://docs.netgate.com/pfsense/en/latest/monitoring/logs/raw-filter-format.html"}


def alias_name(group: str) -> str:
    return (re.sub(r"[^A-Za-z0-9_]", "_", group).strip("_") or "Aurora_blocked")[:31]


def _op(op: str, **args) -> str:
    return json.dumps({"op": op, **args})


# ---- the call -------------------------------------------------------------------------------------------------------
class _API:
    def __init__(self, cfg):
        from ..sec_fwapi import base_url
        self.base = base_url(cfg) + "/api/v2"
        self.auth = (str(cfg["AURORA_FIREWALL_API_USER"]), str(cfg["AURORA_FIREWALL_API_PASSWORD"]))
        self.verify = bool(cfg["AURORA_FIREWALL_VERIFY_TLS"])

    def __call__(self, method: str, path: str, **kw) -> dict:
        from ..sec_fwapi import FirewallAPIError
        try:
            r = httpx.request(method, self.base + path, auth=self.auth, verify=self.verify, timeout=30, **kw)
        except httpx.HTTPError as e:
            raise FirewallAPIError(f"the firewall does not answer: {e}") from None
        if r.status_code == 401:
            raise FirewallAPIError("the firewall refused the login (user, password, or the REST API package missing)")
        try:
            d = r.json()
        except ValueError:
            raise FirewallAPIError(f"HTTP {r.status_code}: not the REST API's answer: {r.text[:200]}") from None
        if r.status_code == 403:
            raise FirewallAPIError(f"599 {d.get('message') or 'no privilege'}")      # read_only() knows 599
        if r.status_code != 200:
            raise FirewallAPIError(f"HTTP {r.status_code}: {d.get('message') or d.get('response_id')}")
        return d.get("data")

    def alias(self, name: str) -> dict | None:
        return next((a for a in self("GET", "/firewall/aliases") or [] if a.get("name") == name), None)

    def rule(self, name: str) -> dict | None:
        return next((r for r in self("GET", "/firewall/rules") or []
                     if r.get("descr") == RULE and r.get("source") == name), None)

    def apply(self):
        self("POST", "/firewall/apply")


def request(cfg, body: str) -> str:
    """One operation of the core (one or a few REST calls); a JSON answer {"code", "message", …}."""
    from ..sec_fwapi import FirewallAPIError, _one_at_a_time
    try:
        b = json.loads(body)
    except ValueError:
        b = None
    if not isinstance(b, dict) or "op" not in b:
        raise FirewallAPIError("this request has no pfSense form yet (plans, audit and network map read the XML "
                               "dialect's objects): only blocking and unblocking addresses work on pfSense")
    api = _API(cfg)
    with _one_at_a_time(cfg):
        return json.dumps(_do(api, b))


def _do(api: _API, b: dict) -> dict:
    name = alias_name(b.get("group") or b.get("name") or "")
    if b["op"] == "get_group":
        a = api.alias(name)
        return {"code": "200", "message": "", "group": name, "exists": bool(a), "addresses": (a or {}).get("address", [])}
    if b["op"] == "add_group":
        made = []
        if not api.alias(name):
            api("POST", "/firewall/alias", json={"name": name, "type": "host", "address": [], "detail": [],
                                                 "descr": "Aurora: addresses the owner blocked"})
            made.append("alias")
        if not api.rule(name):
            api("POST", "/firewall/rule", json={"type": "block", "interface": ["wan"], "ipprotocol": "inet",
                                                "protocol": None, "source": name, "destination": "any",
                                                "descr": RULE, "floating": True, "quick": True, "direction": "any",
                                                "log": True})
            made.append("rule")
        if made:
            api.apply()
        return {"code": "200", "message": f"made: {', '.join(made)}" if made else "exists"}
    if b["op"] == "remove_host":                           # no object of its own: out of the alias is all
        return {"code": "200", "message": "nothing more to remove"}
    a = api.alias(name)
    if a is None:
        return {"code": "404", "message": f"no alias {name}"}
    address, detail = list(a.get("address") or []), list(a.get("detail") or [])
    detail += [""] * (len(address) - len(detail))
    ip = b.get("ip", "")
    if b["op"] == "add_host":
        if ip in address:
            return {"code": "200", "message": "the address is in the group already"}
        address.append(ip)
        detail.append(f"{b.get('host', '')}: {b.get('desc', '')}"[:200])
    elif b["op"] == "ungroup_host":
        if ip not in address:
            return {"code": "200", "message": "the address was not in the group"}
        i = address.index(ip)
        del address[i], detail[i]
    else:
        return {"code": "400", "message": f"unknown operation {b['op']}"}
    api("PATCH", "/firewall/alias", json={"id": a["id"], "address": address, "detail": detail})
    api.apply()                                          # in the filter's table 0.4-0.5 s later (measured, 3 times)
    if b["op"] == "add_host":                            # a connection open before the block lives on as a state
        return {"code": "200", "message": f"{_end_states(api, ip)} open connections closed"}
    return {"code": "200", "message": ""}


def _end_states(api: _API, ip: str) -> int:
    """The states of the address, from it or to it; «ip:» exact, so 1.2.3.4 never ends 1.2.3.45's (measured on the
    lab: the filtered delete took 1 state of 18)."""
    n = 0
    for side in ("source", "destination"):
        n += len(api("DELETE", f"/firewall/states?{side}__startswith={ip}:") or [])
    return n


def status(text: str, entity: str) -> tuple[str, str]:
    try:
        d = json.loads(text)
    except ValueError:
        return "", text[:200]
    return str(d.get("code", "")), str(d.get("message", ""))


def step_status(text: str, entity: str) -> tuple[str, str]:
    return status(text, entity)


def ok_codes(op: str) -> tuple[str, ...]:
    return ("200",)


READ_ONLY_HINT = (" — l'utente API di Aurora su pfSense non ha i privilegi di scrittura: in System → User Manager "
                  "dagli quelli del pacchetto REST API su alias, regole del firewall e «apply»; poi riprova")


def read_only(code: str, msg: str) -> bool:
    return str(code) == "599" or "privilege" in msg.lower()


def has_group(text: str, name: str) -> bool:
    try:
        return bool(json.loads(text).get("exists"))
    except (ValueError, AttributeError):
        return False


# ---- the blocking group ---------------------------------------------------------------------------------------------
def get_group(name: str) -> str:
    return _op("get_group", group=name)


def add_group(name: str) -> str:
    return _op("add_group", group=name)


def add_host(name: str, ip: str, desc: str, group: str) -> str:
    return _op("add_host", host=name, ip=ip, desc=desc, group=group)


def ungroup_host(name: str, ip: str, group: str = "") -> str:
    return _op("ungroup_host", host=name, ip=ip, group=group)


def remove_host(name: str) -> str:
    return _op("remove_host", host=name)
