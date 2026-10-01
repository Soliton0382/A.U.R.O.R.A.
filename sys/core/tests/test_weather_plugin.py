# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import importlib.util
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2] / "plugins" / "weather" / "server.py"


def load(cfg=None, monkeypatch=None):
    """The plugin reads its configuration at import: give it the test's own (never the machine's .env)."""
    if monkeypatch is not None:
        from aurora import sys_config
        monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    spec = importlib.util.spec_from_file_location("weather_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def series(n=8, **over):
    h = {"time": [f"2026-10-01T{12 + i:02d}:00" for i in range(n)], "pressure_msl": [1015.0] * n,
         "wind_gusts_10m": [10.0] * n, "precipitation": [0.0] * n, "weather_code": [2] * n, "temperature_2m": [20.0] * n}
    h.update(over)
    return {"hourly": h}


def test_a_quiet_day_says_nothing(cfg, monkeypatch):
    assert load(cfg, monkeypatch).local_alerts(series()) == []


def test_sudden_changes_are_said_with_their_time(cfg, monkeypatch):
    w = load(cfg, monkeypatch)
    out = w.local_alerts(series(pressure_msl=[1015, 1014, 1012, 1008, 1007, 1007, 1007, 1007],
                                wind_gusts_10m=[10, 20, 30, 72, 40, 10, 10, 10],
                                weather_code=[2, 2, 2, 3, 95, 95, 3, 2],
                                temperature_2m=[24, 24, 22, 15, 15, 15, 15, 15]))
    text = "\n".join(out)
    assert "pressione in calo molto rapido: 7.0 hPa in 3 ore (12:00→15:00)" in text
    assert "raffiche fino a 72 km/h verso le 15:00" in text
    assert "temporale previsto verso le 16:00" in text
    assert "temperatura in calo di 9 °C in 3 ore" in text


def test_errors_never_carry_the_coordinates(cfg, monkeypatch):
    import httpx
    import pytest
    w = load(cfg, monkeypatch)

    @w.tool
    def boom():
        raise httpx.ConnectError("failed for url 'https://api.open-meteo.com/v1/forecast?latitude=45.1&longitude=9.5'")
    with pytest.raises(Exception) as e:
        boom()
    assert "latitude" not in str(e.value) and "?…" in str(e.value)
