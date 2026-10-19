# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A link's reputation before Aurora opens it (sec_linkcheck, the plugin linkcheck): refused with the services'
reasons; a service down is «not checked», never «clean»; the plugin switched off checks nothing."""
import json
import logging

import pytest

from aurora import sec_linkcheck as L


@pytest.fixture
def on(cfg, monkeypatch):
    cfg.values.update({"AURORA_LINKCHECK_VIRUSTOTAL": True, "AURORA_LINKCHECK_URLHAUS": True,
                       "AURORA_LINKCHECK_ABUSEIPDB": False, "AURORA_LINKCHECK_STRICT": False})
    return cfg


def test_a_malicious_link_is_refused_with_the_reason(on, monkeypatch):
    monkeypatch.setitem(L.CHECKS, "virustotal", lambda c, cfg, u: ("malicious", "VirusTotal: 7 motori lo dicono malevolo, 1 sospetto"))
    monkeypatch.setitem(L.CHECKS, "urlhaus", lambda c, cfg, u: ("clean", "URLhaus: non presente"))
    v = L.check("https://bad.example/login", on)
    assert v["blocked"] and v["level"] == "malicious" and "7 motori" in L.refusal(v)
    assert L.check("https://bad.example/login", on)["cached"]                 # a day in memory: the quota is small


def test_a_service_down_is_not_checked_and_never_clean(on, monkeypatch):
    def down(c, cfg, u):
        raise TimeoutError
    monkeypatch.setitem(L.CHECKS, "virustotal", down)
    monkeypatch.setitem(L.CHECKS, "urlhaus", lambda c, cfg, u: ("unknown", "URLhaus: nessuna chiave (abuse.ch, gratuita)"))
    v = L.check("https://fine.example/", on)
    assert not v["blocked"] and v["checked"] == ["form"] and any("non risponde" in r for r in v["reasons"])


def test_the_link_itself_hidden_credentials_and_two_suspicions(on, monkeypatch):
    assert L.form("https://bank.it@evil.example/")[0] == "suspicious"
    assert L.form("https://xn--pple-43d.com/")[0] == "suspicious"
    monkeypatch.setitem(L.CHECKS, "virustotal", lambda c, cfg, u: ("suspicious", "VirusTotal: 1 motore"))
    monkeypatch.setitem(L.CHECKS, "urlhaus", lambda c, cfg, u: ("clean", "URLhaus: non presente"))
    assert L.check("https://bank.it@evil2.example/", on)["blocked"]            # the form and a service: two suspicions


def test_switched_off_nothing_is_checked_and_an_agent_call_is_refused_when_on(on, monkeypatch):
    monkeypatch.setitem(L.CHECKS, "virustotal", lambda c, cfg, u: ("malicious", "VirusTotal: 9 motori"))
    monkeypatch.setitem(L.CHECKS, "urlhaus", lambda c, cfg, u: ("clean", "URLhaus: non presente"))
    seen = []
    out = L.tool_call(on, "web", {"url": "https://bad2.example/x"}, lambda e, p: seen.append(e), logging.getLogger("t"))
    assert out.startswith("REFUSED") and seen == ["link.refused"]
    assert L.tool_call(on, "web", {"query": "meteo"}, lambda e, p: None, logging.getLogger("t")) == ""
    (on.path("AURORA_STATUS_DIR") / "plugins.json").write_text(json.dumps({"linkcheck": {"enabled": False}}))
    assert not L.check("https://bad3.example/", on)["blocked"]


def test_a_read_only_status_folder_never_stops_the_check(on, monkeypatch):
    """C369: in a plugin's sandbox the status folder is read-only; the day's memory is lost, the verdict is not."""
    monkeypatch.setitem(L.CHECKS, "virustotal", lambda c, cfg, u: ("malicious", "VirusTotal: 5 motori"))
    monkeypatch.setitem(L.CHECKS, "urlhaus", lambda c, cfg, u: ("clean", "URLhaus: non presente"))

    def read_only(*a, **k):
        raise OSError(30, "Read-only file system")
    monkeypatch.setattr(L, "_write", read_only)
    assert L.check("https://ro.example/x", on)["blocked"]
