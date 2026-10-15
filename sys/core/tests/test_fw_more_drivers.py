# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""ROADMAP 108 step 2 (N8): the second and third firewall drivers (pfSense's REST API package, OPNsense's own API)
and their guides. The answers below are the shapes the lab's pfSense CE 2.9.0 (package 2.10.2) and OPNsense 26.7 gave
on 16 Oct; the core's block, test and unblock run on them as on the first driver."""
import json

import pytest

from aurora import sec_fwapi
from aurora.fw_drivers import pfsense

CFG = {"AURORA_FIREWALL_API_KIND": "pfsense", "AURORA_FIREWALL_API_URL": "https://192.0.2.1",
       "AURORA_FIREWALL_API_USER": "aurora", "AURORA_FIREWALL_API_PASSWORD": "x", "AURORA_FIREWALL_VERIFY_TLS": False,
       "AURORA_FIREWALL_BLOCK_GROUP": "Aurora-Block-List"}


class Lab:
    """aliases, rules and states as the REST API keeps them; every call recorded."""

    def __init__(self):
        self.aliases, self.rules, self.calls = [], [], []
        self.states = [{"source": "203.0.113.9:4444", "destination": "192.0.2.1:443"},
                       {"source": "203.0.113.90:1", "destination": "192.0.2.1:22"}]

    def __call__(self, api, method, path, **kw):
        self.calls.append((method, path.split("?")[0]))
        body = kw.get("json") or {}
        if (method, path) == ("GET", "/firewall/aliases"):
            return self.aliases
        if (method, path) == ("GET", "/firewall/rules"):
            return self.rules
        if (method, path) == ("POST", "/firewall/alias"):
            self.aliases.append({"id": len(self.aliases), **body})
            return self.aliases[-1]
        if (method, path) == ("POST", "/firewall/rule"):
            self.rules.append(body)
            return body
        if (method, path) == ("PATCH", "/firewall/alias"):
            self.aliases[body["id"]].update(body)
            return self.aliases[body["id"]]
        if path.startswith("/firewall/states?"):
            side, prefix = path.split("?")[1].split("__startswith=")
            gone = [s for s in self.states if s[side].startswith(prefix)]
            self.states = [s for s in self.states if s not in gone]
            return gone
        if path == "/firewall/apply":
            return {"applied": True}
        raise AssertionError(path)


@pytest.fixture
def lab(monkeypatch, tmp_path):
    lab = Lab()
    monkeypatch.setattr(pfsense._API, "__call__", lambda self, m, p, **kw: lab(self, m, p, **kw))
    monkeypatch.setattr(sec_fwapi, "_one_at_a_time", lambda cfg: __import__("contextlib").nullcontext())
    monkeypatch.setattr(sec_fwapi, "_own_addresses", lambda: set())
    return lab


def test_a_block_makes_the_alias_and_its_rule_once_and_ends_the_address_open_connections(lab):
    assert sec_fwapi.test(CFG) == {"ok": True, "group_exists": False}
    out = sec_fwapi.block(CFG, "203.0.113.9", "scan of port 22")
    assert out["status"] == "200" and "1 open connections closed" in out["message"]
    alias = lab.aliases[0]
    assert alias["name"] == "Aurora_Block_List" and alias["address"] == ["203.0.113.9"]
    assert lab.rules == [dict(lab.rules[0], type="block", source="Aurora_Block_List", floating=True, quick=True)]
    assert [s["source"] for s in lab.states] == ["203.0.113.90:1"]         # «ip:» exact: .90 keeps its connection
    sec_fwapi.block(CFG, "203.0.113.10", "")
    assert len(lab.rules) == 1 and len(lab.aliases) == 1 and alias["address"] == ["203.0.113.9", "203.0.113.10"]
    assert sec_fwapi.block(CFG, "203.0.113.9", "")["message"] == "the address is in the group already"
    assert sec_fwapi.test(CFG)["group_exists"]


def test_an_unblock_takes_the_address_out_and_twice_is_no_error(lab):
    sec_fwapi.block(CFG, "203.0.113.9", "x")
    sec_fwapi.block(CFG, "203.0.113.10", "y")
    assert sec_fwapi.unblock(CFG, "203.0.113.9")["status"] == "200"
    assert lab.aliases[0]["address"] == ["203.0.113.10"] and lab.aliases[0]["detail"] == ["aurora-block-203.0.113.10: y"]
    assert sec_fwapi.unblock(CFG, "203.0.113.9")["status"] == "200"


def test_what_has_no_pfsense_form_is_refused_never_sent(lab):
    with pytest.raises(sec_fwapi.FirewallAPIError, match="first dialect.s XML: on pfSense"):
        sec_fwapi.request(CFG, "<Get><FirewallRule/></Get>")
    assert lab.calls == []


def test_the_group_name_is_one_pfsense_takes():
    assert pfsense.alias_name("Aurora-Block-List") == "Aurora_Block_List"
    assert len(pfsense.alias_name("x" * 40)) == 31 and pfsense.alias_name("--") == "Aurora_blocked"
    assert json.loads(pfsense.ungroup_host("h", "203.0.113.9", "G"))["group"] == "G"


class OpnLab:
    """OPNsense's API as the lab's 26.7 answered: aliases with uuid and content, automation rules, states."""

    def __init__(self):
        self.aliases, self.rules, self.dropped = {}, [], []
        self.states = [{"id": "aa/1", "src_addr": "203.0.113.9", "dst_addr": "192.0.2.1"},
                       {"id": "bb/1", "src_addr": "203.0.113.90", "dst_addr": "192.0.2.1"}]

    def __call__(self, api, method, path, body=None):
        if path == "/firewall/alias/search_item":
            return {"rows": [{"uuid": u, **a} for u, a in self.aliases.items()]}
        if path == "/firewall/alias/add_item":
            self.aliases[f"u{len(self.aliases)}"] = dict(body["alias"])
            return {"result": "saved"}
        if path.startswith("/firewall/alias/get_item/"):
            return {"alias": self.aliases[path.rsplit("/", 1)[1]]}
        if path.startswith("/firewall/alias/set_item/"):
            self.aliases[path.rsplit("/", 1)[1]].update(body["alias"])
            return {"result": "saved"}
        if path == "/firewall/filter/search_rule":
            return {"rows": self.rules}
        if path == "/firewall/filter/add_rule":
            self.rules.append(body["rule"])
            return {"result": "saved"}
        if path == "/diagnostics/firewall/query_states":       # a substring search, as the real one
            return {"rows": [s for s in self.states if body["searchPhrase"] in s["src_addr"] + s["dst_addr"]]}
        if path.startswith("/diagnostics/firewall/del_state/"):
            self.dropped.append(path.split("del_state/")[1])
            return {"result": "dropped"}
        if path in ("/firewall/alias/reconfigure", "/firewall/filter/apply"):
            return {"status": "ok"}
        raise AssertionError(path)


def test_opnsense_blocks_in_the_configuration_and_ends_only_the_address_own_connections(monkeypatch):
    from aurora.fw_drivers import opnsense
    lab = OpnLab()
    monkeypatch.setattr(opnsense._API, "__call__", lambda self, m, p, body=None: lab(self, m, p, body))
    monkeypatch.setattr(sec_fwapi, "_one_at_a_time", lambda cfg: __import__("contextlib").nullcontext())
    monkeypatch.setattr(sec_fwapi, "_own_addresses", lambda: set())
    cfg = {**CFG, "AURORA_FIREWALL_API_KIND": "opnsense"}
    assert sec_fwapi.block(cfg, "203.0.113.9", "scan")["message"] == "1 open connections closed"
    assert lab.dropped == ["aa/1"]                                         # 203.0.113.90 matched the search, not the ip
    sec_fwapi.block(cfg, "203.0.113.10", "")
    assert lab.aliases["u0"]["content"] == "203.0.113.9\n203.0.113.10" and len(lab.rules) == 1
    assert lab.rules[0]["source_net"] == "Aurora_Block_List" and lab.rules[0]["quick"] == "1"
    sec_fwapi.unblock(cfg, "203.0.113.9")
    assert lab.aliases["u0"]["content"] == "203.0.113.10"
    with pytest.raises(sec_fwapi.FirewallAPIError, match="first dialect.s XML: on OPNsense"):
        sec_fwapi.request(cfg, "<Get><IPHost/></Get>")
    assert opnsense.alias_name("1-blocked") == "A1_blocked"


def test_each_firewall_has_its_own_guides_and_a_pasted_link_wins(cfg):
    from aurora import sec_fwdocs
    sophos_api = cfg["AURORA_FIREWALL_API_DOC_URL"]
    cfg.values["AURORA_FIREWALL_API_KIND"] = "opnsense"
    assert sec_fwdocs.url(cfg, "api") == "https://docs.opnsense.org/development/api.html"
    assert sec_fwdocs.path(cfg).name == "fwdocs-opnsense.sqlite"
    cfg.values["AURORA_FIREWALL_API_DOC_URL"] = "https://example.org/my-own-copy.html"
    assert sec_fwdocs.url(cfg, "api") == "https://example.org/my-own-copy.html"
    cfg.values.update(AURORA_FIREWALL_API_KIND="sophos", AURORA_FIREWALL_API_DOC_URL=sophos_api)
    assert sec_fwdocs.url(cfg, "api") == sophos_api and sec_fwdocs.path(cfg).name == "fwdocs.sqlite"


def test_an_openapi_reference_is_a_passage_per_operation_and_its_body_the_sample(cfg):
    from aurora import sec_fwdocs
    spec = {"info": {"title": "REST"}, "components": {"schemas": {"Alias": {"properties": {
        "name": {"type": "string"}, "address": {"type": "array"}}}}},
        "paths": {"/api/v2/firewall/alias": {"post": {"summary": "Create an alias", "requestBody": {"content": {
            "application/json": {"schema": {"allOf": [{"$ref": "#/components/schemas/Alias"}]}}}}}}}}
    cfg.values["AURORA_FIREWALL_API_KIND"] = "pfsense"
    con = sec_fwdocs._db(cfg)
    assert sec_fwdocs.add_openapi(con, "https://x/openapi.json", json.dumps(spec)) == 1
    con.commit()
    con.close()
    assert sec_fwdocs.search(cfg, "create alias")[0]["title"] == "POST /api/v2/firewall/alias"
    assert json.loads(sec_fwdocs.sample(cfg, "alias")[0]["xml"]) == {"name": "<string>", "address": "<array>"}
