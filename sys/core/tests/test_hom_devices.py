# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A new device in Home Assistant gets its agents (owner, 2026-10-12): seen once, agents made for it and checked, never
a command to the device; proposed or created as the user's autonomy says."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from aurora import hom_devices as H
from aurora import sys_routine_advice, sys_routines

CAMERA = {"id": "cam1", "name": "Camera", "manufacturer": "Maker", "model": "C1", "entities": [
    {"entity_id": "camera.camera_live_view", "domain": "camera", "device_class": "", "unit": "", "name": "Live", "state": "idle"},
    {"entity_id": "switch.camera_person_detection", "domain": "switch", "device_class": "", "unit": "", "name": "Person",
     "state": "on"}]}
PRINTER = {"id": "prn1", "name": "Printer", "manufacturer": "Maker", "model": "P1", "entities": [
    {"entity_id": "sensor.printer", "domain": "sensor", "device_class": "", "unit": "", "name": "Printer", "state": "idle"}]}


class LLM:
    def __init__(self, items):
        self.items, self.asked = items, []

    def complete(self, system, user, max_tokens, think=None):
        self.asked.append(user)
        return SimpleNamespace(answer="Ecco:\n" + json.dumps(self.items))


GOOD = {"title": "📷 Rilevamento persone acceso", "icon": "📷", "schedule": {"every": "hours", "hours": 6}, "notify": "if_new",
        "goal": "Con homeassistant states('camera') controlla che switch.camera_person_detection sia on. Se non c'è niente "
                "da segnalare rispondi soltanto: NIENTE.", "why": "se si spegne non vedresti chi passa"}
BAD = {**GOOD, "title": "🔦 Accendi il LED", "goal": "Usa call_service switch.turn_on su switch.camera_led ogni sera."}


def test_a_device_is_new_once_and_forgotten_when_it_leaves(cfg):
    assert [d["id"] for d in H.new_devices(cfg, [CAMERA], now=100)] == ["cam1"]
    assert H.new_devices(cfg, [CAMERA, PRINTER], now=200) == [PRINTER]
    assert H.new_devices(cfg, [PRINTER], now=300) == []                     # the camera gone: forgotten
    assert H.new_devices(cfg, [CAMERA, PRINTER], now=400) == [CAMERA]       # and new again when it comes back


def test_the_agents_are_made_for_the_device_and_never_command_it(cfg):
    llm = LLM([GOOD, BAD, {"title": "", "goal": ""}])
    out = H.proposals(llm, CAMERA)
    assert "switch.camera_person_detection" in llm.asked[0] and "C1" in llm.asked[0]
    assert [p["title"] for p in out] == [GOOD["title"]]                     # the command and the empty one refused
    spec = out[0]["change"]
    assert spec["plugins"] == ["homeassistant"] and spec["kind"] == "agent" and spec["memory"] is True
    sys_routines.validate(spec)


def test_level_one_proposes_level_two_creates_zero_does_nothing(cfg):
    cfg.values["AURORA_HA_DEVICE_AGENTS"] = 1
    r = H.welcome(cfg, LLM([GOOD]), [CAMERA])
    assert r == {"new": ["Camera"], "proposed": 1, "created": []} and sys_routines.all_routines(cfg) == []
    advice = sys_routine_advice.current(cfg, {"homeassistant"})["items"]
    assert [a["title"] for a in advice] == [GOOD["title"]] and "Camera" in advice[0]["why"]
    assert sys_routine_advice._load(cfg).get("reviewed", 0) == 0            # Aurora's daily review not postponed
    assert "Applica" in H.message(r)
    cfg.values["AURORA_HA_DEVICE_AGENTS"] = 2
    r = H.welcome(cfg, LLM([GOOD]), [CAMERA, PRINTER])
    assert r["new"] == ["Printer"] and len(r["created"]) == 1
    assert sys_routines.all_routines(cfg)[0]["by"] == "aurora" and "creato" in H.message(r)
    cfg.values["AURORA_HA_DEVICE_AGENTS"] = 0
    assert not H.due(cfg)


def test_the_plugin_groups_entities_by_device_and_leaves_services_out():
    spec = importlib.util.spec_from_file_location(
        "ha_server", Path(__file__).resolve().parents[2] / "plugins" / "homeassistant" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = ("camera.c\tcam1\tCamera\tMaker\tC1\t\t\tLive\tidle\n"
            "switch.c_led\tcam1\tCamera\tMaker\tC1\t\t\tLED\toff\n"
            "sensor.t\tth1\tThermo\tMaker\tT1\ttemperature\t°C\tTemp\t21.5\n")
    devs = mod.grouped(text)
    assert [(d["name"], len(d["entities"])) for d in devs] == [("Camera", 2), ("Thermo", 1)]
    assert devs[1]["entities"][0] == {"entity_id": "sensor.t", "domain": "sensor", "device_class": "temperature",
                                      "unit": "°C", "name": "Temp", "state": "21.5"}
    assert "entry_type" in mod.DEVICES                                      # the sun, the backup… are not devices


def test_the_home_page_shows_each_device_with_its_agents_and_allows_only_simple_commands():
    routines = [{"id": "r1", "title": "📷 Rilevamento", "goal": "controlla switch.camera_person_detection", "enabled": True},
                {"id": "r2", "title": "☀️ Meteo", "goal": "il meteo"}]
    advice = [{"id": "a1", "action": "new", "title": "📶 Segnale", "why": "Camera: un segnale debole…"},
              {"id": "a2", "action": "new", "title": "🖨️ Toner", "why": "Printer: …"}]
    out = {d["name"]: d for d in H.watching([CAMERA, PRINTER], routines, advice)}
    assert [a["id"] for a in out["Camera"]["agents"]] == ["r1"] and [p["id"] for p in out["Camera"]["proposals"]] == ["a1"]
    assert out["Printer"]["agents"] == [] and [p["id"] for p in out["Printer"]["proposals"]] == ["a2"]
    assert "press" in H.ALLOWED["button"] and "toggle" in H.ALLOWED["switch"]
    assert "camera" not in H.ALLOWED and "script" not in H.ALLOWED and "automation" not in H.ALLOWED
