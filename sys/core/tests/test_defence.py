# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Autonomous defence (owner, 2026-10-05): Aurora blocks an attack by herself only within every limit, and lifts it."""
import time

import pytest

from aurora import sec_defence, sec_fwapi, sys_ethics

# public addresses (scanme.nmap.org, meant for tests): documentation ranges are not global, never blocked
ATTACK = {"id": "i1", "kind": "ips_alert", "source": "45.33.32.156", "severity": "high"}


@pytest.fixture
def firewall(cfg, monkeypatch):
    calls = []
    cfg.values.update(AURORA_DEFENCE_MODE="auto", AURORA_DEFENCE_HOURS=24, AURORA_DEFENCE_MIN_SEVERITY="high",
                      AURORA_DEFENCE_MAX_PER_DAY=2, AURORA_DEFENCE_PROTECTED="45.33.33.0/24",
                      AURORA_FIREWALL_API_URL="https://192.0.2.1:4444", AURORA_FIREWALL_API_USER="aurora",
                      AURORA_FIREWALL_API_PASSWORD="secret-password")
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: True)
    monkeypatch.setattr(sec_fwapi, "block", lambda cfg, ip, reason="": calls.append(("block", ip)) or {"blocked": ip})
    monkeypatch.setattr(sec_fwapi, "unblock", lambda cfg, ip: calls.append(("unblock", ip)) or {"unblocked": ip})
    return calls


def test_an_attack_from_outside_is_blocked_for_its_hours_and_then_lifted(cfg, firewall, monkeypatch):
    assert sec_defence.decide(cfg, ATTACK) == (True, "ok")
    out = sec_defence.act(cfg, ATTACK)
    assert firewall == [("block", "45.33.32.156")] and out["until"] > time.time() + 23 * 3600
    assert sec_defence.decide(cfg, ATTACK) == (False, "already blocked")
    later = time.time() + 25 * 3600
    monkeypatch.setattr(time, "time", lambda: later)
    assert sec_defence.release_due(cfg) == ["45.33.32.156"] and firewall[-1] == ("unblock", "45.33.32.156")
    assert sec_defence.active(cfg) == []


@pytest.mark.parametrize("change, why", [
    ({"AURORA_DEFENCE_MODE": "suggest"}, "mode"),
    ({}, "severity"),
])
def test_mode_and_severity_hold_her_back(cfg, firewall, change, why):
    cfg.values.update(change)
    incident = ATTACK if change else {**ATTACK, "severity": "medium"}
    ok, reason = sec_defence.decide(cfg, incident)
    assert not ok and reason.startswith(why)


def test_never_the_house_a_protected_network_or_without_the_exemption(cfg, firewall, monkeypatch):
    assert not sec_defence.decide(cfg, {**ATTACK, "source": "192.168.1.50"})[0]       # a device of the house
    assert not sec_defence.decide(cfg, {**ATTACK, "internal": True})[0]
    assert sec_defence.decide(cfg, {**ATTACK, "source": "45.33.33.9"}) == (False, "a protected address")
    monkeypatch.setattr(sys_ethics, "exempt", lambda cfg=None: False)
    assert sec_defence.decide(cfg, ATTACK)[1].startswith("not exempted")
    assert firewall == []


def test_the_daily_limit_stops_her(cfg, firewall):
    for ip in ("45.33.32.157", "45.33.32.158"):
        sec_defence.act(cfg, {**ATTACK, "source": ip})
    assert sec_defence.decide(cfg, ATTACK) == (False, "today's limit of automatic blocks reached")


def test_unblock_takes_the_host_out_of_the_group_before_removing_it(cfg, monkeypatch):
    """C146, measured on the real firewall: removing a host still in the group is refused (509)."""
    sent = []
    cfg.values.update(AURORA_FIREWALL_API_URL="https://192.0.2.1:4444", AURORA_FIREWALL_API_USER="aurora",
                      AURORA_FIREWALL_API_PASSWORD="secret-password")

    def fake(cfg, body):
        sent.append(body)
        return '<IPHost><Status code="200">Configuration applied successfully.</Status></IPHost>'
    monkeypatch.setattr(sec_fwapi, "request", fake)
    assert sec_fwapi.unblock(cfg, "45.33.32.156")["status"] == "200"
    assert "<HostGroupList></HostGroupList>" in sent[0] and sent[1].startswith("<Remove>")
