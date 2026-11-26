# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The harvester's disk cap (owner, 26 Nov: «terrei 100 GB di soglia»): below it nothing new is taken, and the check
is made before every document, not once per round."""
import importlib
import sys
from pathlib import Path


def _svc(cfg, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda: cfg)            # the test's installation, never this machine's
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "script"))
    monkeypatch.delitem(sys.modules, "svc_harvester", raising=False)
    svc = importlib.import_module("svc_harvester")
    monkeypatch.delitem(sys.modules, "svc_harvester")
    return svc


def test_the_cap_defaults_to_100_gb_and_zero_switches_it_off(cfg, monkeypatch):
    svc = _svc(cfg, monkeypatch)
    assert cfg["AURORA_HARVEST_MIN_FREE_GB"] == 100
    monkeypatch.setattr(svc, "disk_free_gb", lambda: 99.5)
    assert svc.disk_low() == 99.5
    monkeypatch.setattr(svc, "disk_free_gb", lambda: 100.0)
    assert svc.disk_low() is None
    monkeypatch.setattr(svc, "cfg", {"AURORA_HARVEST_MIN_FREE_GB": 0, "AURORA_VAULT_DIR": cfg["AURORA_VAULT_DIR"]})
    monkeypatch.setattr(svc, "disk_free_gb", lambda: 1.0)
    assert svc.disk_low() is None


def test_free_space_is_read_on_the_vault_disk_even_before_the_vault_exists(cfg, monkeypatch):
    svc = _svc(cfg, monkeypatch)
    monkeypatch.setattr(svc, "cfg", {"AURORA_VAULT_DIR": str(Path(cfg["AURORA_VAULT_DIR"]) / "not" / "yet")})
    assert svc.disk_free_gb() > 0


def test_a_round_stops_at_the_document_that_finds_the_disk_full(cfg, monkeypatch):
    svc = _svc(cfg, monkeypatch)
    docs = [svc.kno_sources.Doc(key=f"k{i}", domain="physics", title=f"t{i}", origin="arxiv:x", licence="cc-by",
                                url="u", name="n", data=b"x") for i in range(5)]
    monkeypatch.setattr(svc.kno_sources, "specs", lambda c, d: [(0, {"source": "fake"})])
    monkeypatch.setattr(svc.kno_sources, "SOURCES", {"fake": lambda *a: docs})
    monkeypatch.setattr(svc.kno_sources, "load_state", lambda *a: {})
    monkeypatch.setattr(svc.kno_sources, "save_state", lambda *a: None)
    free = iter([500, 500, 50, 50, 50])
    monkeypatch.setattr(svc, "disk_free_gb", lambda: next(free))
    taken = []
    h = svc.Harvester.__new__(svc.Harvester)
    h.seen = set()
    monkeypatch.setattr(h, "take", lambda d: taken.append(d.key) or 1, raising=False)
    st = h.domain("physics", "exhaust")
    assert taken == ["k0", "k1"] and st["disk_low"] is True and st["new"] == 2
