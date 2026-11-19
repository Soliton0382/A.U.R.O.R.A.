# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import time

import pytest

from aurora import hom_scenes as H

LIGHTS = ["light.giardino_1", "light.giardino_2"]


def test_a_scene_is_saved_found_by_its_name_and_its_colours_move_along(cfg):
    s = H.save(cfg, "Scenario di Natale", LIGHTS, ["rosso", "verde", [42, 85], "bianco caldo"], every_s=1)
    assert s["every_s"] == H.MIN_EVERY_S                               # never faster than a cloud bulb takes
    k, found = H.find(cfg, "natale")
    assert k == "natale" and found["lights"] == LIGHTS
    first, second = H.step(found, 0), H.step(found, 1)
    assert first[0][1]["hs_color"] == [0, 100] and first[1][1]["hs_color"] == [120, 100]      # chase: each its own
    assert second[0][1]["hs_color"] == [120, 100] and second[1][1]["hs_color"] == [42, 85]
    assert H.step(found, 2)[1][1]["color_temp_kelvin"] == 2700
    with pytest.raises(H.SceneError):
        H.save(cfg, "x", ["switch.presa"], ["rosso"])
    with pytest.raises(H.SceneError):
        H.colour("verdolino")
    assert H.colour("#ff0000") == (0, 100)


def test_the_agent_starts_only_what_it_may_and_a_scene_stops(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(H, "_ha", lambda c, path, body: sent.append((path, body)))
    assert H.tool(cfg, {"action": "save", "name": "Natale", "lights": LIGHTS, "colours": ["rosso", "verde"]}, False).startswith("SAVED")
    assert "REFUSED" in H.tool(cfg, {"action": "start", "name": "natale"}, False) and not sent
    assert H.tool(cfg, {"action": "start", "name": "natale"}, True).startswith("STARTED")
    for _ in range(50):
        if len(sent) >= 2:
            break
        time.sleep(0.02)
    assert {b["entity_id"] for _, b in sent[:2]} == set(LIGHTS)
    assert "running" in H.tool(cfg, {"action": "list"}, True) and H.load(cfg)["running"]
    assert H.tool(cfg, {"action": "stop", "name": "natale", "off": True}, True) == "STOPPED."
    assert sent[-1] == ("light/turn_off", {"entity_id": LIGHTS}) and not H.load(cfg)["running"]


def test_a_scene_running_when_the_api_stopped_starts_again_unless_its_time_is_over(cfg, monkeypatch):
    monkeypatch.setattr(H, "_ha", lambda c, path, body: None)
    H.save(cfg, "Natale", LIGHTS, ["rosso"])
    H.save(cfg, "Festa", LIGHTS, ["blu"])
    data = H.load(cfg)
    data["running"] = {"natale": {"since": 1, "until": 0}, "festa": {"since": 1, "until": time.time() - 5}}
    H._save(cfg, data)
    assert H.resume(cfg) == ["natale"] and "festa" not in H.load(cfg)["running"]
    H.stop_scene(cfg, "natale")


def test_any_user_picks_plugs_too_and_they_follow_the_scene(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(H, "_ha", lambda c, path, body: sent.append((path, body)))
    H.save(cfg, "Cena", [], [], switches=["switch.presa_tavolo"])          # no light: no colour needed
    with pytest.raises(H.SceneError):
        H.save(cfg, "Cena", ["light.a"], [])                                # lights need a colour
    H.start(cfg, "cena")
    for _ in range(50):
        if sent:
            break
        time.sleep(0.02)
    assert sent[0] == ("switch/turn_on", {"entity_id": "switch.presa_tavolo"})
    H.stop_scene(cfg, "cena", off=True)
    assert sent[-1] == ("switch/turn_off", {"entity_id": "switch.presa_tavolo"})


def test_a_scene_ends_when_its_plugin_is_switched_off_and_does_not_come_back(cfg, monkeypatch):
    on = [True]
    sent = []
    monkeypatch.setattr(H, "_ha", lambda c, path, body: sent.append(path))
    monkeypatch.setattr(H, "_gate", lambda: on[0])
    H.save(cfg, "Natale", LIGHTS, ["rosso", "verde"], every_s=3, minutes=5)
    H.start(cfg, "natale", "u")
    for _ in range(100):
        if sent:
            break
        time.sleep(0.01)
    assert sent and H.running("u") == ["natale"]
    on[0] = False
    data = H.load(cfg)["running"]["natale"]
    H._running[("u", "natale")].set()                      # wakes the wait the way a next round would
    for _ in range(100):
        if not H.running("u"):
            break
        time.sleep(0.01)
    assert not H.running("u")
    stored = H.load(cfg)
    stored["running"]["natale"] = data
    H._save(cfg, stored)
    assert H.resume(cfg, "u") == [] and not H.running("u")


def test_the_loop_itself_sends_nothing_with_the_plugin_off(cfg, monkeypatch):
    import threading
    sent = []
    monkeypatch.setattr(H, "_ha", lambda c, path, body: sent.append(path))
    monkeypatch.setattr(H, "_gate", lambda: False)
    H.save(cfg, "Natale", LIGHTS, ["rosso", "verde"], every_s=3)
    _, scene = H.find(cfg, "natale")
    H._run(cfg, "u", "natale", scene, threading.Event(), 0, None)      # returns at once: it would otherwise never end
    assert sent == []


def test_a_failed_look_at_the_plugin_does_not_stop_the_lights(monkeypatch):
    def broken():
        raise RuntimeError("host busy")
    monkeypatch.setattr(H, "_gate", broken)
    assert H.allowed()


def test_the_admin_reaches_a_scene_started_for_nobody_and_others_do_not():
    assert H.owners("anna", "anna") == ["anna", ""]
    assert H.owners("bruno", "anna") == ["bruno"]
    assert H.owners("", "anna") == [""]
