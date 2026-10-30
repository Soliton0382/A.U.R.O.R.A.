# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""👥 The people of an appointment (cal_share; owner, 30 Oct: «vorrei aggiungere anche lei… così ad entrambi aurora
manda il promemoria… magari anche indirizzi email»): an invited user has it in their own calendar at once, follows its
changes, keeps their own alerts and may leave it; an address gets an invitation .ics. Made-up users and addresses."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aurora import cal_share as S, cal_store, sys_config, sys_users_layout as L, sys_user_config as U

ROME = ZoneInfo("Europe/Rome")


@pytest.fixture
def base(cfg):
    for key in ("AURORA_UPLOADS_DIR", "AURORA_DOCUMENTS_DIR", "AURORA_IMAGE_DIR"):
        cfg.values[key] = f"usr/{key.split('_')[1].lower()}"
    (cfg.root / "usr" / "uploads").mkdir(parents=True)
    sys_config.write_env(cfg.env_file, {"AURORA_TIMEZONE": "Europe/Rome"})
    cfg = sys_config.load(cfg.env_file, check_root=False)
    cfg.path("AURORA_STATUS_DIR").mkdir(parents=True, exist_ok=True)
    L.migrate(cfg, "boss")
    return sys_config.load(cfg.env_file, check_root=False)


def mine(base, who):
    c = U.for_user(base, who)
    cal_store.ready(c)
    return c


def test_who_takes_part_is_checked():
    users = ["boss", "ada", "eve"]
    got = S.normalize([{"user": "ada"}, "ada", {"user": "boss"}, "Zia.Pina@Example.org", {"email": "zia.pina@example.org"}],
                      "boss", users)
    assert got == [{"user": "ada", "rsvp": "pending"}, {"email": "zia.pina@example.org"}]   # oneself and doubles dropped
    with pytest.raises(ValueError):
        S.normalize([{"user": "mallory"}], "boss", users)                      # not a user here
    with pytest.raises(ValueError):
        S.normalize(["not an address@"], "boss", users)
    with pytest.raises(ValueError):
        S.normalize([f"p{i}@example.org" for i in range(S.MAX_PEOPLE + 1)], "boss", users)


def test_an_invited_user_has_it_follows_it_keeps_her_alerts_and_may_leave(base):
    boss, ada = mine(base, "boss"), mine(base, "ada")
    assert boss.path("AURORA_CALENDAR_DIR") != ada.path("AURORA_CALENDAR_DIR")
    it = cal_store.add(boss, {"title": "Cena dai cugini", "start": "2026-11-01 20:00", "minutes": 120,
                              "people": [{"user": "ada"}, {"email": "zia.pina@example.org"}]})
    assert S.sync(base, "boss", it) == ["ada"]
    cid = S.copy_id("boss", it["id"])
    copy = cal_store.get(ada, cid)
    assert copy["title"] == "Cena dai cugini" and copy["shared_from"] == {"user": "boss", "id": it["id"]}
    assert copy["alerts"] == [30]
    due = cal_store.due(ada, datetime(2026, 11, 1, 19, 30, tzinfo=ROME))          # her own reminder, from her file
    assert [d["item"]["title"] for d in due] == ["Cena dai cugini"]
    cal_store.update(ada, cid, {"alerts": [60]})                                   # her alerts are hers
    new = cal_store.update(boss, it["id"], {"title": "Cena dai cugini (spostata)", "start": "2026-11-01 21:00"})
    S.sync(base, "boss", new, it)
    copy = cal_store.get(ada, cid)
    assert copy["title"] == "Cena dai cugini (spostata)" and copy["start"] == "2026-11-01T21:00" and copy["alerts"] == [60]
    S.leave(base, "ada", copy)                                                     # she leaves it…
    cal_store.delete(ada, cid)
    assert cal_store.get(boss, it["id"])["people"] == [{"email": "zia.pina@example.org"}]   # …off his list, his stays
    assert cal_store.get(ada, cid) is None


def test_taken_off_or_deleted_the_copies_go(base):
    boss, ada = mine(base, "boss"), mine(base, "ada")
    it = cal_store.add(boss, {"title": "Dentista", "start": "2026-11-03 15:00", "people": [{"user": "ada"}]})
    S.sync(base, "boss", it)
    cid = S.copy_id("boss", it["id"])
    off = cal_store.update(boss, it["id"], {"people": []})
    assert S.sync(base, "boss", off, it) == ["ada"] and cal_store.get(ada, cid) is None
    back = cal_store.update(boss, it["id"], {"people": [{"user": "ada"}]})
    S.sync(base, "boss", back, off)
    assert cal_store.get(ada, cid)
    S.unshare(base, "boss", back)
    assert cal_store.get(ada, cid) is None


def test_the_invitation_is_one_event_the_other_calendar_updates():
    it = {"id": "e1234abcd", "kind": "event", "title": "Visita", "start": "2026-11-04T10:00", "end": "2026-11-04T11:00",
          "all_day": False, "location": "Via Verdi 1", "notes": "", "alerts": [30], "repeat": None, "skip": [],
          "people": [{"user": "ada"}, {"email": "zia.pina@example.org"}], "created": 1000.0, "updated": 1300.0}
    subject, body, ics = S.invitation(it, ROME, "boss", "boss@example.org")
    assert subject.startswith("Invito: Visita") and "Via Verdi 1" in body
    for line in ("METHOD:REQUEST", "UID:e1234abcd@aurora", "ORGANIZER:mailto:boss@example.org",
                 "ATTENDEE;RSVP=TRUE;ROLE=REQ-PARTICIPANT:mailto:zia.pina@example.org", "SEQUENCE:300"):
        assert line in ics, line
    assert "ada" not in ics                                                       # a user is never an address
    subject, body, ics = S.invitation(it, ROME, "boss", "boss@example.org", "CANCEL")
    assert subject.startswith("Annullato") and "METHOD:CANCEL" in ics and "STATUS:CANCELLED" in ics


def test_she_is_asked_answers_and_he_knows(base):
    """Owner, 30 Oct: «lui riceve una notifica che… può accettare o rifiutare e a me poi arriva la notifica di quello
    che ha scelto». Each user's answer on the maker's list; a no takes her copy away and keeps her as declined; the
    appointment moved asks again; invited again after a no, she is asked again."""
    boss, ada = mine(base, "boss"), mine(base, "ada")
    people = S.normalize([{"user": "ada"}], "boss", ["boss", "ada"])
    assert people == [{"user": "ada", "rsvp": "pending"}]
    it = cal_store.add(boss, {"title": "Cinema", "start": "2026-11-05 21:00", "people": people})
    assert S.newly(None, it) == ["ada"]
    S.sync(base, "boss", it)
    cid = S.copy_id("boss", it["id"])
    assert S.rsvp_of(cal_store.get(ada, cid), "ada") == "pending"
    item = S.answer(base, "ada", cal_store.get(ada, cid), True)
    assert S.rsvp_of(item, "ada") == "yes" and S.rsvp_of(cal_store.get(ada, cid), "ada") == "yes"   # her copy shows it
    moved = cal_store.update(boss, it["id"], {"start": "2026-11-06 21:00"})
    assert S.moved(item, moved) and S.ask_again(moved["people"]) == [{"user": "ada", "rsvp": "pending"}]
    assert not S.moved(moved, cal_store.update(boss, it["id"], {"title": "Cinema!"}))             # a new title: no
    item = S.answer(base, "ada", cal_store.get(ada, cid), False)
    assert S.rsvp_of(item, "ada") == "no" and cal_store.get(ada, cid) is None and S.users_of(item) == set()
    again = S.normalize([{"user": "ada"}], "boss", ["boss", "ada"], item["people"])
    assert again == [{"user": "ada", "rsvp": "pending"}]                                          # asked again
    assert S.newly(item, {**item, "people": again}) == ["ada"]
    with pytest.raises(KeyError):
        S.answer(base, "ada", {"id": "x"}, True)                                                   # not a shared one
