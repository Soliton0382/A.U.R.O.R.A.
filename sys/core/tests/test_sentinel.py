# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from aurora.sec_sentinel import Detector, is_private, parse

DENY = 'device="SFW" log_type="Firewall" status="Deny" src_ip="203.0.113.7" dst_ip="192.168.1.10" dst_port={p} protocol="TCP"'


def test_parse_key_values():
    f = parse(DENY.format(p=22))
    assert f["log_type"] == "Firewall" and f["src_ip"] == "203.0.113.7" and f["dst_port"] == "22"


def test_port_scan_and_deny_burst_once_per_hour():
    d = Detector(window_s=300, deny_threshold=30, scan_ports=20)
    kinds = []
    for i in range(40):
        kinds += [x.kind for x in d.feed(parse(DENY.format(p=1000 + i)), now=1000 + i)]
    assert kinds == ["port_scan", "deny_burst"]                  # each raised once
    assert not d.feed(parse(DENY.format(p=5000)), now=1100)       # not again within the hour


def test_slow_denies_outside_the_window_raise_nothing():
    d = Detector(window_s=60, deny_threshold=5, scan_ports=50)
    assert all(not d.feed(parse(DENY.format(p=22)), now=i * 100) for i in range(20))


def test_ips_alert_and_internal_sources():
    d = Detector(300, 50, 20)
    inc = d.feed(parse('log_type="IDP" src_ip="192.168.1.50" signature_msg="ET SCAN Nmap" dst_port=445'), now=10)
    assert inc[0].kind == "ips_alert" and inc[0].internal and inc[0].detail["signature"] == "ET SCAN Nmap"
    assert is_private("10.0.0.1") and not is_private("203.0.113.7")
