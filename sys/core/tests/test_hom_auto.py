# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🪄 The home's automations (hom_auto): any device the 🏠 page allows, at a time, at sunrise or sunset with an offset,
on chosen days; once a day, a missed time still run within the window, never twice; one failed action not the end."""
from datetime import timedelta

import httpx
import pytest

from aurora import hom_auto as A
from aurora import hom_scenes, sns_clock

PLUGS = [{"entity_id": "switch.presa_ulivo", "service": "turn_on"},
         {"entity_id": "light.palla_giardino", "service": "turn_on", "data": {"brightness_pct": 140}}]


def test_only_what_the_home_page_allows_is_saved(cfg):
    a = A.save(cfg, {"name": "Luci del giardino", "when": {"type": "time", "at": "19:30", "days": [0, 1, 2, 3, 4]},
                     "actions": PLUGS + [{"scene": "Natale"}]})
    assert a["actions"][1]["data"] == {"brightness_pct": 100} and a["when"]["days"] == [0, 1, 2, 3, 4]
    assert A.save(cfg, {**a, "name": "Giardino"})["id"] == a["id"] and len(A.load(cfg)["automations"]) == 1
    for bad in ({"entity_id": "lock.porta", "service": "open"}, {"entity_id": "shell_command.x", "service": "run"}):
        with pytest.raises(A.AutoError):
            A.save(cfg, {"name": "x", "actions": [bad]})
    with pytest.raises(A.AutoError):
        A.save(cfg, {"name": "x", "when": {"type": "time", "at": "25:00"}, "actions": PLUGS})


def test_a_time_runs_once_a_missed_one_within_the_window_and_on_its_days_only(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(hom_scenes, "_ha", lambda c, path, body: sent.append((path, body["entity_id"])))
    now = sns_clock.now(cfg).replace(hour=19, minute=40, second=0, microsecond=0)
    a = A.save(cfg, {"name": "Sera", "when": {"type": "time", "at": "19:30"}, "actions": PLUGS})
    assert [x["name"] for x in A.due(cfg, now)] == ["Sera"]                          # 10 min late: still run
    A.run(cfg, A.due(cfg, now)[0], now=now)
    assert sent == [("switch/turn_on", "switch.presa_ulivo"), ("light/turn_on", "light.palla_giardino")]
    assert A.due(cfg, now) == [] and A.load(cfg)["automations"][0]["last_ok"]          # never twice
    assert A.due(cfg, now.replace(hour=20, minute=0)) == []                           # 30 min late: no
    A.save(cfg, {**a, "when": {"type": "time", "at": "19:30", "days": [(now.weekday() + 1) % 7]}, "last": None})
    assert A.due(cfg, now) == []                                                       # not one of its days


def test_the_sun_with_its_offset_and_a_failed_action_is_not_the_end(cfg, monkeypatch):
    now = sns_clock.now(cfg).replace(hour=18, minute=5, second=0, microsecond=0)
    monkeypatch.setattr(A, "_sun", lambda c: {"sunrise": now.replace(hour=7, minute=44), "sunset": now.replace(hour=18, minute=28)})
    A.save(cfg, {"name": "Prima del tramonto", "when": {"type": "sunset", "offset_min": -30}, "actions": PLUGS})
    assert A.at_today(cfg, A.load(cfg)["automations"][0]) == now.replace(hour=17, minute=58)
    assert [x["name"] for x in A.due(cfg, now)] == ["Prima del tramonto"]

    def ha(c, path, body):
        if body["entity_id"].startswith("switch"):
            raise httpx.ConnectError("away")
    monkeypatch.setattr(hom_scenes, "_ha", ha)
    out = A.run(cfg, A.due(cfg, now)[0], now=now)
    assert out["done"] == ["light.palla_giardino turn_on"] and "switch.presa_ulivo" in out["failed"][0]
    assert "non riuscite" in A.load(cfg)["automations"][0]["last_text"]
    assert A.due(cfg, now + timedelta(minutes=1)) == []


def test_a_white_with_its_warmth_and_a_scene_started_then_stopped(cfg, monkeypatch):
    a = A.save(cfg, {"name": "Natale", "when": {"type": "sunset"}, "actions": [
        {"entity_id": "light.palla", "service": "turn_on", "data": {"brightness_pct": 15, "color_temp_kelvin": 9000}},
        {"scene": "Natale"}, {"scene": "Natale", "stop": True}]})
    assert a["actions"][0]["data"] == {"brightness_pct": 15, "color_temp_kelvin": 6500}
    seen = []
    monkeypatch.setattr(hom_scenes, "_ha", lambda c, path, body: seen.append(("ha", path, body)))
    monkeypatch.setattr(hom_scenes, "start", lambda c, name, user, log=None: seen.append(("start", name)))
    monkeypatch.setattr(hom_scenes, "stop_scene", lambda c, name, user: seen.append(("stop", name)))
    out = A.run(cfg, a)
    assert seen == [("ha", "light/turn_on", {"entity_id": "light.palla", "brightness_pct": 15, "color_temp_kelvin": 6500}),
                    ("start", "Natale"), ("stop", "Natale")] and out["done"][2] == "Natale stop"


def test_a_scene_on_chosen_lights_grouped_and_a_light_off_stops_it(cfg, monkeypatch):
    a = A.save(cfg, {"name": "Natale", "when": {"type": "sunset"}, "actions": [
        {"entity_id": "light.palla_grande", "service": "scene", "scene_name": "natale"},
        {"entity_id": "switch.presa", "service": "turn_on"},
        {"entity_id": "light.palla_piccola", "service": "scene", "scene_name": "natale"},
        {"entity_id": "light.suprema", "service": "scene", "scene_name": "colorful"}]})
    seen = []
    monkeypatch.setattr(hom_scenes, "_ha", lambda c, path, body: seen.append(("ha", path)))
    monkeypatch.setattr(hom_scenes, "start", lambda c, name, user, log=None, lights=None: seen.append(("start", name, lights)))
    monkeypatch.setattr(hom_scenes, "stop_on", lambda c, lights, user="": seen.append(("stop_on", lights)))
    A.run(cfg, a)
    assert seen == [("start", "natale", ["light.palla_grande", "light.palla_piccola"]), ("ha", "switch/turn_on"),
                    ("start", "colorful", ["light.suprema"])]                   # one start for the two balls
    seen.clear()
    off = A.save(cfg, {"name": "Notte", "actions": [{"entity_id": "light.palla_grande", "service": "turn_off"}]})
    A.run(cfg, off)
    assert seen == [("stop_on", ["light.palla_grande"]), ("ha", "light/turn_off")]


def test_a_normal_white_is_set_once_and_a_scene_runs_on_the_lights_given(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(hom_scenes, "_ha", lambda c, path, body: sent.append(body))
    s = hom_scenes.save(cfg, "Luce normale", ["light.palla_grande"], ["3000K"], brightness=15)
    assert s["colours"] == ["k3000"] and hom_scenes.step(s, 0)[0][1] == {"brightness_pct": 15, "color_temp_kelvin": 3000}
    import threading
    stop = threading.Event()
    hom_scenes._run(cfg, "", "luce normale", {**s, "every_s": 0.01, "lights": ["light.a", "light.b"]}, stop, 0, None)
    assert [b["entity_id"] for b in sent] == ["light.a", "light.b"]               # once, not every few seconds


def test_off_from_the_page_switches_off_the_light_a_white_scene_was_tried_on(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(hom_scenes, "_ha", lambda c, path, body: sent.append((path, body)))
    hom_scenes.save(cfg, "Ordinaria", [], ["3125K"], brightness=15)
    import threading
    hom_scenes._run(cfg, "", "ordinaria", {**hom_scenes.find(cfg, "ordinaria")[1], "lights": ["light.s"]}, threading.Event(), 0, None)
    assert not hom_scenes.stop_scene(cfg, "ordinaria", "", True)              # a white: over at once, nothing running
    hom_scenes.stop_on(cfg, ["light.s"], "")
    hom_scenes._ha(cfg, "light/turn_off", {"entity_id": ["light.s"]})        # what the page's ⏹ does after it
    assert sent[-1] == ("light/turn_off", {"entity_id": ["light.s"]}) and sent[0][1]["color_temp_kelvin"] == 3125
