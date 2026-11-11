# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""12 Nov: Home Assistant's sun asked once a day, not at every routines' tick; a failure remembered for a while."""
import httpx
import pytest

from aurora import hom_auto as A


class _R:
    def raise_for_status(self):
        pass

    def json(self):
        return {"attributes": {"next_rising": "2099-01-02T07:44:00+00:00", "next_setting": "2099-01-01T18:28:00+00:00"}}


def test_the_sun_is_asked_once_a_day_and_a_failure_waits(cfg, monkeypatch):
    A._SUN.clear()
    cfg.values["AURORA_HA_URL"] = "http://ha.example:8123"
    calls = []
    monkeypatch.setattr(A.httpx, "get", lambda *a, **k: calls.append(k["timeout"]) or _R())
    first = A._sun(cfg)
    assert A._sun(cfg) == first and calls == [A.SUN_TIMEOUT_S]
    A._SUN.clear()

    def down(*a, **k):
        calls.append("down")
        raise httpx.ConnectError("away")
    monkeypatch.setattr(A.httpx, "get", down)
    for _ in range(3):
        with pytest.raises(httpx.HTTPError):
            A._sun(cfg)
    assert calls.count("down") == 1
    A._SUN.clear()
