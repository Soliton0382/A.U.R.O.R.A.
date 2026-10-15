# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The OPNsense dialect (ROADMAP 108, step 2): OPNsense's own REST API (docs.opnsense.org, «Using the API»),
<AURORA_FIREWALL_API_URL>/api/..., basic authentication with an API key as user and its secret as password (System →
Access → Users → API keys). Measured on OPNsense 26.7 in an aurora-lab VM.

The blocking group is a host alias and one block rule on the WAN, «quick», with the alias as source (the filter's
automation rules, evaluated before the interface rules). An address is a line of the alias's content, written in the
configuration and then «reconfigure»: alias_util/add alone changes only the filter's table of the moment, lost at the
next reload (measured). A blocked address's open connections are closed one by one, only those whose source or
destination is the address itself — kill_states' «filter» matches by substring, so 1.2.3.4 would also end
1.2.3.45's.

Like pfsense.py, what a plan, the audit and the network map ask in the first dialect's XML is refused with the
reason, never sent."""
from __future__ import annotations

import json
import re

import httpx

RULE = "Aurora: addresses the owner blocked"
# the official guides (sec_fwdocs), used while the owner has not pasted others: the documentation (its sitemap), the
# API reference's index (its pages under development/api/), the firewall's API page with the log's fields
DOCS = {"manual": "https://docs.opnsense.org/",
        "api": "https://docs.opnsense.org/development/api.html",
        "syslog": "https://docs.opnsense.org/development/api/core/firewall.html"}


def alias_name(group: str) -> str:
    """OPNsense: letters, digits and _, 32 at most, not starting with a digit."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", group).strip("_") or "Aurora_blocked"
    return ("A" + name if name[0].isdigit() else name)[:32]


def _op(op: str, **args) -> str:
    return json.dumps({"op": op, **args})


# ---- the call -------------------------------------------------------------------------------------------------------
class _API:
    def __init__(self, cfg):
        from ..sec_fwapi import base_url
        self.base = base_url(cfg) + "/api"
        self.auth = (str(cfg["AURORA_FIREWALL_API_USER"]), str(cfg["AURORA_FIREWALL_API_PASSWORD"]))
        self.verify = bool(cfg["AURORA_FIREWALL_VERIFY_TLS"])

    def __call__(self, method: str, path: str, body: dict | None = None) -> dict:
        from ..sec_fwapi import FirewallAPIError
        try:
            r = httpx.request(method, self.base + path, auth=self.auth, verify=self.verify, timeout=30,
                              **({"json": body} if body is not None else {}))
        except httpx.HTTPError as e:
            raise FirewallAPIError(f"the firewall does not answer: {e}") from None
        if r.status_code == 401:
            raise FirewallAPIError("the firewall refused the login (the API key and its secret)")
        if r.status_code == 403:
            raise FirewallAPIError("599 the API key's user has no privilege for this page")   # read_only() knows 599
        try:
            d = r.json()
        except ValueError:
            raise FirewallAPIError(f"HTTP {r.status_code}: not the API's answer: {r.text[:200]}") from None
        if r.status_code != 200 or (isinstance(d, dict) and d.get("result") == "failed"):
            raise FirewallAPIError(f"HTTP {r.status_code}: {json.dumps(d)[:200]}")
        return d

    def alias(self, name: str) -> dict | None:
        rows = self("GET", "/firewall/alias/search_item").get("rows") or []
        return next((a for a in rows if a.get("name") == name), None)

    def content(self, uuid: str) -> list[str]:
        a = self("GET", f"/firewall/alias/get_item/{uuid}").get("alias") or {}
        c = a.get("content")
        if isinstance(c, dict):                              # the form's shape: {value: {"value", "selected"}}
            return [k for k, v in c.items() if k and (not isinstance(v, dict) or v.get("selected"))]
        return [x for x in str(c or "").split("\n") if x]

    def rule(self, name: str) -> dict | None:
        rows = self("GET", "/firewall/filter/search_rule").get("rows") or []
        return next((r for r in rows if r.get("description") == RULE), None)


def request(cfg, body: str) -> str:
    """One operation of the core (one or a few REST calls); a JSON answer {"code", "message", …}."""
    from ..sec_fwapi import FirewallAPIError, _one_at_a_time
    try:
        b = json.loads(body)
    except ValueError:
        b = None
    if not isinstance(b, dict) or "op" not in b:
        raise FirewallAPIError("this request has no OPNsense form yet (plans, audit and network map read the XML "
                               "dialect's objects): only blocking and unblocking addresses work on OPNsense")
    api = _API(cfg)
    with _one_at_a_time(cfg):
        return json.dumps(_do(api, b))


def _do(api: _API, b: dict) -> dict:
    name = alias_name(b.get("group") or "")
    if b["op"] == "get_group":
        a = api.alias(name)
        return {"code": "200", "message": "", "group": name, "exists": bool(a)}
    if b["op"] == "add_group":
        made = []
        if not api.alias(name):
            api("POST", "/firewall/alias/add_item", {"alias": {"enabled": "1", "name": name, "type": "host",
                                                               "content": "", "description": RULE}})
            api("POST", "/firewall/alias/reconfigure")
            made.append("alias")
        if not api.rule(name):
            api("POST", "/firewall/filter/add_rule", {"rule": {
                "enabled": "1", "action": "block", "quick": "1", "interface": "wan", "direction": "in",
                "ipprotocol": "inet", "source_net": name, "destination_net": "any", "log": "1",
                "description": RULE}})
            api("POST", "/firewall/filter/apply")
            made.append("rule")
        return {"code": "200", "message": f"made: {', '.join(made)}" if made else "exists"}
    if b["op"] == "remove_host":                             # no object of its own: out of the alias is all
        return {"code": "200", "message": "nothing more to remove"}
    a = api.alias(name)
    if a is None:
        return {"code": "404", "message": f"no alias {name}"}
    now, ip = api.content(a["uuid"]), b.get("ip", "")
    if b["op"] == "add_host":
        if ip in now:
            return {"code": "200", "message": "the address is in the group already"}
        now.append(ip)
    elif b["op"] == "ungroup_host":
        if ip not in now:
            return {"code": "200", "message": "the address was not in the group"}
        now.remove(ip)
    else:
        return {"code": "400", "message": f"unknown operation {b['op']}"}
    api("POST", f"/firewall/alias/set_item/{a['uuid']}", {"alias": {"content": "\n".join(now)}})
    api("POST", "/firewall/alias/reconfigure")
    if b["op"] == "add_host":                                # a connection open before the block lives on as a state
        return {"code": "200", "message": f"{_end_states(api, ip)} open connections closed"}
    return {"code": "200", "message": ""}


def _end_states(api: _API, ip: str) -> int:
    rows = api("POST", "/diagnostics/firewall/query_states", {"searchPhrase": ip, "rowCount": 500}).get("rows") or []
    n = 0
    for r in rows:
        if ip in (r.get("src_addr"), r.get("dst_addr")) and "/" in str(r.get("id", "")):
            api("POST", f"/diagnostics/firewall/del_state/{r['id']}")
            n += 1
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


READ_ONLY_HINT = (" — la chiave API di Aurora su OPNsense non ha i privilegi: in System → Access → Users dai al suo "
                  "utente le pagine «Firewall: Alias», «Firewall: Automation» e «Diagnostics: Show States»; poi riprova")


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
