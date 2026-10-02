# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aurora import txt_ical as I

ROME = ZoneInfo("Europe/Rome")
ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:a
DTSTART;TZID=Europe/Rome:20261005T090000
DTEND;TZID=Europe/Rome:20261005T093000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=5
EXDATE;TZID=Europe/Rome:20261007T090000
SUMMARY:Riunione\\, team
  di progetto
END:VEVENT
BEGIN:VEVENT
UID:b
DTSTART;VALUE=DATE:20261008
SUMMARY:Ferie
END:VEVENT
BEGIN:VEVENT
UID:c
DTSTART:20261006T120000Z
DURATION:PT1H30M
SUMMARY:Call
LOCATION:Online
END:VEVENT
BEGIN:VEVENT
UID:d
DTSTART:20261001T080000Z
RRULE:FREQ=MONTHLY;BYDAY=2MO
SUMMARY:Complicato
END:VEVENT
END:VCALENDAR
"""


def test_a_week_of_events_with_recurrence_exceptions_zones_and_all_day():
    a, b = datetime(2026, 10, 5, tzinfo=ROME), datetime(2026, 10, 12, tzinfo=ROME)
    ev = I.events(ICS, a, b, ROME)
    got = [(e["summary"], e["start"].astimezone(ROME).strftime("%a %d %H:%M"), e["all_day"]) for e in ev]
    assert got == [("Riunione, team di progetto", "Mon 05 09:00", False), ("Call", "Tue 06 14:00", False),
                   ("Ferie", "Thu 08 00:00", True)]                            # Wed 07 excluded by EXDATE
    call = next(e for e in ev if e["summary"] == "Call")
    assert call["end"] - call["start"] == timedelta(hours=1, minutes=30) and call["location"] == "Online"
    later = I.events(ICS, datetime(2026, 10, 12, tzinfo=ROME), datetime(2026, 11, 30, tzinfo=ROME), ROME)
    assert [e["start"].day for e in later if e["uid"] == "a"] == [12, 14, 19]   # COUNT=5: 05, 07 (excluded), 12, 14, 19
    first = I.events(ICS, datetime(2026, 10, 1, tzinfo=timezone.utc), b, ROME)
    assert any(e.get("note") for e in first if e["uid"] == "d")                 # too complex: said, not guessed


def test_an_event_made_for_caldav_reads_back_the_same():
    s = datetime(2026, 10, 9, 15, 0, tzinfo=ROME)
    uid, text = I.make_event("Dentista; controllo, annuale", s, s + timedelta(hours=1), "Via Roma 1")
    ev = I.events(text, s - timedelta(days=1), s + timedelta(days=1), ROME)
    assert len(ev) == 1 and ev[0]["summary"] == "Dentista; controllo, annuale" and ev[0]["start"] == s
    assert ev[0]["uid"] == uid and ev[0]["location"] == "Via Roma 1"
