# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora reachable from away (net_cloudflare, the cloudflare plugin, roadmap 56): the state read, what is missing,
«Salva» on a fake Cloudflare account. Documentation addresses only (RFC 5737); no real account."""
import json
import stat
from types import SimpleNamespace

import httpx
import pytest

from aurora import net_cloudflare as CF

VALUES = {"AURORA_CLOUDFLARE_ACCOUNT_ID": "acc1", "AURORA_CLOUDFLARE_API_TOKEN": "api-t0ken-never-shown",
          "AURORA_CLOUDFLARE_TUNNEL": "aurora", "AURORA_CLOUDFLARE_NETWORK": "192.0.2.10/32",
          "AURORA_CLOUDFLARE_DOMAIN": "home.example", "AURORA_CLOUDFLARE_DNS": "192.0.2.1"}
TUNNEL_TOKEN = "eyJhIjoiZmFrZSJ9-tunnel-secret"


class Fake:
    """A Cloudflare account in memory: tunnels, routes, an exclude split tunnel (WARP's default), fallback domains."""

    def __init__(self, published=()):
        self.tunnels, self.routes, self.fallback, self.writes = [], [], [], []
        self.exclude = [{"address": "192.0.0.0/16", "description": "LAN"}, {"address": "10.0.0.0/8"}]
        self.published = list(published)
        if published:                                  # a tunnel made by hand in the dashboard, with a public route
            self.tunnels.append({"id": "tun1", "name": "aurora", "status": "inactive", "connections": []})

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p, m = req.url.path.removeprefix("/client/v4"), req.method
        ok = lambda r: httpx.Response(200, json={"success": True, "result": r})       # noqa: E731
        assert req.headers["authorization"] == "Bearer api-t0ken-never-shown"
        body = json.loads(req.content) if req.content else None
        if m != "GET":
            self.writes.append((m, p))
        if p.endswith("/tokens/verify"):
            return ok({"status": "active"})
        if p.endswith("/cfd_tunnel") and m == "GET":
            return ok(self.tunnels)
        if p.endswith("/cfd_tunnel") and m == "POST":
            self.tunnels.append({"id": "tun1", "name": body["name"], "status": "inactive", "connections": []})
            return ok(self.tunnels[-1])
        if p.endswith("/configurations"):
            return ok({"config": {"ingress": [{"hostname": h, "service": "https://localhost"} for h in self.published]
                                  + [{"service": "http_status:404"}]}})
        if p.endswith("/tun1/token"):
            return ok(TUNNEL_TOKEN)
        if p.endswith("/teamnet/routes"):
            if m == "POST":
                self.routes.append({**body, "tunnel_name": "aurora"})
            return ok(self.routes)
        if p.endswith("/devices/policy"):
            return ok({"exclude": self.exclude})
        if p.endswith("/devices/policy/exclude"):
            if m == "PUT":
                self.exclude = body
            return ok(self.exclude)
        if p.endswith("/fallback_domains"):
            if m == "PUT":
                self.fallback = body
            return ok(self.fallback)
        return httpx.Response(404, json={"success": False, "errors": [{"code": 7003, "message": "no route"}]})


@pytest.fixture
def account(monkeypatch, cfg):
    real = httpx.Client

    def use(fake, service="inactive"):
        monkeypatch.setattr(CF.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
        monkeypatch.setattr(CF, "service_state", lambda: service)
        for k, v in VALUES.items():
            cfg.values[k] = v
        return cfg
    return use


def test_the_lan_exclusion_is_carved_around_aurora_only():
    import ipaddress
    out = CF.without([{"address": "192.0.0.0/16", "description": "LAN"}, {"address": "10.0.0.0/8"}], "192.0.2.10/32")
    nets = [o["address"] for o in out]
    assert "10.0.0.0/8" in nets and "192.0.2.10/32" not in nets and len(nets) == 1 + 16
    covered = [ipaddress.ip_network(n) for n in nets if n != "10.0.0.0/8"]
    assert sum(n.num_addresses for n in covered) == 2 ** 16 - 1                # the whole LAN but Aurora's address
    assert all(ipaddress.ip_address("192.0.2.10") not in n for n in covered)


def test_check_lists_what_is_missing_and_never_a_token(account):
    fake = Fake()
    cfg = account(fake, service="missing")
    out = CF.check(cfg)
    assert "creare il tunnel «aurora»" in out and "aggiungere la rotta privata 192.0.2.10/32" in out
    assert "togliere 192.0.2.10/32 dagli esclusi di WARP (192.0.0.0/16)" in out
    assert "aggiungere home.example al Local Domain Fallback di WARP (DNS 192.0.2.1)" in out
    assert "sudo bash sys/deploy/cloudflared/install.sh" in out
    assert "t0ken" not in out and not fake.writes                             # read only


def test_save_does_every_step_once_and_keeps_the_token_private(account):
    fake = Fake()
    cfg = account(fake)
    verbs = []
    r = CF.apply(cfg, systemctl=lambda verb: verbs.append(verb) or SimpleNamespace(returncode=0, stderr=""))
    assert r["ok"], r["text"]
    assert "✅ tunnel «aurora» creato" in r["text"] and "✅ rotta 192.0.2.1/32 aggiunta al tunnel" in r["text"]
    assert {x["network"] for x in fake.routes} == {"192.0.2.10/32", "192.0.2.1/32"}
    assert not CF.net_in("192.0.2.10/32", fake.exclude) and CF.net_in("192.0.3.5/32", fake.exclude)
    assert fake.fallback == [{"suffix": "home.example", "dns_server": ["192.0.2.1"], "description": CF.NOTE}]
    f = CF.token_file(cfg)                                                     # fetched by Aurora: nothing to paste
    assert f.read_text() == TUNNEL_TOKEN and stat.S_IMODE(f.stat().st_mode) == 0o600
    assert verbs == ["restart"] and "eyJ" not in r["text"] and "t0ken" not in r["text"]
    n = len(fake.writes)
    again = CF.apply(account(fake, service="active"), systemctl=lambda verb: verbs.append(verb) or SimpleNamespace(returncode=0, stderr=""))
    assert "Account Cloudflare già a posto." in again["text"] and len(fake.writes) == n and verbs[-1] == "start"


def test_a_hostname_published_on_the_internet_is_said(account):
    cfg = account(Fake(published=["aurora.home.example"]), service="active")
    assert "⚠️ aurora.home.example: PUBBLICATO su Internet" in CF.status(cfg)
    r = CF.apply(cfg, systemctl=lambda verb: SimpleNamespace(returncode=0, stderr=""))
    assert "aurora.home.example è pubblicato su Internet" in r["text"]


def test_without_the_service_installed_save_says_the_one_command(account):
    r = CF.apply(account(Fake(), service="missing"), systemctl=lambda verb: pytest.fail("no systemctl"))
    assert not r["ok"] and "servizio aurora-tunnel non installato: sudo bash sys/deploy/cloudflared/install.sh" in r["text"]
