# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛡️ Security → 🔌 Firewall connections (owner, 16 Oct: «può scegliere tutti quelli che vuole… una volta confermato il
collegamento la suite security comincia a funzionare»): many firewalls, passwords sealed, a block on every connected one."""
import pytest

from aurora import sec_firewalls, sec_fwapi


def test_a_firewall_is_kept_with_its_password_sealed_and_read_through_a_view(cfg):
    out = sec_firewalls.save(cfg, "new", {"name": "Lab pf", "kind": "pfsense", "url": "https://192.0.2.1"}, "s3cret")
    fid = out["id"]
    f = cfg.path("AURORA_STATUS_DIR") / "security"
    assert b"s3cret" not in (f / "firewalls.secrets").read_bytes() and "s3cret" not in (f / "firewalls.json").read_text()
    it = next(x for x in sec_firewalls.items(cfg) if x["id"] == fid)
    assert it["has_password"] and not it["confirmed"] and "password" not in it
    v = sec_firewalls.view(cfg, it)
    assert v["AURORA_FIREWALL_API_KIND"] == "pfsense" and v["AURORA_FIREWALL_API_PASSWORD"] == "s3cret"
    assert cfg["AURORA_FIREWALL_API_PASSWORD"] != "s3cret"                     # the machine's own stays as it was
    with pytest.raises(ValueError):
        sec_firewalls.save(cfg, fid, {"kind": "nonsense"})
    sec_firewalls.remove(cfg, fid)
    assert all(x["id"] != fid for x in sec_firewalls.items(cfg))


def test_a_block_goes_to_every_connected_firewall_and_one_failing_does_not_stop_the_others(cfg, monkeypatch):
    a = sec_firewalls.save(cfg, "new", {"name": "a", "kind": "pfsense", "url": "https://192.0.2.1"}, "x")["id"]
    b = sec_firewalls.save(cfg, "new", {"name": "b", "kind": "opnsense", "url": "https://192.0.2.2"}, "y")["id"]
    c = sec_firewalls.save(cfg, "new", {"name": "c", "kind": "pfsense", "url": "https://192.0.2.3", "blocks": False}, "z")["id"]
    monkeypatch.setattr(sec_fwapi, "test", lambda v: {"ok": True, "group_exists": False})
    monkeypatch.setattr(sec_fwapi, "request", lambda v, body: "{}")
    for fid in (a, b, c):
        assert sec_firewalls.connect(cfg, fid, docs=False)["ok"]
    assert {x["id"] for x in sec_firewalls.receivers(cfg)} >= {a, b} and c not in {x["id"] for x in sec_firewalls.receivers(cfg)}

    def block(v, ip, reason=""):
        if v["AURORA_FIREWALL_API_KIND"] == "opnsense":
            raise sec_fwapi.FirewallAPIError("the firewall does not answer")
        return {"blocked": ip, "status": "200", "message": ""}
    monkeypatch.setattr(sec_fwapi, "block", block)
    out = sec_firewalls.block(cfg, "203.0.113.9", "scan")
    assert out["blocked"] == "203.0.113.9" and a in out["firewalls"] and b in out["failed"]


def test_a_firewall_that_cannot_log_in_is_not_confirmed(cfg, monkeypatch):
    fid = sec_firewalls.save(cfg, "new", {"name": "x", "kind": "opnsense", "url": "https://192.0.2.4"}, "k")["id"]
    def refuse(v):
        raise sec_fwapi.FirewallAPIError("the firewall refused the login")
    monkeypatch.setattr(sec_fwapi, "test", refuse)
    assert sec_firewalls.connect(cfg, fid, docs=False) == {"ok": False, "error": "the firewall refused the login"}
    it = next(x for x in sec_firewalls.items(cfg) if x["id"] == fid)
    assert not it["confirmed"] and "refused" in it["error"]
    assert [k["kind"] for k in sec_firewalls.kinds()] == ["sophos", "pfsense", "opnsense"]


def test_the_settings_firewall_keeps_its_blocks_when_another_is_added(cfg, monkeypatch):
    cfg.values.update(AURORA_FIREWALL_API_URL="https://192.0.2.10", AURORA_FIREWALL_API_USER="u",
                      AURORA_FIREWALL_API_PASSWORD="p")
    monkeypatch.setattr(sec_fwapi, "test", lambda v: {"ok": True, "group_exists": True})
    monkeypatch.setattr(sec_fwapi, "request", lambda v, body: "{}")
    assert [x["id"] for x in sec_firewalls.receivers(cfg)] == ["main"]
    fid = sec_firewalls.save(cfg, "new", {"name": "b", "kind": "pfsense", "url": "https://192.0.2.2"}, "y")["id"]
    sec_firewalls.connect(cfg, fid, docs=False)
    assert [x["id"] for x in sec_firewalls.receivers(cfg)] == ["main", fid]


def test_saving_without_a_change_to_the_connection_keeps_it_confirmed(cfg, monkeypatch):
    monkeypatch.setattr(sec_fwapi, "test", lambda v: {"ok": True, "group_exists": True})
    monkeypatch.setattr(sec_fwapi, "request", lambda v, body: "{}")
    fid = sec_firewalls.save(cfg, "new", {"name": "a", "kind": "pfsense", "url": "https://192.0.2.1"}, "x")["id"]
    sec_firewalls.connect(cfg, fid, docs=False)
    sec_firewalls.save(cfg, fid, {"name": "renamed", "manual": "https://example.org/manual/"})
    assert next(x for x in sec_firewalls.items(cfg) if x["id"] == fid)["confirmed"]
    sec_firewalls.save(cfg, fid, {"url": "https://192.0.2.9"})
    assert not next(x for x in sec_firewalls.items(cfg) if x["id"] == fid)["confirmed"]
