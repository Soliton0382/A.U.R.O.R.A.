# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The firewalls in one neutral form (ROADMAP N8): the audit, the map and the plans for the dialects other than the
first, on answers shaped like the lab firewalls' (pfSense CE 2.9.0 with its REST API package, OPNsense 26.7); the
addresses are documentation ones."""
import json

import pytest

from aurora import sec_audit, sec_fwmodel, sec_fwops, sec_fwplan_ops
from aurora.fw_drivers import opnsense_read, opnsense_write, pfsense_read, pfsense_write


class FakeAPI:
    """GET answers by path; every other call recorded."""

    def __init__(self, gets: dict):
        self.gets, self.calls = gets, []

    def __call__(self, method, path, body=None, **kw):
        if method == "GET":
            return self.gets.get(path.split("?")[0])
        self.calls.append((method, path, body or kw.get("json") or kw.get("params")))
        return {}

    def apply(self):
        self.calls.append(("POST", "/firewall/apply", None))

    def content(self, uuid):
        return ["192.0.2.9"]


PF = {
    "/interfaces": [{"id": "wan", "descr": "WAN"}, {"id": "lan", "descr": "LAN"}],
    "/status/interfaces": [{"name": "wan", "descr": "WAN", "hwif": "vtnet0", "status": "up", "ipaddr": "198.51.100.2", "subnet": "255.255.255.0"},
                           {"name": "lan", "descr": "LAN", "hwif": "vtnet1", "status": "up", "ipaddr": "192.0.2.1", "subnet": "255.255.255.0"}],
    "/firewall/rules": [
        {"id": 1, "type": "pass", "interface": ["wan"], "source": "any", "destination": "192.0.2.10", "destination_port": "443",
         "protocol": "tcp", "descr": "web", "log": False},
        {"id": 2, "type": "pass", "interface": ["wan"], "source": "any", "destination": "wan:ip", "destination_port": "443",
         "protocol": "tcp", "descr": "gui from outside", "log": True},
        {"id": 0, "type": "block", "interface": ["wan"], "source": "Aurora_blocked", "destination": "any", "floating": True,
         "descr": "Aurora: addresses the owner blocked", "log": True}],
    "/firewall/nat/port_forwards": [{"descr": "web in", "protocol": "tcp", "destination_port": "443", "target": "192.0.2.10",
                                     "source": "any", "interface": "wan"}],
    "/system/webgui/settings": {"protocol": "https", "port": "443"},
    "/system/packages": [{"name": "pfSense-pkg-System_Patches"}],
    "/status/logs/settings": {"enableremotelogging": True, "remoteserver": "192.0.2.50:514", "filter": True},
    "/firewall/aliases": [{"id": 0, "name": "Aurora_blocked", "type": "host", "descr": "Aurora: addresses the owner blocked",
                           "address": ["203.0.113.5"], "detail": [""]},
                          {"id": 1, "name": "Servers", "type": "host", "descr": "", "address": ["192.0.2.10"], "detail": ["NAS"]}],
    "/services/dhcp_servers": [{"interface": "lan", "enable": True, "range_from": "192.0.2.100", "range_to": "192.0.2.199",
                                "staticmap": [{"mac": "02:00:00:00:00:01", "ipaddr": "192.0.2.20", "hostname": "printer"}]}],
    "/routing/static_routes": [], "/diagnostics/arp_table": [{"ip_address": "192.0.2.30", "mac_address": "02:00:00:00:00:02",
                                                              "hostname": "?", "interface": "LAN"}],
    "/status/dhcp_server/leases": [{"ip": "192.0.2.30", "mac": "02:00:00:00:00:02", "hostname": "phone"}],
}


@pytest.fixture
def pf(monkeypatch):
    api = FakeAPI(PF)
    from aurora.fw_drivers import pfsense
    monkeypatch.setattr(pfsense, "_API", lambda cfg: api)
    return api


def test_pfsense_read_into_the_neutral_form_and_judged(pf, monkeypatch):
    from aurora import sec_fwapi
    monkeypatch.setattr(sec_fwapi, "_own_addresses", lambda: {"192.0.2.50"})
    m = pfsense_read.read_model(None, "Aurora blocked")
    assert m["rules"][0]["name"].startswith("Aurora:")                     # floating first: evaluated first
    web = next(r for r in m["rules"] if r["name"] == "web")
    assert web["src_zones"] == ["WAN"] and web["ports"] == ["TCP 443"] and web["ips"] is None and not web["to_self"]
    assert m["wan_admin"] == ["HTTPS"] and m["threat"]["state"] == "off" and m["block_object"] == "Aurora_blocked"
    a = sec_audit.run(type("C", (), {"__getitem__": lambda s, k: "Aurora blocked"})(), m)
    ids = {f["id"]: f for f in a["findings"]}
    assert ids["admin_wan"]["severity"] == "high" and ids["ids"]["severity"] == "high"
    assert ids["exposed:web"]["severity"] == "high"                       # no engine, open to everyone
    assert "blocklist" not in ids and "syslog" not in ids                   # the blocks apply; the log reaches Aurora


def test_pfsense_network_with_what_it_sees_now(pf):
    n = pfsense_read.read_network(None)
    assert {h["name"] for h in n["hosts"]} == {"aurora-block-203.0.113.5", "NAS"}
    assert n["interfaces"][1] == {"id": "lan", "name": "LAN", "hardware": "vtnet1", "ip": "192.0.2.1",
                                  "netmask": "255.255.255.0", "zone": "LAN", "status": "up"}
    assert n["dhcp"][0]["static"] == [{"host": "printer", "mac": "02:00:00:00:00:01", "ip": "192.0.2.20"}]
    assert n["seen"] == [{"ip": "192.0.2.30", "mac": "02:00:00:00:00:02", "host": "phone", "interface": "LAN"}]


OPN = {
    "/interfaces/overview/interfaces_info": {"rows": [
        {"identifier": "wan", "description": "WAN", "device": "vtnet0", "addr4": "198.51.100.3/24", "status": "up"},
        {"identifier": "lan", "description": "LAN", "device": "vtnet1", "addr4": "192.0.2.1/24", "status": "up"}]},
    "/firewall/filter/search_rule": {"rows": [
        {"sort_order": "000001.1", "enabled": "1", "action": "block", "interface": None, "source_net": "sshlockout",
         "destination_net": "(self)", "destination_port": "22", "protocol": "tcp", "log": True, "description": "sshlockout",
         "is_automatic": True},
        {"sort_order": "400000.1", "enabled": "1", "action": "block", "interface": "wan", "%interface": "WAN",
         "source_net": "Aurora_blocked", "destination_net": "any", "log": "1", "description": "Aurora: addresses the owner blocked"}]},
    "/firewall/d_nat/search_rule": {"rows": [{"uuid": "lockout_1", "is_automatic": True, "descr": "Anti-Lockout Rule"}]},
    "/ids/settings/get": {"ids": {"general": {"enabled": "1", "mode": {"pcap": {"selected": 1}, "netmap": {"selected": 0}}}}},
    "/syslog/settings/search_destinations": {"rows": []},
}


def test_opnsense_read_its_engine_its_lockout_its_order(monkeypatch):
    api = FakeAPI(OPN)
    from aurora.fw_drivers import opnsense
    monkeypatch.setattr(opnsense, "_API", lambda cfg: api)
    m = opnsense_read.read_model(None, "Aurora blocked")
    assert m["rules"][0]["system"] and m["rules"][1]["src_zones"] == ["WAN"]
    assert m["threat"] == {"what": "Suricata (Intrusion Detection)", "state": "log"} and m["login"]["lockout"] is True
    assert m["nat"] == []                                                   # the anti-lockout redirect is the firewall's
    f = {x["id"]: x for x in sec_audit.threat(m) + sec_audit.syslog(m, {"192.0.2.50"})}
    assert f["ids"]["severity"] == "medium" and f["syslog"]["severity"] == "high"


NET = {"interfaces": [{"id": "wan", "name": "WAN", "ip": "10.0.0.2", "netmask": "24", "zone": "WAN"},
                      {"id": "lan", "name": "LAN", "ip": "192.0.2.1", "netmask": "24", "zone": "LAN"},
                      {"id": "opt1", "name": "WIFI", "ip": "198.51.100.1", "netmask": "24", "zone": "WIFI"}],
       "groups": [], "hosts": []}


def test_a_publication_is_a_forward_and_its_rule_per_port_with_the_origin_as_an_alias():
    p = sec_fwops.plan_publish(None, "nas", "192.0.2.10", [("TCP", "443")], ["203.0.113.7"], NET)
    ops = [json.loads(s["xml"])["op"] for s in p["steps"]]
    assert ops == ["put_alias", "put_nat", "put_rule"] and all(s["undo"] for s in p["steps"])
    rule = json.loads(p["steps"][2]["xml"])
    assert rule["destination"] == "192.0.2.10" and rule["source"] == "Aurora_src_nas" and rule["log"]
    assert any("dietro un altro router" in n for n in p["notes"])          # a private WAN: a router in front
    with pytest.raises(sec_fwops.OpsError):
        sec_fwops.plan_publish(None, "x", "10.0.0.9", [("TCP", "80")], [], NET)   # on the WAN's own network


def test_the_quarantine_rule_covers_every_inside_interface_and_is_made_once():
    q = sec_fwops.plan_quarantine(None, "192.0.2.77", "test", NET, {"rules": []})
    rule = json.loads(q["steps"][1]["xml"])
    assert rule["interfaces"] == ["lan", "opt1"] and rule["action"] == "block" and rule["floating"]
    again = sec_fwops.plan_quarantine(None, "192.0.2.78", "test", {**NET, "groups": [{"name": "Aurora_Quarantine", "hosts": []}]},
                                      {"rules": [{"name": "Aurora-Quarantine"}]})
    assert [json.loads(s["xml"])["op"] for s in again["steps"]] == ["alias_add"]


def test_a_plan_in_words_is_checked_step_by_step(monkeypatch):
    from aurora import sec_fwapi
    monkeypatch.setattr(sec_fwapi, "_own_addresses", lambda: {"192.0.2.5"})
    fw = {"AURORA_FIREWALL_API_URL": "https://192.0.2.1"}
    model = {"rules": [{"name": "owner's rule"}], "nat": []}
    net = {**NET, "groups": [{"name": "Servers", "hosts": []}]}
    good = [{"op": "put_alias", "name": "Aurora_Bad", "addresses": ["203.0.113.0/24"]},
            {"op": "put_rule", "descr": "Aurora-block bad", "floating": True, "interfaces": ["wan"], "action": "block",
             "source": "Aurora_Bad", "destination": "any", "protocol": "any"}]
    steps, problems = sec_fwplan_ops.check(fw, good, model, net)
    assert problems == [] and [s["entity"] for s in steps] == ["alias", "rule"]
    assert json.loads(steps[1]["undo"]) == {"op": "drop_rule", "descr": "Aurora-block bad"}
    bad = [{"op": "drop_rule", "descr": "owner's rule"},                                     # not Aurora's
           {"op": "put_rule", "descr": "Aurora-gui", "interfaces": ["wan"], "action": "pass", "destination": "wan:ip"},
           {"op": "put_rule", "descr": "Aurora-me", "floating": True, "action": "block", "source": "192.0.2.5"},
           {"op": "put_rule", "descr": "Aurora-x", "interfaces": ["dmz"], "action": "pass"},
           {"op": "set_admin", "descr": "Aurora-y"}]
    _, problems = sec_fwplan_ops.check(fw, bad, model, net)
    text = " ".join(problems)
    for said in ("Aurora's objects are described", "reach the firewall itself", "never block this machine",
                 "interfaces ['dmz']", "not an operation"):
        assert said in text


def test_the_writes_find_objects_by_name_never_by_a_kept_id():
    api = FakeAPI({"/firewall/aliases": [{"id": 3, "name": "Aurora_src_nas", "address": ["203.0.113.7"]}],
                   "/firewall/rules": [{"id": 7, "descr": "Aurora-nas TCP 443"}], "/firewall/nat/port_forwards": []})
    assert pfsense_write.do(api, {"op": "drop_rule", "descr": "Aurora-nas TCP 443"})["code"] == "200"
    assert ("DELETE", "/firewall/rule", {"id": 7}) in api.calls and api.calls[-1][1] == "/firewall/apply"
    assert pfsense_write.do(api, {"op": "drop_nat", "descr": "Aurora-nas TCP 443"})["message"] == "already gone"
    pfsense_write.do(api, {"op": "put_alias", "name": "Aurora_src_nas", "addresses": ["203.0.113.8"]})
    assert ("PATCH", "/firewall/alias") == api.calls[-2][:2] and api.calls[-2][2]["id"] == 3
    o = FakeAPI({"/firewall/filter/search_rule": {"rows": []}})
    opnsense_write.do(o, {"op": "put_rule", "descr": "Aurora-pb", "interfaces": ["wan"], "action": "block", "source": "203.0.113.9",
                          "port": "8000:8010", "protocol": "tcp"})
    assert o.calls[0][1] == "/firewall/filter/add_rule" and o.calls[0][2]["rule"]["destination_port"] == "8000-8010"


def test_the_first_dialect_reads_into_the_same_form():
    conf = {"FirewallRule": [{"Name": "In", "Status": "Enable", "NetworkPolicy": {
        "Action": "Accept", "SourceZones": {"Zone": "WAN"}, "DestinationZones": {"Zone": "LAN"}, "Services": {"Service": "Web"},
        "IntrusionPrevention": "None", "LogTraffic": "Disable"}}],
        "Services": [{"Name": "Web", "ServiceDetails": {"ServiceDetail": {"Protocol": "TCP", "DestinationPort": "443"}}}],
        "ATP": [{"ThreatProtectionStatus": "Enable", "Policy": "Log Only"}], "_errors": {}}
    m = sec_fwmodel.of_sophos(conf, "Blocked")
    assert m["rules"][0]["ports"] == ["TCP 443"] and m["rules"][0]["ips"] == "None" and m["threat"]["state"] == "log"
    assert sec_audit.exposed(conf)[0]["severity"] == "high" and sec_audit.threat(conf)[0]["id"] == "atp"
