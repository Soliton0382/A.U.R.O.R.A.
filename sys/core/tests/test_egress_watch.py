# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Every way out of Aurora's services, learnt and watched (sec_egress_watch, ROADMAP N50; owner, 2026-10-27): a week
of learning, then a network never seen is an incident — high «from nothing», medium during a run —, a file going out
is high, the owner's answers are kept, the owner's desktop is never looked at."""
import json

from aurora import sec_egress_watch as W, sec_incidents, sec_quiet

DAY = 86400
NETS = {"198.51.100.7": {"asn": 64500, "prefix": "198.51.100.0/24", "holder": "EXAMPLE-NET"},
        "203.0.113.9": {"asn": 64501, "prefix": "203.0.113.0/24", "holder": "OTHER-NET"}}


def _sock(peer, sent=1000, pid=10):
    return {"pid": pid, "process": "python", "peer": peer, "port": "443", "state": "ESTAB", "sent": sent}


def _watch(cfg, socks, busy=False):
    owner = {10: "aurora-api.service", 20: ""}.get                       # 20: the owner's browser
    return W.EgressWatch(cfg, busy=lambda: busy, sample=lambda: socks, owner=lambda pid: owner(pid, ""),
                         networks=W.Networks(cfg, lookup=lambda ip: NETS.get(ip, {})))


def test_a_week_of_learning_then_a_new_network_is_told(cfg):
    socks = [_sock("198.51.100.7")]
    w = _watch(cfg, socks)
    assert w.look(now=1000) == []                                        # learning: notes only
    assert W.baseline(cfg)["services"]["aurora-api.service"]["AS64500"]["learning"] is True
    socks.append(_sock("203.0.113.9"))
    socks.append(_sock("203.0.113.9", pid=20))                           # the desktop: never looked at
    [inc] = w.look(now=1000 + 8 * DAY)
    assert inc["kind"] == "egress_new" and inc["detail"]["key"] == "AS64501" and inc["detail"]["busy"] is False
    assert "nessun lavoro" in inc["detail"]["why"] and sec_incidents.severity(inc) == "high"
    assert w.look(now=1000 + 8 * DAY + 60) == []                         # learnt now, and told once
    assert sec_quiet.pattern(inc) is None                                # never quieted


def test_during_a_run_a_new_network_is_medium(cfg):
    w = _watch(cfg, [_sock("198.51.100.7")], busy=True)
    w.look(now=1000)
    w.sample = lambda: [_sock("203.0.113.9")]
    [inc] = w.look(now=1000 + 8 * DAY)
    assert inc["detail"]["busy"] is True and sec_incidents.severity(inc) == "medium"


def test_a_file_going_out_is_high_and_the_owners_answers_hold(cfg):
    w = _watch(cfg, [_sock("198.51.100.7", sent=50_000)])
    w.look(now=1000)
    big = W.UPLOAD_BYTES + 1
    w.sample = lambda: [_sock("198.51.100.7", sent=big)]
    [inc] = w.look(now=1000 + 8 * DAY)
    assert inc["kind"] == "egress_upload" and sec_incidents.severity(inc) == "high" and str(big) in inc["detail"]["why"]
    W.decide(cfg, "aurora-api.service", "AS64500", "legit")
    w.read_at = 0                                                        # the answers read again
    assert w.look(now=1000 + 9 * DAY) == []                              # legitimate: not told again
    W.decide(cfg, "aurora-api.service", "AS64501", "denied")
    w.sample = lambda: [_sock("203.0.113.9")]
    w.read_at = 0
    assert w.look(now=1000 + 10 * DAY) == []                             # answered: the deny list has it (sec_egress)
    r = W.report(cfg, now=1000 + 10 * DAY)
    nets = {n["key"]: n for n in r["services"]["aurora-api.service"]}
    assert r["learning"] is False and nets["AS64500"]["answer"] == "legit" and nets["AS64501"]["answer"] == "denied"


def test_ripestat_is_asked_sparingly_and_remembered(cfg):
    asked = []
    nets = W.Networks(cfg, lookup=lambda ip: asked.append(ip) or {"asn": 64500, "holder": "X"})
    for k in range(W.LOOKUPS_PER_MIN + 5):
        nets.of(f"198.51.100.{k}", now=100)
    assert len(asked) == W.LOOKUPS_PER_MIN                               # the rest at the next sample
    again = W.Networks(cfg, lookup=lambda ip: 1 / 0)
    assert again.of("198.51.100.0", now=200)["asn"] == 64500             # kept across a restart
    assert json.loads((cfg.path("AURORA_STATUS_DIR") / "egress_networks.json").read_text())


def test_only_public_peers_are_read_from_ss(monkeypatch):
    out = ("ESTAB 0 0 192.0.2.101:5000 9.9.9.9:443 users:((\"python\",pid=10,fd=3))\n"
           "\t cubic bytes_sent:4242 bytes_acked:4243\n"
           "ESTAB 0 0 127.0.0.1:5001 127.0.0.1:9711 users:((\"python\",pid=10,fd=4))\n"
           "ESTAB 0 0 192.0.2.101:5002 10.0.0.9:445 users:((\"python\",pid=10,fd=5))\n")
    monkeypatch.setattr(W.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": out})())
    assert W.sockets() == [{"pid": 10, "process": "python", "peer": "9.9.9.9", "port": "443", "state": "ESTAB",
                            "sent": 4242}]
