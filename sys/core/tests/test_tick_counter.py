# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C600: every routines' tick counted by day (api.log said only those over 10 s), and the tick no longer starts every
plugin to ask whether one is on (each start of the API: 4–5 s a user, up to 323 s once). Invented numbers only."""
import importlib
import json
import sys
import time
from datetime import datetime
from types import SimpleNamespace

from aurora import hom_auto, sys_config, sys_ticks


def _at(day: str, hms: str) -> float:
    return datetime.fromisoformat(f"{day}T{hms}").timestamp()


def test_every_tick_is_counted_and_the_first_of_a_new_day_closes_the_one_before(cfg):
    sys_ticks.record(cfg, 5.0, {"automations": 4.0, "scenes": 0.5}, now=_at("2031-03-03", "08:00:00"))
    sys_ticks.record(cfg, 31.5, {"automations": 30.9, "automations.due": 2.5}, now=_at("2031-03-03", "09:00:00"))
    sys_ticks.record(cfg, None, busy=True, now=_at("2031-03-03", "09:00:20"))
    sys_ticks.record(cfg, 12.0, {"local_ticks": 11.0}, deferred=True, now=_at("2031-03-03", "10:00:00"))
    today = sys_ticks.days(cfg)
    assert len(today) == 1 and today[0]["open"] and today[0]["ticks"] == 3
    closed = sys_ticks.record(cfg, 1.0, {"automations": 0.1}, now=_at("2031-03-04", "07:00:00"))
    assert closed["day"] == "2031-03-03"
    assert (closed["ticks"], closed["busy"], closed["deferred"], closed["over_slow"]) == (3, 1, 1, 1)
    assert closed["max_s"] == 31.5 and closed["max_at"] == "09:00:00" and closed["max_steps"]["automations"] == 30.9
    assert closed["steps"]["automations"] == {"max_s": 30.9, "sum_s": 34.9}
    assert sys_ticks.slowest_step(closed) == ("automations", 30.9)
    assert sys_ticks.summary(closed) == ("2031-03-03: 3 ticks, 1 over 30 s, longest 31.5 s, slowest step automations "
                                         "(30.9 s); 1 skipped while one ran")
    lines = (cfg.path("AURORA_STATUS_DIR") / sys_ticks.DAYS).read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["day"] == "2031-03-03"
    assert sys_ticks.last_day(cfg) == {"day": "2031-03-03", "ticks": 3, "over_slow": 1, "max_s": 31.5,
                                       "slowest_step": "automations", "slowest_step_s": 30.9, "busy": 1}
    both = sys_ticks.days(cfg)
    assert [d["day"] for d in both] == ["2031-03-03", "2031-03-04"] and both[-1]["open"]


def test_a_day_under_the_limit_reads_as_such(cfg):
    for h in range(8, 20):
        sys_ticks.record(cfg, 2.0 + h / 10, {"automations": 1.0 + h / 10}, now=_at("2031-05-05", f"{h:02d}:00:00"))
    closed = sys_ticks.record(cfg, 1.0, {}, now=_at("2031-05-06", "07:00:00"))
    assert closed["ticks"] == 12 and closed["over_slow"] == 0 and closed["max_s"] == 3.9


def test_the_automations_tick_hands_its_parts_to_the_routines_tick(cfg, monkeypatch):
    clock = iter(range(0, 1000, 3))                               # every reading 3 s later
    monkeypatch.setattr("time.monotonic", lambda: next(clock))
    monkeypatch.setattr(hom_auto, "due", lambda c: [])
    monkeypatch.setattr(hom_auto, "load", lambda c: {"automations": []})
    parts = {"automations.plugin": 1.0}
    assert hom_auto.tick(cfg, "u", None, spent=parts, prefix="automations.") == []
    assert parts == {"automations.plugin": 1.0, "automations.due": 3.0, "automations.load": 3.0}


class _Host:
    """A plugin host that refuses to start a plugin: the tick must ask without the tools."""

    def __init__(self, on=("homeassistant",)):
        self.on, self.asked = on, []

    def plugins(self, with_tools=True):
        self.asked.append(with_tools)
        assert with_tools is False, "the tick started every plugin to ask whether one is on"
        return [SimpleNamespace(name=n, available=True) for n in self.on]

    def get(self, name):
        raise AssertionError("get() lists every plugin's tools")


def _routines(cfg, monkeypatch):
    from aurora import hom_scenes
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    monkeypatch.setattr(hom_scenes, "_gate", hom_scenes._gate)   # api/home sets the scenes' gate: given back after
    import aurora
    if "aurora.api" in sys.modules:                             # the package's attribute given back too: `import
        monkeypatch.setattr(aurora, "api", sys.modules["aurora.api"])   # aurora.api.core as x` reads it after us
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    importlib.import_module("aurora.api.oai")                     # the app's own order (svc_api)
    return importlib.import_module("aurora.api.routines")


def test_the_tick_asks_whether_a_plugin_is_on_without_starting_the_plugins(cfg, monkeypatch):
    R = _routines(cfg, monkeypatch)
    from aurora import hom_scenes
    host = _Host()
    monkeypatch.setattr(R, "plugin_host", lambda *a: host)
    seen = []
    monkeypatch.setattr(hom_auto, "tick", lambda c, u, log, spent=None, prefix="": seen.append((u, prefix)) or [])
    monkeypatch.setattr(hom_scenes, "resume", lambda c, u, log: [])
    parts: dict = {}
    R._automations("u1", parts)
    R._scenes_again("u1", parts)
    R._astro_again("u1", parts)                                   # astro not there: nothing started
    assert seen == [("u1", "automations.")]
    assert host.asked == [False, False, False]
    assert {"automations.plugin", "scenes.plugin", "astro.plugin"} <= set(parts)
    off = _Host(on=())
    monkeypatch.setattr(R, "plugin_host", lambda *a: off)
    R._automations("u1", {})
    assert seen == [("u1", "automations.")]                       # Home Assistant off: not run


def test_a_whole_tick_is_counted_with_its_steps_and_their_parts(cfg, monkeypatch):
    R = _routines(cfg, monkeypatch)
    from aurora import sys_routines
    from aurora.api import assist, core
    monkeypatch.setattr(assist, "expire_due", lambda: None)
    monkeypatch.setattr(core, "trim_memory", lambda: None)
    monkeypatch.setattr(R, "everyone", lambda: ["u1", "u2"])
    monkeypatch.setattr(R, "_someone_talking", lambda: None)
    monkeypatch.setattr(R, "_automations", lambda who, parts: parts.update({"automations.due": 0.25}))
    for name in ("_anon_expired", "_people_first"):
        monkeypatch.setattr(R, name, lambda who: None)
    for name in ("_devices_if_due", "_scenes_again", "_astro_again", "_local_ticks"):
        monkeypatch.setattr(R, name, lambda who, parts: None)
    monkeypatch.setattr(R, "_welcome", lambda s: [])
    monkeypatch.setattr(sys_routines, "due", lambda c: [])
    assert R.routine_tick() == {"started": [], "welcomed": []}
    d = sys_ticks.days(cfg)[-1]
    assert d["day"] == time.strftime("%Y-%m-%d") and d["ticks"] == 1 and d["over_slow"] == 0
    assert {"automations", "automations.due", "scenes", "astro", "welcome"} <= set(d["steps"])


def test_the_scenes_gate_starts_no_plugin(cfg, monkeypatch):
    """C600, 20 Nov: with the automations fixed, the first tick after a start still waited 19.7 s in the scenes —
    hom_scenes.allowed() asked api/home's gate, which listed every plugin's tools."""
    _routines(cfg, monkeypatch)
    from aurora.api import home
    host = _Host()
    monkeypatch.setattr(home, "plugin_host", lambda *a: host)
    assert home._plugin_on() is True and host.asked == [False]
    monkeypatch.setattr(home, "plugin_host", lambda *a: _Host(on=()))
    assert home._plugin_on() is False


def test_each_local_extension_s_tick_is_timed(cfg, monkeypatch):
    import importlib.util
    import pytest
    if not importlib.util.find_spec("aurora.local"):
        pytest.skip("no extensions of this installation")
    R = _routines(cfg, monkeypatch)
    from aurora import local

    def watch_one(who):
        pass
    watch_one.__module__ = "aurora.local.ext_one"
    monkeypatch.setattr(local, "ticks", lambda: [watch_one])
    parts: dict = {}
    R._local_ticks("u1", parts)
    assert list(parts) == ["local_ticks.ext_one.watch_one"]
