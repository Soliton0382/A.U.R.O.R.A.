# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin's scheduled pause (owner, 2026-10-27): off by default; inside the window the plugin is not available,
so the routines skip it in silence and a call says until when it is paused."""
import json
import time

import pytest

from aurora import plg_away, plg_host


def _at(hm: str) -> float:
    """A moment today at HH:MM, local time."""
    h, m = map(int, hm.split(":"))
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, m, 0, 0, 0, -1))


@pytest.fixture
def host(cfg, tmp_path):
    d = tmp_path / "plugins" / "demo"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text(json.dumps({"name": "demo"}))
    cfg.values.update(AURORA_PLUGINS_DIR=str(d.parent))
    return plg_host.PluginHost(cfg)


def test_a_window_across_midnight_and_one_within_the_day():
    night = {"on": True, "from": "01:40", "to": "06:00"}
    assert plg_away.paused(night, _at("01:40")) and plg_away.paused(night, _at("05:59"))
    assert not plg_away.paused(night, _at("06:00")) and not plg_away.paused(night, _at("01:39"))
    late = {"on": True, "from": "23:30", "to": "02:00"}
    assert plg_away.paused(late, _at("23:45")) and plg_away.paused(late, _at("00:30"))
    assert not plg_away.paused(late, _at("12:00"))


def test_off_by_default_and_never_paused_when_off_or_unreadable():
    assert plg_away.clean(None) == plg_away.OFF
    assert not plg_away.paused({"on": False, "from": "00:00", "to": "23:59"}, _at("12:00"))
    assert not plg_away.paused({"on": True, "from": "25:00", "to": "06:00"}, _at("03:00"))
    with pytest.raises(ValueError):
        plg_away.clean({"on": True, "from": "03:00", "to": "03:00"})
    with pytest.raises(ValueError):
        plg_away.clean({"on": True, "from": "3", "to": "06:00"})


def test_inside_its_window_the_plugin_is_not_available_and_a_call_says_until_when(host, cfg, monkeypatch):
    assert host.get("demo").away == {} and not host.get("demo").paused
    now = time.localtime()
    start = f"{now.tm_hour:02d}:{now.tm_min:02d}"
    end = time.strftime("%H:%M", time.localtime(time.time() + 3600))
    assert host.set_away("demo", {"on": True, "from": start, "to": end}) == {"on": True, "from": start, "to": end}
    p = host.get("demo")
    assert p.paused and not p.available
    assert plg_away.paused(plg_away.of(cfg, "demo"))                   # the same window, read from the state alone
    out = host.call("demo", "anything", {})
    assert not out["ok"] and f"scheduled pause until {end}" in out["text"]
    host.set_away("demo", {"on": False, "from": start, "to": end})      # off again: the times stay for next time
    assert not host.get("demo").paused and host.get("demo").away["from"] == start
