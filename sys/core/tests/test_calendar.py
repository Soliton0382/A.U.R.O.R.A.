# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own calendar (owner, 2026-10-08, roadmap 68): sealed on the disk, repeats at the same wall time across
summer time, one occurrence skipped, the alerts told once (late, snoozed, answered), the dates from the user's words
computed by the code, an .ics out and back in, and the chat's tools."""
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from aurora import cal_external, cal_store, cal_text, sys_config, sys_push, sys_seal

ROME = ZoneInfo("Europe/Rome")
PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "calendar"


@pytest.fixture
def cal(cfg):
    cfg.values.update(AURORA_TIMEZONE="Europe/Rome", AURORA_CALENDAR_ICS_URLS="", AURORA_CALDAV_URL="")
    cal_store.ready(cfg)
    return cfg


def _occ(cfg, a, b):
    return cal_store.occurrences(cfg, datetime.fromisoformat(a).replace(tzinfo=ROME), datetime.fromisoformat(b).replace(tzinfo=ROME))


def test_items_are_sealed_on_the_disk_and_read_back(cal):
    it = cal_store.add(cal, {"title": "Dentista dott. Rossi", "start": "2026-10-12 15:00", "minutes": 45, "location": "Via Roma 3"})
    raw = (cal.path("AURORA_CALENDAR_DIR") / "events.sealed").read_bytes()
    assert raw.startswith(sys_seal.MAGIC) and b"Dentista" not in raw and b"Rossi" not in raw
    assert cal_store.get(cal, it["id"])["end"] == "2026-10-12T15:45" and it["alerts"] == [30]
    o = _occ(cal, "2026-10-12T00:00", "2026-10-13T00:00")
    assert [x["start_iso"] for x in o] == ["2026-10-12T15:00:00+02:00"]


def test_a_weekly_appointment_stays_at_its_hour_across_summer_time(cal):
    """Rome leaves summer time on 25 Oct 2026: the 10:00 of the 26th is +01:00, still 10:00 on the wall."""
    cal_store.add(cal, {"title": "Palestra", "start": "2026-10-19T10:00", "minutes": 60, "repeat": "weekly"})
    o = _occ(cal, "2026-10-19T00:00", "2026-11-03T00:00")
    assert [x["start_iso"] for x in o] == ["2026-10-19T10:00:00+02:00", "2026-10-26T10:00:00+01:00", "2026-11-02T10:00:00+01:00"]
    assert all(x["end_iso"][11:16] == "11:00" for x in o)


def test_repeats_end_by_date_or_count_and_a_skipped_occurrence_is_gone(cal):
    a = cal_store.add(cal, {"title": "Pillola", "kind": "reminder", "start": "2026-10-10T08:00",
                            "repeat": {"freq": "daily", "until": "2026-10-13"}})
    b = cal_store.add(cal, {"title": "Corso", "start": "2026-10-10T18:00",
                            "repeat": {"freq": "weekly", "days": ["MO", "WE"], "count": 3}})
    o = _occ(cal, "2026-10-01T00:00", "2026-11-30T00:00")
    assert [x["at"] for x in o if x["id"] == a["id"]] == ["2026-10-10T08:00", "2026-10-11T08:00", "2026-10-12T08:00", "2026-10-13T08:00"]
    assert [x["at"][:10] for x in o if x["id"] == b["id"]] == ["2026-10-12", "2026-10-14", "2026-10-19"]
    cal_store.delete(cal, a["id"], "2026-10-11T08:00")
    o = _occ(cal, "2026-10-01T00:00", "2026-11-30T00:00")
    assert "2026-10-11T08:00" not in [x["at"] for x in o if x["id"] == a["id"]] and len([x for x in o if x["id"] == a["id"]]) == 3
    cal_store.delete(cal, a["id"])
    assert cal_store.get(cal, a["id"]) is None


def test_moving_keeps_the_length_and_bad_input_is_refused(cal):
    it = cal_store.add(cal, {"title": "Riunione", "start": "2026-10-12T09:00", "end": "2026-10-12T10:30"})
    moved = cal_store.update(cal, it["id"], {"start": "2026-10-13T14:00"})
    assert (moved["start"], moved["end"]) == ("2026-10-13T14:00", "2026-10-13T15:30") and moved["created"] == it["created"]
    assert cal_store.update(cal, it["id"], {"title": "Riunione Q4"})["end"] == "2026-10-13T15:30"
    for bad in ({"title": "", "start": "2026-10-12T09:00"}, {"title": "x", "start": "domani"},
                {"title": "x", "start": "2026-10-12T09:00", "end": "2026-10-12T08:00"},
                {"title": "x", "start": "2026-10-12T09:00", "repeat": "hourly"}):
        with pytest.raises(ValueError):
            cal_store.add(cal, bad)
    with pytest.raises(KeyError):
        cal_store.update(cal, "e-none", {"title": "y"})


def test_an_alert_is_told_once_late_up_to_12_hours_snoozed_and_answered(cal):
    it = cal_store.add(cal, {"title": "Dentista", "start": "2026-10-12T15:00", "alerts": [30, 0]})
    at = lambda hm: datetime.fromisoformat(f"2026-10-12T{hm}").replace(tzinfo=ROME)   # noqa: E731
    assert cal_store.due(cal, at("14:29")) == []
    first = cal_store.due(cal, at("14:30"))
    assert [(d["item"]["id"], d["minutes"], d["late"]) for d in first] == [(it["id"], 30, False)]
    assert "tra 30 minuti (15:00)" in cal_text.alert_text(first[0], at("14:30"))
    assert cal_store.due(cal, at("14:31")) == []                                    # once
    assert [d["key"] for d in cal_store.pending(cal, at("14:40"))] == [first[0]["key"]]
    cal_store.answer(cal, first[0]["key"], snooze_min=10, now=at("14:40"))
    assert cal_store.pending(cal, at("14:41")) == []
    again = cal_store.due(cal, at("14:50"))
    assert [d["key"] for d in again] == [first[0]["key"]] and again[0].get("snoozed")
    cal_store.answer(cal, first[0]["key"], now=at("14:51"))
    assert cal_store.pending(cal, at("14:52")) == []
    late = cal_store.due(cal, at("20:00"))                                           # Aurora was off at 15:00
    assert [(d["minutes"], d["late"]) for d in late] == [(0, True)]
    other = cal_store.add(cal, {"title": "Vecchio", "start": "2026-10-11T06:00", "alerts": [0]})
    assert all(d["item"]["id"] != other["id"] for d in cal_store.due(cal, at("20:01")))   # 38 h late: not told


def test_the_user_s_words_become_dates_computed_by_the_code():
    now = datetime(2026, 10, 8, 16, 0, tzinfo=ROME)                                   # a Thursday
    cases = {"domani alle 9": ("2026-10-09T09:00", True), "venerdì 18:30": ("2026-10-09T18:30", True),
             "giovedì prossimo ore 10": ("2026-10-15T10:00", True), "12/10 ore 15": ("2026-10-12T15:00", True),
             "2026-11-02 08:15": ("2026-11-02T08:15", True), "stasera alle 8": ("2026-10-08T20:00", True),
             "dopodomani": ("2026-10-10T00:00", False), "9": ("2026-10-09T09:00", True), "17:30": ("2026-10-08T17:30", True),
             "3/1": ("2027-01-03T00:00", False), "tomorrow 7pm": ("2026-10-09T19:00", True)}
    for words, want in cases.items():
        assert cal_text.when(words, now) == want, words
    for bad in ("", "boh", "domani alle 25"):
        with pytest.raises(ValueError):
            cal_text.when(bad, now)


def test_an_ics_goes_out_and_comes_back_the_same(cal):
    cal_store.add(cal, {"title": "Cena, con; amici \\ e \"altro\" " + "x" * 120, "start": "2026-10-16T20:00",
                        "minutes": 120, "notes": "riga 1\nriga 2", "location": "Trattoria"})
    w = cal_store.add(cal, {"title": "Yoga", "start": "2026-10-13T19:00", "repeat": {"freq": "weekly", "days": ["TU", "TH"], "until": "2026-12-31"}})
    cal_store.delete(cal, w["id"], "2026-10-15T19:00")
    cal_store.add(cal, {"title": "Compleanno Anna", "start": "2026-11-05", "all_day": True, "repeat": "yearly"})
    text = cal_text.to_ics(cal_store.items(cal), ROME)
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert "RRULE:FREQ=WEEKLY;INTERVAL=1;UNTIL=20261231;BYDAY=TU,TH" in text and "TRIGGER:-PT30M" in text
    specs, simplified = cal_text.from_ics(text, ROME)
    assert simplified == 0
    mine = {i["title"]: i for i in cal_store.items(cal)}
    for s in specs:
        m = mine[s["title"]]
        assert (s["start"], s["end"], s["all_day"], s["notes"], s["location"]) == (m["start"], m["end"], m["all_day"], m["notes"], m["location"])
        assert (cal_store._repeat(s.get("repeat")) or None) == m["repeat"] and sorted(s.get("skip", [])) == m["skip"]


def test_an_ics_from_elsewhere_with_a_rule_beyond_ours_keeps_its_first_date(cal):
    text = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a\r\nDTSTART;TZID=Europe/Rome:20261012T090000\r\nDTEND;TZID=Europe/Rome:"
            "20261012T100000\r\nRRULE:FREQ=MONTHLY;BYDAY=2MO\r\nSUMMARY:Consiglio\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    specs, simplified = cal_text.from_ics(text, ROME)
    assert simplified == 1 and specs[0]["start"] == "2026-10-12T09:00" and "repeat" not in specs[0]


def test_the_alert_is_a_notification_of_its_own(cal):
    m = sys_push.message("calendar.alert", {"text": "📅 Dentista — tra 30 minuti", "key": "e1|2026-10-12T15:00|30"}, cal)
    assert m and m["view"] == "chat" and m["tag"] == "aurora-calendar-e1|2026-10-12T15:00|30"
    assert "calendar" in sys_push.PRESETS["suggested"] and "calendar" not in sys_push.MACHINE


def test_no_other_calendar_set_means_nothing_fetched(cal):
    assert not cal_external.configured(cal.values)
    assert cal_external.events(cal.values, datetime.now(ROME), datetime.now(ROME) + timedelta(days=1)) == ([], [])


def _plugin(monkeypatch, cfg):
    monkeypatch.setattr(sys_config, "_cached", cfg)
    monkeypatch.setenv("AURORA_PLUGIN", "calendar")
    spec = importlib.util.spec_from_file_location("calendar_plugin_server", PLUGIN / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_chat_s_tools_add_list_change_and_delete(cal, monkeypatch):
    p = _plugin(monkeypatch, cal)
    said = p.calendar_remind("chiamare Marco", "domani alle 9")
    assert said.startswith("Ok, te lo ricorderò: promemoria «chiamare Marco»") and "alle 09:00" in said
    p.calendar_add("Dentista", "venerdì 15:00", minutes=45, location="Via Roma", alert_minutes="1440,60")
    rows = {i["title"]: i for i in cal_store.items(cal)}
    assert rows["chiamare Marco"]["kind"] == "reminder" and rows["chiamare Marco"]["alerts"] == [0]
    assert rows["Dentista"]["alerts"] == [60, 1440] and rows["Dentista"]["by"] == "chat"
    agenda = p.calendar_agenda(days=8)
    assert agenda.startswith("Oggi è ") and f"id {rows['Dentista']['id']}" in agenda and "⏰ chiamare Marco" in agenda
    moved = p.calendar_change(rows["Dentista"]["id"], when="lunedì 16:00")
    assert "alle 16:00" in moved and cal_store.get(cal, rows["Dentista"]["id"])["end"].endswith("16:45")
    assert p.calendar_delete(rows["Dentista"]["id"]) == "Eliminato «Dentista»"
    with pytest.raises(Exception, match="già passato"):
        p.calendar_remind("ieri", "2020-01-01 10:00")


def test_the_manifest_says_what_each_tool_does():
    m = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    assert m["effects"]["calendar_agenda"] == "read" and m["effects"]["calendar_add_event"] == "external"
    assert {m["effects"][t] for t in ("calendar_add", "calendar_remind", "calendar_change", "calendar_delete")} == {"write_local"}
    assert m["sandbox"] == {"write": ["AURORA_CALENDAR_DIR"]} and "network" not in m["sandbox"]     # the ICS links need it
    assert not m["requires"]                                                         # always there, nothing to set
    sys.modules.pop("calendar_plugin_server", None)
