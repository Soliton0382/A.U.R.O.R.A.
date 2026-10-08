# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's advice on the agents and routines, the ready-made sets and the colour themes (owner, 2026-10-08)."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import sys_routine_advice as A
from aurora import sys_routine_templates as T
from aurora import sys_routines

ROOT = Path(__file__).resolve().parents[1]


def _r(rid, title, kind="agent", at="07:00", **kw):
    return {"id": rid, "title": title, "kind": kind, "enabled": True, "schedule": {"every": "day", "at": at},
            **({"goal": title} if kind == "agent" else {}), **kw}


def test_the_code_finds_a_double_a_crowded_minute_a_failure_and_a_plugin_not_ready():
    rs = [_r("a", "Resoconto notturno degli alert del firewall"),
          _r("b", "Resoconto notturno del firewall", "tool", plugin="security", tool="security_night_report"),
          _r("c", "Bollettino meteo", "tool", plugin="weather", tool="weather_today"),
          _r("d", "Allerta meteo", "tool", "08:00", plugin="weather", tool="weather_alerts", last_ok=False, last_text="boom"),
          _r("e", "Spese", "tool", "09:00", plugin="expenses", tool="expense_summary")]
    out = A.checks(rs, {"security", "weather"})
    pause = {a["routine"] for a in out if a["action"] == "pause"}
    assert "b" in pause and "a" not in pause                    # the double: the tool one, the agent says more
    assert "e" in pause                                         # its plugin is not ready
    moved = [a for a in out if a["action"] == "change"]
    assert [a["change"]["schedule"]["at"] for a in moved] == ["07:30", "08:00"]   # 3 at 07:00: spread
    assert any(a["action"] == "run" and a["routine"] == "d" for a in out)


def test_aurora_s_proposals_are_checked_before_they_are_shown():
    rs = [_r("a", "Post del giorno", goal="pubblica")]
    reply = json.dumps([
        {"action": "change", "routine": "a", "title": "Correggi", "why": "x", "change": {"goal": "nuovo obiettivo"}},
        {"action": "change", "routine": "zzz", "title": "Inesistente", "change": {"goal": "x"}},
        {"action": "change", "routine": "a", "title": "Orario rotto", "change": {"schedule": {"every": "day", "at": "25:00"}}},
        {"action": "new", "routine": None, "title": "Agenda", "why": "y",
         "change": {"goal": "leggi l'agenda", "title": "Agenda", "plugins": ["calendar"],
                    "schedule": {"every": "custom", "times": ["07:15"], "group": "workdays"}, "notify": "if_any"}},
        {"action": "delete", "routine": "a", "title": "Cancella tutto"},
    ])
    llm = SimpleNamespace(complete=lambda *a, **k: SimpleNamespace(answer=reply))
    out = A.review(llm, rs, [{"name": "calendar", "tools": ["calendar_agenda"]}])
    assert [(a["action"], a["title"]) for a in out] == [("change", "Correggi"), ("new", "Agenda")]
    assert out[1]["change"]["kind"] == "agent"


def test_a_paused_routine_is_left_alone_by_aurora():
    seen = {}
    def complete(system, user, *a, **k):
        seen["user"] = user
        return SimpleNamespace(answer=json.dumps([{"action": "change", "routine": "p", "title": "x", "change": {"goal": "y"}}]))
    rs = [_r("a", "Attiva"), {**_r("p", "In pausa"), "enabled": False}]
    assert A.review(SimpleNamespace(complete=complete), rs, []) == []
    assert "PAUSED BY THE OWNER (leave them): «In pausa»" in seen["user"]


def test_apply_and_dismiss_are_kept(cfg):
    sys_routines.create(cfg, {"kind": "tool", "plugin": "weather", "tool": "weather_today", "title": "Meteo",
                              "schedule": {"every": "day", "at": "07:30"}})
    sys_routines.create(cfg, {"kind": "tool", "plugin": "weather", "tool": "weather_today", "title": "Meteo bis",
                              "schedule": {"every": "day", "at": "07:30"}})
    items = A.current(cfg, {"weather"})["items"]
    assert len(items) == 1 and items[0]["action"] == "pause"
    A.apply(cfg, items[0]["id"], {"weather"})
    assert [r["enabled"] for r in sys_routines.all_routines(cfg)] == [True, False]
    assert A.current(cfg, {"weather"})["items"] == []
    A.remember(cfg, [{"action": "new", "routine": None, "title": "Agenda", "why": "",
                      "change": {"kind": "agent", "goal": "agenda", "title": "Agenda",
                                 "schedule": {"every": "custom", "times": ["07:15"], "group": "all"}}}])
    new = A.current(cfg, {"weather"})["items"][0]
    out = A.apply(cfg, new["id"], {"weather"})
    assert out["routine"]["by"] == "aurora"
    A.remember(cfg, [{**new, "by": None}])                    # the same proposal again: not shown twice
    assert A.current(cfg, {"weather"})["items"] == []


def test_a_set_adds_only_what_is_missing_and_can_work(cfg):
    out = T.apply(cfg, "home", "it", {"weather", "calendar"}, admin=False)
    assert "☀️ Bollettino meteo ogni mattina" in out["created"] and "📅 L'agenda di oggi" in out["created"]
    assert {s["why"] for s in out["skipped"]} == {"missing"}             # email, expenses not ready
    again = T.apply(cfg, "home", "it", {"weather", "calendar"}, admin=False)
    assert again["created"] == [] and all(s["why"] in ("present", "missing") for s in again["skipped"])
    assert all(r["by"] == "template:home" for r in sys_routines.all_routines(cfg))


def test_the_admin_s_sets_and_routines_are_never_offered_to_a_user(cfg):
    ready = {"security", "facebook", "news", "diary", "netintel"}
    user_view = {p["id"]: p for p in T.view(cfg, "it", ready, admin=False)}
    assert "security" not in user_view
    assert not any(i["kind"] == "story" for i in user_view["social"]["items"])
    with pytest.raises(KeyError):
        T.apply(cfg, "security", "it", ready, admin=False)
    T.apply(cfg, "social", "it", ready, admin=False)
    assert not any(r["kind"] == "story" for r in sys_routines.all_routines(cfg))
    admin_view = {p["id"]: p for p in T.view(cfg, "it", ready, admin=True)}
    assert any(i["kind"] == "story" for i in admin_view["social"]["items"])


def test_my_configuration_becomes_a_set_without_the_machine_s_routines_for_others(cfg):
    sys_routines.create(cfg, {"kind": "tool", "plugin": "weather", "tool": "weather_today", "title": "Meteo",
                              "schedule": {"every": "day", "at": "07:30"}})
    sys_routines.create(cfg, {"kind": "tool", "plugin": "security", "tool": "threat_hunt", "title": "Caccia",
                              "schedule": {"every": "hours", "hours": 6}})
    saved = T.save_mine(cfg, "La mia configurazione", "owner1")
    pack = next(p for p in T.view(cfg, "it", {"weather", "security"}, admin=False, user="alice") if p["id"] == saved["id"])
    assert [i["title"] for i in pack["items"]] == ["Meteo"] and not pack["mine"]
    with pytest.raises(PermissionError):
        T.delete_saved(cfg, saved["id"], "alice", admin=False)
    T.delete_saved(cfg, saved["id"], "owner1", admin=False)


def test_every_built_in_routine_is_valid():
    for pack in json.loads((ROOT / "config" / "routine_templates.json").read_text())["packs"]:
        for spec in pack["routines"]:
            r = {k: spec[k] for k in T.KEEP if k in spec}
            r["title"] = T._text(spec["title"], "it")
            if "goal" in spec:
                r["goal"] = T._text(spec["goal"], "it")
            sys_routines.validate(r)


def test_routes_of_the_advice_and_sets_need_a_login():
    src = (ROOT / "aurora" / "api" / "routine_advice.py").read_text()
    routes = re.findall(r'@router\.\w+\("([^"]+)", dependencies=\[Depends\((\w+)\)\]\)', src)
    assert len(routes) == 7 and all(dep == "auth" for _, dep in routes)
    assert "/v1/aurora/plugins/signature\", dependencies=[Depends(admin_only)]" in (ROOT / "aurora" / "api" / "agents.py").read_text()


def test_the_themes_change_only_tokens_and_every_theme_has_its_words():
    css = (ROOT / "webui" / "css" / "themes.css").read_text()
    js = (ROOT / "webui" / "js" / "theme.js").read_text()
    ids = re.findall(r'id: "(\w+)"', js)
    for i in ids[1:]:
        assert f':root[data-theme="{i}"]' in css
    it = json.loads((ROOT / "webui" / "i18n" / "it_IT.json").read_text())
    en = json.loads((ROOT / "webui" / "i18n" / "en_US.json").read_text())
    assert all(f"theme.{i}" in it and f"theme.{i}" in en for i in ids)
    tokens = set(re.findall(r"(--[\w-]+):", (ROOT / "webui" / "app.css").read_text().split("}")[0]))
    assert set(re.findall(r"(--[\w-]+):", css)) <= tokens                 # a theme never invents a token
