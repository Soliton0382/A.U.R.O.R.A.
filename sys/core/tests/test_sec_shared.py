# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""ROADMAP 103: a shared network's traffic the firewall already refused is counted, told once a day, not an incident."""
from aurora import sec_intel, sec_shared

DENIED = ('<30>log_id="010302602002" log_type="Firewall" log_component="Appliance Access" log_subtype="Denied" '
          'src_ip="172.70.216.176" dst_ip="192.168.1.2" protocol="TCP" src_port=11853 dst_port=80')
ALLOWED = DENIED.replace('log_subtype="Denied"', 'log_subtype="Allowed"')


def incident(samples, source="172.70.216.176", kind="rule:scanning_firewall_rules"):
    return {"kind": kind, "source": source, "count": 50, "internal": False, "samples": samples}


def test_classify(cfg, monkeypatch):
    monkeypatch.setattr(sec_intel, "shared", lambda c, ip: "Cloudflare" if ip.startswith("172.70.") else "")
    assert sec_shared.classify(cfg, incident([DENIED] * 5)) == {
        "provider": "Cloudflare", "source": "172.70.216.176", "ports": [80], "lines": 50}
    assert sec_shared.classify(cfg, incident([DENIED, ALLOWED])) is None          # something got through: an incident
    assert sec_shared.classify(cfg, incident([DENIED], source="134.33.66.242")) is None   # not a shared network
    assert sec_shared.classify(cfg, incident([DENIED], kind="honeypot")) is None
    assert sec_shared.classify(cfg, incident([])) is None


def test_group_tells_once_a_day(cfg):
    g = {"provider": "Cloudflare", "source": "172.70.216.176", "ports": [80], "lines": 50}
    first = sec_shared.group(cfg, g, now=1_760_000_000)
    assert "Full (strict)" in first and "50 tentativi" in first
    assert sec_shared.group(cfg, {**g, "source": "172.70.1.1"}, now=1_760_000_100) == ""
    assert sec_shared.group(cfg, g, now=1_760_000_000 + 86400)                     # the next day: told again
    data = sec_shared._file(cfg).read_text()
    assert '"trips": 2' in data and "172.70.1.1" in data


def test_hint_other_ports():
    assert "Full (strict)" not in sec_shared.hint("Cloudflare", [22])
    assert "Google" in sec_shared.hint("Google", [3389])
