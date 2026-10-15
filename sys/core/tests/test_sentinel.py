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


def test_closed_incidents_leave_the_page_but_stay_for_the_reports(cfg):
    from aurora.sec_incidents import Incidents
    inc = Incidents(cfg)
    a = inc.add({"kind": "port_scan", "source": "203.0.113.5", "count": 40})
    b = inc.add({"kind": "deny_burst", "source": "203.0.113.6", "count": 90})
    inc.update(a["id"], status="closed")
    assert inc.archive_closed() == 1 and inc.archive_closed() == 0          # once, the open one untouched
    assert [i["id"] for i in inc.list(archived=False)] == [b["id"]]       # the page
    assert {i["id"] for i in inc.list()} == {a["id"], b["id"]}            # the reports still see both


def test_pfsense_and_opnsense_filterlog_become_the_same_fields():
    """ROADMAP 108: the sentinel reads pfSense's and OPNsense's filterlog (CSV by position), in both syslog formats."""
    from aurora import sec_sentinel as S
    pf = ("<134>1 2026-10-16T12:00:00+02:00 pfSense.home.arpa filterlog 5577 - - 4,,,1000000103,vtnet0,match,block,in,4,"
          "0x0,,64,51234,0,DF,6,tcp,60,198.51.100.23,192.0.2.10,44123,22,0,S,123456,,64240,,mss")
    opn = ("<13>Oct 16 12:00:00 OPNsense.internal filterlog[1234]: 82,,,fae5593,vtnet0,match,pass,out,4,0x0,,64,0,0,DF,"
           "17,udp,76,192.0.2.11,198.51.100.1,53412,53,56")
    v6 = "filterlog[1]: 7,,,1000000105,vtnet0,match,block,in,6,0x00,0x00000,255,udp,17,52,2001:db8::1,2001:db8::2,5353,5353,52"
    a, b, c = S.parse(pf), S.parse(opn), S.parse(v6)
    assert (a["status"], a["src_ip"], a["dst_port"], a["protocol"]) == ("Deny", "198.51.100.23", "22", "tcp")
    assert (b["status"], b["src_ip"], b["dst_port"]) == ("Allow", "192.0.2.11", "53")
    assert (c["status"], c["src_ip"], c["dst_port"]) == ("Deny", "2001:db8::1", "5353")
    assert S.parse('log_type="Firewall" status="Deny" src_ip=1.2.3.4')["status"] == "Deny"     # the first dialect
    assert S.parse("filterlog[1]: not,a,line")["_raw"].startswith("filterlog")
