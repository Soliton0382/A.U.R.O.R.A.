# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Each plugin's small cache (owner, 2026-10-05): the same read, the result already obtained; never a write."""
import time

from aurora import plg_shadow as S


def test_only_declared_read_tools_are_kept():
    m = {"cache": {"forecast": 600, "*": 60}}
    assert S.ttl(m, "forecast", "read") == 600 and S.ttl(m, "now", "read") == 60
    assert S.ttl(m, "forecast", "external") == 0 and S.ttl(m, "forecast", "write_local") == 0
    assert S.ttl({}, "forecast", "read") == 0


def test_same_arguments_same_result_until_it_is_old(cfg, monkeypatch):
    S.put(cfg, "weather", "forecast", {"city": "Roma", "days": 2}, "sole")
    assert S.get(cfg, "weather", "forecast", {"days": 2, "city": "Roma"}, 600) == "sole"   # order of arguments irrelevant
    assert S.get(cfg, "weather", "forecast", {"city": "Milano", "days": 2}, 600) is None
    assert S.get(cfg, "news", "forecast", {"city": "Roma", "days": 2}, 600) is None        # another plugin's cache
    assert S.get(cfg, "weather", "forecast", {"city": "Roma", "days": 2}, 0) is None
    later = time.time() + 700
    monkeypatch.setattr(S.time, "time", lambda: later)
    assert S.get(cfg, "weather", "forecast", {"city": "Roma", "days": 2}, 600) is None
    assert S.stats(cfg)["weather"] == {"results": 1, "served": 1}
