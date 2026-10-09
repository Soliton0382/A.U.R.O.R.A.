# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Roadmap 81 (owner, 10 Oct: «solo così posso fidarmi a lasciarle il pilota automatico»), from M161's numbers."""
import importlib
import sys
import time

import pytest

from aurora import sec_scorecard as SC
from aurora.sec_sentinel import household, is_ips, parse

LAN = 'log_id="010302602002" log_type="Firewall" log_component="Appliance Access" log_subtype="Denied" src_ip="10.0.0.21" '


def test_the_houses_chatter_is_never_a_port_scan():
    assert household(parse(LAN + 'dst_ip="10.0.0.255" protocol="UDP" dst_port="6667"'))        # Tuya discovery
    assert household(parse(LAN + 'dst_ip="239.255.255.250" protocol="UDP" dst_port="1900"'))   # SSDP
    assert household(parse(LAN + 'dst_ip="10.0.0.1" protocol="TCP" dst_port="853"'))           # DNS over TLS
    assert not household(parse(LAN + 'dst_ip="10.0.0.1" protocol="TCP" dst_port="22"'))        # SSH to the firewall
    assert not household(parse(LAN.replace("10.0.0.21", "203.0.113.9") + 'dst_ip="10.0.0.255" dst_port="6667"'))
    atp = parse('log_type="ATP" log_component="Firewall" src_ip="10.0.0.20" dst_ip="34.102.215.99" threatfeed="GreyNoise"')
    assert is_ips(atp) and not household(atp)                                     # a threat line: the detector's


@pytest.fixture
def incidents_api(cfg, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "_cached", cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):
        importlib.import_module(f"aurora.api.{name}")
    return importlib.import_module("aurora.api.incidents")


def test_a_device_at_home_reaching_a_threat_feed_address_is_explained(incidents_api, monkeypatch):
    from aurora import sec_intel
    monkeypatch.setattr(sec_intel, "lookup", lambda c, ip: [])
    monkeypatch.setattr(sec_intel, "shared", lambda c, ip: "Google Cloud")
    inc = {"kind": "ips_alert", "internal": True, "source": "10.0.0.20",
           "samples": ['src_ip="10.0.0.20" dst_ip="34.102.215.99" malware="GreyNoise" threatfeed="GreyNoise"']}
    out = incidents_api.destination_of(inc)
    assert out["destination"] == "34.102.215.99" and out["destination_provider"] == "Google Cloud"
    assert out["destination_feed"] == "GreyNoise"
    assert incidents_api.destination_of({**inc, "internal": False}) == {}


def test_the_scorecard_counts_verdicts_and_blind_time():
    now = 1_800_000_000.0
    items = [{"received_ts": now - 3600 * (k + 1), "kind": "ips_alert", "verdict": v}
             for k, v in enumerate(["right"] * 9 + ["false_alarm"])]
    w = SC.week(items, now - SC.WEEK, now, [(now - 7200, now - 7200 + 45 * 60)])
    assert (w["incidents"], w["reviewed"], w["precision"], w["reviewed_share"], w["blind_min"]) == (10, 10, 0.9, 1.0, 45)
    assert SC.passes(w) == ["cieca per 45 min (il firewall non ha mandato niente)"]
    out = SC.scorecard(None, now=now, items=items, silences=[])
    assert not out["ready"] and any("giudicati 0" in x for x in out["weeks"][1]["short"])   # the week before: nothing


def test_silences_in_the_firewalls_log_are_found(tmp_path):
    t0 = time.time() - 3 * 3600
    f = tmp_path / "firewall.log"
    lines = [time.strftime("%Y-%m-%dT%H:%M:%S.000+00:00", time.gmtime(t0 + s)) + " INFO aurora.firewall x\n"
             for s in (0, 60, 60 + 50 * 60)]                                         # a 50-minute hole
    f.write_text("".join(lines))
    g = SC.gaps(tmp_path, t0, t0 + 60 + 50 * 60)
    assert len(g) == 1 and round((g[0][1] - g[0][0]) / 60) == 50


def test_looking_around_then_going_out_is_one_high_incident():
    """The owner, 10 Oct: broadcasts alone are noise; the same device's broadcasts and then a threat going out are not."""
    from aurora.sec_incidents import severity
    from aurora.sec_sentinel import Recon
    r, now = Recon(), 1000.0
    out = parse('log_type="ATP" src_ip="10.0.0.20" dst_ip="34.102.215.99" threatfeed="GreyNoise"')
    assert r.out(out, now) is None                                        # going out alone: the detector's alert
    for k in range(200):
        r.chatter("10.0.0.20", now + k / 10, "6667")                       # a smart plug's steady chatter: one port
    assert r.out(out, now + 30) is None
    for k, port in enumerate(["22", "23", "80", "139", "445", "554", "3389", "8080"]):
        r.chatter("10.0.0.20", now + 31 + k, port)                         # then eight services asked
    inc = r.out(out, now + 60)
    assert inc["kind"] == "recon_then_out" and len(inc["detail"]["ports"]) == 9 and inc["detail"]["destination"] == "34.102.215.99"
    assert severity({**inc, "known": "Telefono"}) == "high"                # even a known device
    assert r.out(out, now + 60 + Recon.WINDOW_S) is None                   # too long after: not linked
    other = Recon()
    for k, port in enumerate(["22", "23", "80", "139", "445", "554", "3389", "8080", "9000"]):
        other.chatter("10.0.0.30", now + k, port)                         # another device looked around
    assert other.out(out, now + 30) is None
