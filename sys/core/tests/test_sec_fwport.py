# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""ROADMAP 103 steps 2 and 3: an address blocked on a port only (sec_fwport), the author behind Cloudflare blocked at
Cloudflare (net_cfwaf) — both refused where the block would hit the wrong people, both lifted by themselves."""
import json

import httpx
import pytest

from aurora import net_cfwaf, net_cloudflare, sec_fwport, sec_fwwrite, sec_intel

CF_NODE, SCANNER = "172.70.216.176", "45.132.10.20"


@pytest.fixture
def shared(monkeypatch):
    monkeypatch.setattr(sec_intel, "shared", lambda c, ip: "Cloudflare" if ip.startswith("172.70.") else "")


def test_port_block_is_a_drop_rule_from_wan_on_those_ports_only(cfg, shared):
    p = sec_fwport.plan_port_block(cfg, CF_NODE, "22/tcp", "brute force on ssh", 6, conf={})
    assert p["kind"] == "portblock" and p["hours"] == 6
    entities = [s["entity"] for s in p["steps"]]
    assert entities == ["IPHost", "Services", "FirewallRule"]
    rule = p["steps"][2]["xml"]
    assert "<Action>Drop</Action>" in rule and "<Zone>WAN</Zone>" in rule and "<Position>Top</Position>" in rule
    assert all(s["name"].lower().startswith("aurora-") and s["undo"] for s in p["steps"])   # its own objects, undoable
    assert any("Cloudflare" in n for n in p["notes"])


def test_a_cloudflare_node_on_a_proxied_port_is_refused(cfg, shared):
    for ports in ("80", "443/tcp", "22,8443"):
        with pytest.raises(sec_fwwrite.WriteError, match="cloudflare_block"):
            sec_fwport.plan_port_block(cfg, CF_NODE, ports, "x", conf={})
    assert sec_fwport.plan_port_block(cfg, SCANNER, "80", "x", conf={})["steps"]      # not shared: any port
    with pytest.raises(sec_fwwrite.WriteError):
        sec_fwport.plan_port_block(cfg, "192.168.1.50", "22", "x", conf={})          # the house: quarantine instead
    with pytest.raises(sec_fwwrite.WriteError, match="durata"):
        sec_fwport.plan_port_block(cfg, SCANNER, "22", "x", hours=24 * 31, conf={})


def test_due_reverts_only_the_expired_port_blocks(cfg, monkeypatch):
    now = 1_760_000_000
    history = [{"id": "a", "kind": "portblock", "status": "applied", "applied": now - 7 * 3600, "hours": 6, "title": "A"},
               {"id": "b", "kind": "portblock", "status": "applied", "applied": now - 3600, "hours": 6, "title": "B"},
               {"id": "c", "kind": "quarantine", "status": "applied", "applied": 0, "title": "C"}]
    monkeypatch.setattr(sec_fwwrite, "history", lambda c: history)
    reverted = []
    monkeypatch.setattr(sec_fwwrite, "revert", lambda c, i: reverted.append(i) or {"status": "reverted"})
    assert sec_fwport.due(cfg, now) == ["A"] and reverted == ["a"]


class FakeCloudflare:
    def __init__(self, allowed=True):
        self.allowed, self.rules = allowed, {}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p, m = req.url.path, req.method
        ok = lambda r: httpx.Response(200, json={"success": True, "errors": [], "result": r})      # noqa: E731
        if not self.allowed and "graphql" not in p:
            return httpx.Response(403, json={"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]})
        if p.endswith("/zones"):
            return ok([{"id": "z1", "name": "example.it"}, {"id": "z2", "name": "example.com"}])
        if p.endswith("/graphql"):
            zone = json.loads(req.content)["variables"]["zone"]
            g = [{"count": 30, "dimensions": {"clientIP": SCANNER, "clientRequestHTTPHost": f"www.{zone}.it",
                                              "clientRequestPath": "/wp-login.php", "edgeResponseStatus": 522}},
                 {"count": 2, "dimensions": {"clientIP": "93.40.1.2", "clientRequestHTTPHost": f"www.{zone}.it",
                                             "clientRequestPath": "/", "edgeResponseStatus": 522}}]
            return httpx.Response(200, json={"data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": g}]}}})
        if p.endswith("/access_rules/rules") and m == "POST":
            body = json.loads(req.content)
            self.rules["r1"] = body
            return ok({"id": "r1", **body})
        if "/access_rules/rules/" in p and m == "DELETE":
            self.rules.pop(p.rsplit("/", 1)[1], None)
            return ok({"id": p.rsplit("/", 1)[1]})
        return httpx.Response(404, json={"success": False, "errors": [{"code": 7003, "message": "no route"}]})


@pytest.fixture
def cloudflare(monkeypatch, cfg, shared):
    real = httpx.Client

    def use(fake):
        monkeypatch.setattr(net_cloudflare.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
        cfg.values.update(AURORA_CLOUDFLARE_ACCOUNT_ID="acc123", AURORA_CLOUDFLARE_API_TOKEN="tok-secret")
        return cfg
    return use


def test_culprits_are_the_clients_behind_cloudflare_across_zones(cloudflare):
    cfg = cloudflare(FakeCloudflare())
    rows = net_cfwaf.culprits(cfg, 6)
    assert rows[0]["ip"] == SCANNER and rows[0]["requests"] == 60 and rows[0]["paths"] == ["/wp-login.php"]
    assert len(rows[0]["hosts"]) == 2 and rows[1]["requests"] == 4


def test_a_missing_permission_is_said_with_what_to_add(cloudflare):
    cfg = cloudflare(FakeCloudflare(allowed=False))
    with pytest.raises(net_cfwaf.CloudflareError, match="Access Rules"):
        net_cfwaf.culprits(cfg)
    with pytest.raises(net_cfwaf.CloudflareError, match="Access Rules"):
        net_cfwaf.block(cfg, SCANNER, "scanner")


def test_block_unblock_and_expiry_at_cloudflare(cloudflare):
    fake = FakeCloudflare()
    cfg = cloudflare(fake)
    rec = net_cfwaf.block(cfg, SCANNER, "wp-login scanner", hours=2)
    assert fake.rules["r1"]["mode"] == "block" and fake.rules["r1"]["configuration"]["value"] == SCANNER
    assert "tok-secret" not in net_cfwaf._file(cfg).read_text()
    with pytest.raises(net_cfwaf.CloudflareError, match="già"):
        net_cfwaf.block(cfg, SCANNER, "again")
    assert net_cfwaf.release_due(cfg, rec["at"] + 3600) == []
    assert net_cfwaf.release_due(cfg, rec["at"] + 3 * 3600) == [SCANNER] and not fake.rules
    assert net_cfwaf.active(cfg) == []


def test_never_a_cloudflare_node_or_a_house_address_at_cloudflare(cloudflare):
    cfg = cloudflare(FakeCloudflare())
    for ip in (CF_NODE, "192.168.1.50", "not-an-ip"):
        with pytest.raises(net_cfwaf.CloudflareError):
            net_cfwaf.block(cfg, ip, "x")


def test_a_cloud_machine_seen_by_cloudflare_is_the_author_and_blockable(cloudflare, monkeypatch):
    """C315: a Google Cloud VM reading /.aws/credentials was refused as a «shared» address."""
    cfg = cloudflare(FakeCloudflare())
    monkeypatch.setattr(sec_intel, "shared", lambda c, ip: {"34.1.2.3": "Google Cloud"}.get(ip, ""))
    assert net_cfwaf.blockable(cfg, "34.1.2.3") == "34.1.2.3"
    s = {"ip": "34.1.2.3", "requests": 1262, "paths": {"/.aws/credentials": 900}}
    assert net_cfwaf.looks(cfg, s).startswith("scanner") and "Google Cloud" in net_cfwaf.looks(cfg, s)
    assert "not to block" in net_cfwaf.looks(cfg, {"ip": "81.2.69.160", "requests": 2, "paths": {"/v1/aurora/push-ack": 1}})


def test_an_ipv6_client_is_blocked_as_ip6(cloudflare):
    fake = FakeCloudflare()
    cfg = cloudflare(fake)
    net_cfwaf.block(cfg, "2a0c:b641:b0:a1a1:21c4::1", "phpinfo, .env")
    assert fake.rules["r1"]["configuration"] == {"target": "ip6", "value": "2a0c:b641:b0:a1a1:21c4::1"}


def test_autoblock_blocks_only_scanners_only_when_asked_and_within_the_day(cloudflare, monkeypatch):
    from aurora import sys_ethics
    fake = FakeCloudflare()
    cfg = cloudflare(fake)
    monkeypatch.setattr(sys_ethics, "exempt", lambda c: True)
    cfg.values["AURORA_CLOUDFLARE_AUTOBLOCK"] = False
    assert net_cfwaf.autoblock(cfg) == [] and not fake.rules                     # off: she only lists them
    cfg.values.update(AURORA_CLOUDFLARE_AUTOBLOCK=True, AURORA_DEFENCE_HOURS=24, AURORA_DEFENCE_MAX_PER_DAY=20)
    done = net_cfwaf.autoblock(cfg)
    assert [b["ip"] for b in done] == [SCANNER] and done[0]["auto"]               # 93.40.1.2 asked «/»: not hers
    assert net_cfwaf.autoblock(cfg) == []                                          # blocked already
    monkeypatch.setattr(sys_ethics, "exempt", lambda c: False)
    net_cfwaf.unblock(cfg, SCANNER)
    assert net_cfwaf.autoblock(cfg) == []                                          # not exempted: the owner decides
