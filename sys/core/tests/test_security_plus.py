# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Security beyond blocking an address (owner, 2026-10-06): threat lists, each device's normal, decoys, Aurora's own
firewall, the week's report."""
import json

from aurora import sec_baseline, sec_hostfw, sec_incidents, sec_intel, sec_report


def test_threat_lists_parsed_and_looked_up(cfg):
    assert sec_intel.parse("spamhaus_drop", '{"cidr":"198.51.100.0/24","sblid":"SBL1"}\n{"type":"metadata"}') == ["198.51.100.0/24"]
    assert sec_intel.parse("feodo", "# comment\n203.0.113.7\n") == ["203.0.113.7"]
    f = sec_intel._file(cfg)
    f.write_text(json.dumps({"at": 1, "lists": {"spamhaus_drop": {"nets": ["198.51.100.0/24"]}, "feodo": {"nets": ["203.0.113.7"]}}}))
    sec_intel._cache["at"] = 0
    cfg.values["AURORA_INTEL_ENABLED"] = True
    # 198.51.100.x and 203.0.113.x are documentation ranges, not "global": the lookup refuses them like a private one
    assert sec_intel.lookup(cfg, "192.168.1.10") == []
    data = json.loads(f.read_text()); data["lists"]["feodo"]["nets"] = ["8.8.8.0/24"]; f.write_text(json.dumps(data)); sec_intel._cache["at"] = 0
    assert [h["list"] for h in sec_intel.lookup(cfg, "8.8.8.8")] == ["feodo"] and sec_intel.lookup(cfg, "9.9.9.9") == []
    assert sec_incidents.severity({"kind": "deny_burst", "source": "8.8.8.8", "intel_lists": [{"list": "feodo"}]}) == "high"
    assert sec_incidents.severity({"kind": "honeypot", "source": "192.0.2.9", "internal": True, "known": "pc"}) == "high"


def line(**k):
    return {"log_type": "Firewall", "src_zone": "LAN", "src_mac": "AA:BB:CC:00:00:01", "src_ip": "192.0.2.20",
            "dst_country": "ITA", "dst_port": "443", "app_name": "HTTPS", "bytes_sent": "1000", "_raw": "x", **k}


def test_a_device_learns_its_normal_then_says_what_is_new(cfg):
    b = sec_baseline.Baseline(cfg, days=7)
    t0 = 1_800_000_000.0
    b.state["since"] = t0
    assert b.feed(line(), now=t0) == [] and b.feed(line(dst_country="USA", dst_port="993"), now=t0 + 3600) == []   # learning
    later = t0 + 8 * 86400
    kinds = [i["kind"] for i in b.feed(line(dst_country="RUS", dst_port="4444"), now=later)]
    assert kinds == ["behaviour:new_country", "behaviour:new_port"]
    assert b.feed(line(dst_country="RUS", dst_port="4444"), now=later + 60) == []                  # said once
    assert [i["kind"] for i in b.feed(line(src_mac="AA:BB:CC:00:00:99", src_ip="192.0.2.99"), now=later)] == ["behaviour:new_device"]
    for d in range(3):                                   # usual days of ~1 KB, then 2 GB in one day
        b.feed(line(bytes_sent="1000"), now=later + (d + 1) * 86400)
    big = b.feed(line(bytes_sent=str(2 * 2**30)), now=later + 5 * 86400)
    assert [i["kind"] for i in big] == ["behaviour:upload"]


def test_aurora_s_firewall_never_blocks_a_protected_address(cfg):
    cfg.values["AURORA_DEFENCE_PROTECTED"] = "192.0.2.205"
    assert sec_hostfw.never(cfg, "192.0.2.205") == "a protected address"
    assert sec_hostfw.never(cfg, "127.0.0.1") and sec_hostfw.never(cfg, "not-an-ip")
    assert sec_hostfw.never(cfg, "192.0.2.30") == ""
    cfg.values["AURORA_HOSTFW"] = False
    assert sec_hostfw.block(cfg, "192.0.2.30", "test") == {"ok": False, "why": "AURORA_HOSTFW off"}


def test_the_week_has_a_score_and_campaigns(cfg):
    inc = sec_incidents.Incidents(cfg)
    inc.add({"kind": "port_scan", "source": "8.8.4.4", "count": 10})
    inc.add({"kind": "port_scan", "source": "8.8.4.9", "count": 5})
    r = sec_report.week(cfg)
    assert r["incidents"] == 2 and r["campaigns"][0]["network"] == "8.8.4.0/24" and r["score"] < 100
    assert "punteggio" in sec_report.text(r)
