# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Networks Aurora never reaches (sec_egress; owner, 2026-10-27): the list fetched and kept, written into the
services' units, and the sentinel's high incident when this machine goes there anyway."""
import subprocess
import sys
from pathlib import Path

from aurora import sec_egress as E, sec_incidents, sec_quiet, sys_config

ME = "192.0.2.101"


def test_the_list_is_fetched_collapsed_kept_and_kept_when_the_fetch_fails(cfg):
    cfg.values["AURORA_EGRESS_DENY_ASNS"] = ["64500", "64501"]
    got = E.refresh(cfg, fetch=lambda a: {64500: ["198.51.100.0/25", "198.51.100.128/25"], 64501: ["203.0.113.0/24", "2001:db8::/32"]}[a])
    assert got["asns"] == [64500, 64501] and got["prefixes"] == ["198.51.100.0/24", "203.0.113.0/24"]
    assert E.refresh(cfg, fetch=lambda a: 1 / 0, force=True)["prefixes"] == got["prefixes"]   # RIPEstat away
    deny = E.Deny(got["prefixes"])
    assert "198.51.100.77" in deny and "203.0.113.1" in deny and "192.0.2.1" not in deny and "bad" not in deny


def test_this_machine_towards_a_listed_network_is_a_high_incident_never_quieted(cfg, monkeypatch):
    cfg.values["AURORA_EGRESS_DENY_ASNS"] = ["64500"]
    E.refresh(cfg, fetch=lambda a: ["198.51.100.0/24"])
    monkeypatch.setattr(E, "holder", lambda ip: "curl")
    w = E.Watch(cfg, mine={ME})
    line = {"src_ip": ME, "dst_ip": "198.51.100.9", "dst_port": "443", "_raw": "x"}
    inc = w.feed(line, now=1000)
    assert inc["kind"] == "egress_deny" and inc["detail"]["process"] == "curl" and "198.51.100.9" in inc["detail"]["title"]
    assert w.feed(line, now=1500) is None                                   # once an hour per destination
    assert w.feed({**line, "src_ip": "192.0.2.50"}, now=9000) is None       # another device: not this check's
    assert w.feed({**line, "dst_ip": "192.0.2.9"}, now=9000) is None        # not listed
    assert sec_incidents.severity({**inc, "known": "PC"}) == "high"         # a named device does not lower it
    assert sec_quiet.pattern(inc) is None


def test_the_units_carry_the_list_and_the_reasoner_reaches_only_itself(cfg, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import sys_install_services as inst
    monkeypatch.setattr(sys_config, "get", lambda: cfg)
    from aurora import net_https
    monkeypatch.setattr(net_https.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    cfg.values["AURORA_EGRESS_DENY_ASNS"] = ["64500"]
    cfg.values["AURORA_LLM_HOST"] = "127.0.0.1"
    E.refresh(cfg, fetch=lambda a: ["198.51.100.0/24"])
    assert inst.main() == 0
    out = cfg.root / "sys/deploy/systemd"
    assert "IPAddressDeny=198.51.100.0/24" in (out / "aurora-api.service").read_text(encoding="utf-8")
    llm = (out / "aurora-llm.service").read_text(encoding="utf-8")
    assert "IPAddressDeny=any" in llm and "198.51.100.0/24" not in llm
