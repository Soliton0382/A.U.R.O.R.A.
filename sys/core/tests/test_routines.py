# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from aurora import sys_push, sys_routines as R

TZ = ZoneInfo("Europe/Rome")


@dataclass
class P:                                   # a plugin as the host lists it
    name: str
    manifest: dict = field(default_factory=dict)
    available: bool = True


def at(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 10, day, hh, mm, tzinfo=TZ)                    # 2026-10-05 is a Monday


def test_schedules_fire_once_per_slot():
    daily = {"enabled": True, "schedule": {"every": "day", "at": "07:30"}, "created": at(1, 12).timestamp(), "last_run": None}
    assert not R.is_due(daily, at(1, 20))                    # created after today's slot: waits for tomorrow
    assert R.is_due(daily, at(2, 7, 31))
    daily["last_run"] = at(2, 7, 31).timestamp()
    assert not R.is_due(daily, at(2, 23))
    assert R.is_due(daily, at(3, 7, 30))
    weekly = {"enabled": True, "schedule": {"every": "week", "weekday": 0, "at": "09:00"}, "created": at(1, 12).timestamp()}
    assert not R.is_due(weekly, at(4, 23)) and R.is_due(weekly, at(5, 9, 1))
    hourly = {"enabled": True, "schedule": {"every": "hours", "hours": 1}, "created": at(1, 12).timestamp(), "last_run": None}
    assert R.is_due(hourly, at(1, 12, 1))                    # runs at once, then every hour
    hourly["last_run"] = at(1, 12, 1).timestamp()
    assert not R.is_due(hourly, at(1, 12, 59)) and R.is_due(hourly, at(1, 13, 2))
    assert not R.is_due({**hourly, "enabled": False}, at(2, 0))


def test_notify_modes():
    r = {"notify": "if_new", "last_notified": "⛈️ temporale verso le 18:00"}
    assert not R.should_notify(r, "", True)
    assert not R.should_notify(r, "⛈️ temporale verso le 18:00", True)          # said once
    assert R.should_notify(r, "💨 raffiche fino a 70 km/h", True)
    assert not R.should_notify({"notify": "if_any"}, "NIENTE", True)
    assert not R.should_notify({"notify": "if_any"}, "Nothing new.", True)
    assert R.should_notify({"notify": "never"}, "", False)                      # a failure is always said
    assert R.should_notify({"notify": "always"}, "", True)


def test_validation():
    with pytest.raises(ValueError):
        R.validate({"kind": "tool", "plugin": "weather", "schedule": {"every": "day", "at": "07:30"}})
    with pytest.raises(ValueError):
        R.validate({"kind": "agent", "goal": "x", "schedule": {"every": "day", "at": "25:00"}})
    with pytest.raises(ValueError):
        R.validate({"kind": "agent", "goal": "x", "schedule": {"every": "minute"}})
    ok = R.validate({"kind": "agent", "goal": "x", "schedule": {"every": "week", "weekday": 6, "at": "08:00"}, "evil": 1})
    assert "evil" not in ok


def test_suggestions_become_routines_once_and_record(cfg):
    weather = P("weather", {"welcome": {"it": "ciao"}, "routines": [
        {"id": "alerts", "title": {"it": "Allerta meteo", "en": "Weather alerts"}, "kind": "tool", "tool": "weather_alerts",
         "args": {}, "schedule": {"every": "hours", "hours": 1}, "notify": "if_new", "event": "weather.alert"}]})
    off = P("github", {"routines": [{"id": "weekly", "kind": "agent", "goal": "x",
                                      "schedule": {"every": "week", "weekday": 0, "at": "09:00"}}]}, available=False)
    s = R.suggestions([weather, off], [])
    assert [x["suggestion"] for x in s] == ["weather/alerts"] and not s[0]["active"]
    r = R.from_suggestion(cfg, [weather, off], "weather/alerts", "it")
    assert r["title"] == "Allerta meteo" and r["plugin"] == "weather" and r["event"] == "weather.alert"
    assert R.suggestions([weather], R.all_routines(cfg))[0]["active"]
    with pytest.raises(ValueError):
        R.from_suggestion(cfg, [weather], "weather/alerts")
    _, notify = R.record(cfg, r["id"], "⛈️ temporale", True)
    assert notify
    _, notify = R.record(cfg, r["id"], "⛈️ temporale", True)
    assert not notify
    assert R.update(cfg, r["id"], {"enabled": False, "kind": "agent"})["kind"] == "tool"   # only owner fields change
    assert R.delete(cfg, r["id"]) and not R.all_routines(cfg)


def test_welcome_once_per_plugin(cfg):
    a, b = P("weather", {"welcome": {"it": "ciao"}}), P("github", {"welcome": {"it": "ciao"}}, available=False)
    assert [p.name for p in R.newly_ready(cfg, [a, b])] == ["weather"]
    assert R.newly_ready(cfg, [a, b]) == []
    b.available = True
    assert [p.name for p in R.newly_ready(cfg, [a, b])] == ["github"]


def test_new_notification_kinds_are_on_for_owners_who_chose_before(cfg):
    import json
    f = sys_push._dir(cfg) / "prefs.json"
    f.write_text(json.dumps({"push": ["incident"], "webui": ["incident", "dream"]}))    # saved before the new kinds
    p = sys_push.prefs(cfg)
    assert {"routine", "weather", "plugin"} <= set(p["push"]) and "thought" not in p["webui"]
    sys_push.set_prefs(cfg, {"push": ["incident"], "webui": ["incident"]})            # now he chose with them in sight
    assert sys_push.prefs(cfg) == {"push": ["incident"], "webui": ["incident"]}


def test_owners_who_never_chose_get_the_new_kinds_on_their_phone(cfg):
    p = sys_push.prefs(cfg)                                    # no prefs.json: AURORA_PUSH_EVENTS + the new kinds
    assert {"routine", "weather", "plugin"} <= set(p["push"]) and "thought" not in p["push"]


def test_a_routine_report_becomes_a_downloadable_pdf_and_a_failed_pdf_never_fails_it(cfg, monkeypatch, tmp_path):
    import logging
    from aurora import doc_pdf, sys_uploads
    events = []
    made = tmp_path / "20261002-report.pdf"
    monkeypatch.setattr(doc_pdf, "create", lambda title, text, lang, cfg: (made.write_bytes(b"%PDF"), made)[1])
    files = R.report_pdf(cfg, {"id": "r1", "title": "Resoconto notturno"}, "testo " * 50, "run1",
                         lambda e, p: events.append((e, p)), logging.getLogger("t"))
    assert files == [{"name": made.name, "url": f"/v1/aurora/documents/{made.name}", "mime": "application/pdf"}]
    assert events[-1][1]["ok"] is True
    assert any(f["name"] == made.name for f in sys_uploads.by_run(cfg, {"run1"})["run1"])   # shown with the turn
    monkeypatch.setattr(doc_pdf, "create", lambda *a: (_ for _ in ()).throw(RuntimeError("no chrome")))
    assert R.report_pdf(cfg, {"id": "r1"}, "x" * 300, "run2", lambda e, p: events.append((e, p)), logging.getLogger("t")) == []
    assert events[-1][1]["ok"] is False and "no chrome" in events[-1][1]["error"]


def test_a_routine_may_propose_actions_only_when_asked_and_only_with_a_true_or_false():
    spec = {"kind": "agent", "goal": "prepara un post", "schedule": {"every": "day", "at": "18:30"}}
    assert "propose" not in R.validate(spec)
    assert R.validate({**spec, "propose": True})["propose"] is True
    with pytest.raises(ValueError):
        R.validate({**spec, "propose": "yes"})
