# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C596 (security audit of 12 Nov, area C — the sentinel): one flooding source no longer makes every line cost more,
the owner's rules hold a bounded number of sources, the firewall's words reach the agent marked, the automatic
blocks spare the house's own address and what a forged packet names, and the smaller gaps. Made-up addresses."""
import json
import ssl
import time

import pytest

from aurora import agt_logguard, net_cfwaf, sec_defence, sec_detonate, sec_intel, sec_rules, sec_tlspin
from aurora.sec_baseline import MAX_DEVICES, SILENT_S, Baseline
from aurora.sec_sentinel import SAMPLE, Budget, Detector, Window, parse

DENY = 'log_type="Firewall" status="Deny" src_ip="{ip}" dst_ip="10.0.0.10" dst_port={p} protocol="TCP"'


# ---- C1: one source, any rate -------------------------------------------------------------------------------------
def test_a_flooding_source_is_counted_by_the_second_not_line_by_line():
    d = Detector(window_s=300, deny_threshold=50, scan_ports=20)
    line = parse(DENY.format(ip="203.0.113.7", p=22) + " " + "x" * 3000)
    raised = []
    for i in range(30000):                                    # 100 lines a second for five minutes
        raised += d.feed(line, now=1000 + i / 100)
    q = d.denies["203.0.113.7"]
    assert len(q) == 30000 and len(q.cells) <= 301            # the count exact, one cell a second
    assert len(q.samples) == 5 and all(len(s) <= SAMPLE for s in q.samples)
    assert [i.kind for i in raised] == ["deny_burst"] and raised[0].count == 50
    assert all(len(s) <= SAMPLE for s in raised[0].samples)   # C9: a sample is a line's start, not 8 KB
    d.feed(line, now=1000 + 300 + 400)                        # silent, then one line: the window is its own again
    assert len(d.denies["203.0.113.7"]) == 1


def test_the_ports_of_a_source_are_one_entry_each_and_bounded():
    d = Detector(window_s=300, deny_threshold=10**9, scan_ports=20)
    out = []
    for i in range(5000):
        out += d.feed(parse(DENY.format(ip="203.0.113.8", p=1000 + i)), now=1000 + i / 100)
    assert len(d.ports["203.0.113.8"]) == Detector.MAX_PORTS
    assert [i.kind for i in out] == ["port_scan"] and len(out[0].detail["ports"]) == 20
    for i in range(1000):                                     # the same port again and again: one entry
        d.feed(parse(DENY.format(ip="203.0.113.9", p=443)), now=2000 + i / 100)
    assert len(d.ports["203.0.113.9"]) == 1


def test_a_window_forgets_by_the_time_of_its_lines():
    w = Window()
    for t in (10.2, 10.9, 11.5, 400.0):
        w.add(t, "line")
    assert len(w) == 4 and w.first == 10.2
    w.trim(400.0, 300)
    assert len(w) == 1 and w.first == 400.0


# ---- C3: the budget never walks its hour -------------------------------------------------------------------------
def test_the_budget_counts_its_minute_apart():
    b = Budget(per_min=3, per_hour=5)
    assert [b.take(100 + i) for i in range(4)] == [True, True, True, False]
    assert b.take(170) and b.take(171) and not b.take(172)            # the hour's five are taken
    assert len(b.minute) == 2 and len(b.taken) == 5 and b.refused == 2
    assert b.take(100 + 3600)                                          # the first ones are an hour old


# ---- C2: the owner's rules ---------------------------------------------------------------------------------------
RULE = {"id": "wan_denied", "match": {"status": ["deny"]}, "threshold": 3, "window_min": 10, "per_source": True, "on": True}


def test_the_rule_set_forgets_and_has_a_budget():
    rs = sec_rules.RuleSet([sec_rules.check(RULE)])
    for i in range(5000):                                     # sources that never come back, in one minute
        rs.feed(parse(DENY.format(ip=f"198.51.{i // 250}.{i % 250}", p=80)), f"198.51.{i // 250}.{i % 250}", 1000 + i * 0.01)
    assert len(rs.seen) == rs.NEW_PER_MIN and rs.fresh.refused == 5000 - rs.NEW_PER_MIN
    rs.feed(parse(DENY.format(ip="203.0.113.1", p=80)), "203.0.113.1", 1000 + 3600)
    assert set(rs.seen) == {("wan_denied", "203.0.113.1")}    # the silent ones are gone
    hits = [rs.feed(parse(DENY.format(ip="203.0.113.1", p=80)), "203.0.113.1", 4601 + i) for i in range(3)]
    assert [len(h) for h in hits] == [0, 1, 0] and hits[1][0][2] == 3 and len(hits[1][0][3]) == 3


def test_the_rules_incidents_a_minute_are_capped():
    rs = sec_rules.RuleSet([sec_rules.check({**RULE, "threshold": 1})])
    told = sum(len(rs.feed(parse(DENY.format(ip=f"203.0.113.{i}", p=80)), f"203.0.113.{i}", 1000 + i * 0.1)) for i in range(100))
    assert told == rs.RAISED_PER_MIN and rs.alarms.refused == 100 - rs.RAISED_PER_MIN
    assert len(rs.raised) == rs.RAISED_PER_MIN                # a held one is not marked as said


# ---- C4: the firewall's words reach the agent marked -------------------------------------------------------------
def test_the_security_tools_that_read_the_log_are_log_tools():
    for tool in ("security_incidents", "firewall_summary", "security_night_report", "security_weekly_report",
                 "threat_hunt", "security_posture"):
        assert agt_logguard.reads_logs("security", tool), tool
    assert not agt_logguard.reads_logs("security", "firewall_apply")


def test_the_summary_cuts_a_strangers_words():
    """The plugin's server is not imported in a test (it reads its own configuration): its source is looked at."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "plugins" / "security" / "server.py").read_text(encoding="utf-8")
    assert '" ".join(str(what).split())[:120]' in src and '" ".join(str(dest).split())[:120]' in src


# ---- C5, C7: what is blocked by herself --------------------------------------------------------------------------
@pytest.fixture
def auto(cfg, monkeypatch):
    cfg.values.update(AURORA_DEFENCE_MODE="auto", AURORA_DEFENCE_MIN_SEVERITY="low", AURORA_DEFENCE_PROTECTED="")
    from aurora import sec_firewalls, sec_fwapi, sys_ethics
    monkeypatch.setattr(sys_ethics, "exempt", lambda c: True)
    monkeypatch.setattr(sec_fwapi, "blockable", lambda c, ip: ip)
    monkeypatch.setattr(sec_firewalls, "receivers", lambda c: [{"id": "main"}])
    monkeypatch.setattr(sec_intel, "shared", lambda c, ip: "")
    monkeypatch.setattr(sec_defence, "house", lambda c: {"1.0.0.1"})
    return cfg


def test_refused_packets_alone_never_block_an_address(auto):
    inc = {"kind": "port_scan", "source": "9.9.9.9", "severity": "medium", "internal": False}
    ok, why = sec_defence.decide(auto, inc)
    assert not ok and "forged" in why
    assert not sec_defence.decide(auto, {**inc, "kind": "deny_burst"})[0]
    assert not sec_defence.decide(auto, {**inc, "kind": "rule:wan_denied"})[0]
    assert sec_defence.decide(auto, {**inc, "intel_lists": [{"list": "feodo"}]}) == (True, "ok")   # a known attacker
    assert sec_defence.decide(auto, {**inc, "kind": "auth_fail"}) == (True, "ok")                  # a session was made


def test_the_houses_own_address_is_never_blocked(auto):
    inc = {"kind": "auth_fail", "source": "1.0.0.1", "severity": "high", "internal": False}
    ok, why = sec_defence.decide(auto, inc)
    assert not ok and "WAN" in why
    assert net_cfwaf.blockable(auto, "8.8.4.4") == "8.8.4.4"
    with pytest.raises(net_cfwaf.CloudflareError):
        net_cfwaf.blockable(auto, "1.0.0.1")


def test_the_wan_address_comes_from_the_firewalls_map(cfg, monkeypatch):
    from aurora import sec_netmap
    monkeypatch.setattr(sec_netmap, "stored", lambda c: ["main"])
    monkeypatch.setattr(sec_netmap, "load", lambda c, which="netmap", fid="main": {"interfaces": [
        {"name": "Port2", "zone": "WAN", "ip": "8.8.4.4"}, {"name": "Port1", "zone": "LAN", "ip": "192.168.1.1"},
        {"name": "Port3", "zone": "WAN", "ip": "192.168.100.2"}, {"name": "Port4", "zone": "WAN", "ip": ""}]})
    assert sec_defence.house(cfg) == {"8.8.4.4"}
    monkeypatch.setattr(sec_netmap, "load", lambda *a, **k: (_ for _ in ()).throw(OSError("unreadable")))
    assert sec_defence.house(cfg) == set()


def test_one_request_to_a_secret_looking_path_is_not_blocked_at_cloudflare(cfg, monkeypatch):
    from aurora import sys_ethics
    cfg.values.update(AURORA_CLOUDFLARE_AUTOBLOCK=True, AURORA_DEFENCE_MAX_PER_DAY=5, AURORA_DEFENCE_HOURS=24)
    monkeypatch.setattr(sys_ethics, "exempt", lambda c: True)
    rows = [{"ip": "8.8.4.4", "requests": 1, "paths": ["/admin"], "looks": "scanner (…)", "secret_paths": 1,
             "secret_requests": 1},
            {"ip": "8.8.8.8", "requests": 3, "paths": ["/.env", "/.git/config", "/wp-login.php"], "looks": "scanner (…)",
             "secret_paths": 3, "secret_requests": 3},
            {"ip": "9.9.9.9", "requests": 40, "paths": ["/wp-login.php"], "looks": "scanner (…)", "secret_paths": 1,
             "secret_requests": 40}]
    monkeypatch.setattr(net_cfwaf, "culprits", lambda c, hours, limit=20: rows)
    done = []
    monkeypatch.setattr(net_cfwaf, "block", lambda c, ip, why, hours, auto=False: done.append(ip) or {"ip": ip})
    net_cfwaf.autoblock(cfg)
    assert done == ["8.8.8.8", "9.9.9.9"]                     # many paths, or one many times: a scanner


# ---- C6: Cloudflare's nodes are known with the lists off ---------------------------------------------------------
def test_cloudflares_ranges_are_known_without_the_downloaded_lists(cfg):
    sec_intel._shared["at"] = 0.0
    assert not (cfg.path("AURORA_STATUS_DIR") / "security" / "intel.json").exists()
    assert sec_intel.shared(cfg, "104.16.1.1") == "Cloudflare" and sec_intel.shared(cfg, "2606:4700::1111") == "Cloudflare"
    assert sec_intel.shared(cfg, "203.0.113.9") == ""
    sec_intel._shared["at"] = 0.0


# ---- C8: «whole» reads past the first 48,000 characters ----------------------------------------------------------
def test_the_decoy_reads_the_end_of_a_long_content_too():
    head = sec_detonate.CHUNK * sec_detonate.MAX_CHUNKS
    text = "a" * (head + 20000) + " THE-END-OF-IT"
    got = sec_detonate.pieces(text, whole=True)
    assert any("THE-END-OF-IT" in p for p in got) and sum(map(len, got)) >= len(text)       # all of it, here
    long = "a" * (head * 5) + " THE-END-OF-IT"
    got = sec_detonate.pieces(long, whole=True)
    assert len(got) <= sec_detonate.MAX_CHUNKS * 2 and got[-1].endswith("THE-END-OF-IT")
    assert sec_detonate.partial(long) and not sec_detonate.partial(text)
    assert sec_detonate.pieces("short", whole=True) == ["short"]


# ---- C9: the smaller ones ----------------------------------------------------------------------------------------
def test_a_forgotten_pin_is_never_learnt_again_by_itself(cfg, real_tls, monkeypatch):
    url = "https://192.168.1.1:4444"
    learnt = []
    monkeypatch.setattr(sec_tlspin, "learn", lambda c, u, timeout=10.0: learnt.append(u))
    sec_tlspin._save(cfg, {"192.168.1.1:4444": {"pem": "PEM", "sha256": "x", "at": 1.0}})
    assert sec_tlspin.forget(cfg, url)
    with pytest.raises(ssl.SSLError):
        sec_tlspin.verify(cfg, url, ca=False)
    assert learnt == [] and sec_tlspin.why(ssl.SSLError(sec_tlspin.FORGOTTEN)) == sec_tlspin.FORGOTTEN


def test_the_baseline_gives_a_silent_devices_place_to_a_new_one(cfg):
    b = Baseline(cfg, days=0)
    line = lambda i: {"log_type": "Firewall", "src_zone": "LAN", "src_ip": f"10.{i // 250}.{i % 250}.9"}   # noqa: E731
    for i in range(MAX_DEVICES):
        b.feed(line(i), now=1000.0)
    b.feed(line(5000), now=1100.0)
    assert len(b.state["devices"]) == MAX_DEVICES and "10.20.0.9" not in b.state["devices"]   # full: not followed
    b.feed(line(0), now=1000.0 + SILENT_S + 50)                   # one of the house's speaks every day
    b.feed(line(5000), now=1000.0 + SILENT_S + 200)               # a day later the silent ones give their place
    assert set(b.state["devices"]) == {"10.0.0.9", "10.20.0.9"}


def test_a_block_done_on_some_firewalls_only_is_recorded(cfg, monkeypatch):
    from aurora import sec_firewalls
    monkeypatch.setattr(sec_firewalls, "block", lambda c, ip, reason="": {
        "blocked": ip, "firewalls": {"main": {}}, "failed": {"second": "no answer"}})
    out = sec_defence.act(cfg, {"source": "8.8.4.4", "kind": "auth_fail", "id": "i1", "severity": "high"})
    assert out["failed"] == {"second": "no answer"}
    assert sec_defence._load(cfg)[-1]["failed"] == {"second": "no answer"}


def test_the_dns_name_is_asked_outside_the_event_loop():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "aurora" / "api" / "incidents.py").read_text(encoding="utf-8")
    assert "await asyncio.to_thread(destination_of, incident)" in src and "setdefaulttimeout(" not in src
