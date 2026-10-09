# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's colleague, 9 Oct: plugins «tutti spenti ma… c'è solo il pulsante spegni», and the weather asking for
coordinates («ma che ne so»)."""
import importlib
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def api(cfg, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "_cached", cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):                                   # the app's own order (svc_api)
        importlib.import_module(f"aurora.api.{name}")
    return SimpleNamespace(agents=importlib.import_module("aurora.api.agents"),
                           places=importlib.import_module("aurora.api.places"))


def test_a_plugin_on_that_does_not_start_says_why_from_its_stderr(api, cfg):
    logs = cfg.path("AURORA_LOG_DIR") / "plugins"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "weather.stderr.log").write_text("Traceback (most recent call last):\n  File \"x\", line 1\n"
                                             "bwrap: setting up uid map: Permission denied\n", encoding="utf-8")
    p = SimpleNamespace(name="weather", enabled=True, available=False, missing=[], error="MCPError: Connection closed")
    assert api.agents._why(p) == "MCPError: Connection closed — bwrap: setting up uid map: Permission denied"
    assert api.agents._why(SimpleNamespace(name="w", enabled=True, available=False, missing=["AURORA_X"], error="")) == ""


def test_switching_on_again_or_retry_forgets_the_remembered_failure(api, monkeypatch):
    from aurora import plg_host
    monkeypatch.setattr(plg_host, "_FAILED", {("weather", 1.0): (9e9, "Connection closed"), ("news", 1.0): (9e9, "x")})
    api.agents._forget_failure("weather")
    assert list(plg_host._FAILED) == [("news", 1.0)]


def test_a_town_gives_its_coordinates_and_region(api):
    def get(url, params):
        assert params["name"] == "Treviglio" and params["language"] == "it"
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": [
            {"name": "Treviglio", "latitude": 45.52098, "longitude": 9.59275, "admin1": "Lombardia", "admin2": "Bergamo",
             "country": "Italia"}]})
    assert api.places.search("Treviglio", "it", get) == [{"name": "Treviglio", "lat": 45.521, "lon": 9.5928,
                                                         "region": "Lombardia", "country": "Italia",
                                                         "label": "Treviglio, Bergamo, Lombardia, Italia"}]
