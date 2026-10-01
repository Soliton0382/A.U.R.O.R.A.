# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import importlib.util
from pathlib import Path

from aurora.sec_sentinel import is_ips, parse

SERVER = Path(__file__).resolve().parents[2] / "plugins" / "security" / "server.py"
L = '2026-10-01T22:00:00.000+02:00 INFO aurora.firewall 10.0.0.1 <30>device_name="xg" '


def load(cfg, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    spec = importlib.util.spec_from_file_location("security_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_detector_and_the_plugin_share_one_ips_rule():
    assert is_ips(parse('log_type="ATP" log_subtype="Alert"'))
    assert is_ips(parse('log_type="IDP" signature_msg="x"')) and is_ips(parse('log_component="IPS"'))
    assert not is_ips(parse('log_type="Firewall" status="Denied"'))


def test_summary_counts_denied_sources_ports_and_threats(cfg, monkeypatch):
    s = load(cfg, monkeypatch).summary([
        L + 'log_type="Firewall" status="Denied" src_ip=192.168.1.20 dst_port=6667',
        L + 'log_type="Firewall" status="Denied" src_ip=192.168.1.20 dst_port=6667',
        L + 'log_type="Firewall" status="Allowed" src_ip=192.168.1.30 dst_port=443',
        L + 'log_type="ATP" log_subtype="Alert" message="destination match" src_ip=192.168.1.40 dst_ip=203.0.113.9'])
    assert s["lines"] == 4 and s["denied_sources"] == [("192.168.1.20", 2)] and s["denied_ports"] == [("6667", 2)]
    assert s["ips"] == [("ATP destination match → 203.0.113.9 da 192.168.1.40", 1)]
    assert dict(s["kinds"])[("Firewall", "Denied")] == 2
