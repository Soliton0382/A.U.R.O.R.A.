# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The calendar in words and in files (cal_store's items):

when(text, now)          «domani alle 9», «venerdì 15:30», «12/10 ore 18», «2026-10-12 18:00» -> wall time; the date is
                         the code's, never the model's guess (the diet's lesson, C179)
agenda(occ, today, ...)  the agenda of some days for the chat (what the tool returns)
alert_text(d, now)       the words of an alert: «📅 Dentista — tra 30 minuti (10:00) · Via Roma»
to_ics(items, tz)        the whole calendar as one .ics (RRULE, EXDATE, VALARM): Google, Outlook, Apple import it
from_ics(text, tz)       the events of an .ics as items; a rule beyond cal_store's repeats is kept as its first date
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

from . import cal_store, txt_ical

DAYS = ("lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica")
DAYS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
REL = {"oggi": 0, "today": 0, "stasera": 0, "stamattina": 0, "domani": 1, "tomorrow": 1, "dopodomani": 2}
MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre")
SHOWN = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn")


def when(text: str, now: datetime) -> tuple[str, bool]:
    """(wall time "YYYY-MM-DDTHH:MM", has_time). Raises ValueError on words it does not know."""
    t = _norm(text).strip()
    if not t:
        raise ValueError("when: empty")
    day: date | None = None
    rest = t
    if m := re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[t\s]+|$)", t):
        day, rest = date(int(m[1]), int(m[2]), int(m[3])), t[m.end():]
    elif m := re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?:\s+|$)", t):
        y = int(m[3]) if m[3] else now.year
        y = y + 2000 if y < 100 else y
        day, rest = date(y, int(m[2]), int(m[1])), t[m.end():]
        if not m[3] and day < now.date():                              # «12/1» in December: next year's
            day = day.replace(year=y + 1)
    else:
        for w, n in REL.items():
            if re.match(rf"{w}\b", t):
                day, rest = now.date() + timedelta(days=n), t[len(w):]
                break
        else:
            for names in (DAYS, DAYS_EN):
                for i, w in enumerate(names):
                    if m := re.match(rf"(?:(?:il|la|next|prossim[oa])\s+)?{w}(?:\s+prossim[oa])?\b", t):
                        ahead = (i - now.weekday()) % 7 or (7 if re.search(r"prossim|next", m[0]) else 0)
                        day, rest = now.date() + timedelta(days=ahead), t[m.end():]
                        break
                if day:
                    break
    rest = re.sub(r"^\s*(?:,|alle|ore|at|dalle|h)\s*", "", rest.strip()).strip()
    rest = re.sub(r"^(?:alle|ore|at)\s*", "", rest).strip()
    hm = None
    if m := re.match(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", rest):
        h, mi = int(m[1]), int(m[2] or 0)
        if m[3] == "pm" and h < 12:
            h += 12
        elif m[3] == "am" and h == 12:
            h = 0
        if h > 23 or mi > 59:
            raise ValueError("when: a time HH:MM")
        hm = (h, mi)
        rest = rest[m.end():].strip()
    elif rest.startswith(("mezzogiorno", "noon")):
        hm, rest = (12, 0), ""
    if rest and day is None and hm is None:
        raise ValueError("when: oggi, domani, a weekday, DD/MM or YYYY-MM-DD, and a time HH:MM")
    if day is None:
        if hm is None:
            raise ValueError("when: a day or a time")
        day = now.date() if (hm[0], hm[1]) > (now.hour, now.minute) else now.date() + timedelta(days=1)
    if "stasera" in t and hm and hm[0] < 12:                          # «stasera alle 8»: 20:00
        hm = (hm[0] + 12, hm[1])
    return datetime.combine(day, datetime.min.time()).replace(hour=hm[0] if hm else 0, minute=hm[1] if hm else 0).strftime(cal_store.FMT), hm is not None


def date_it(d: date) -> str:
    return f"{SHOWN[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def _hm(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M")


def line(o: dict) -> str:
    """One occurrence in a row of the agenda."""
    if o.get("kind") == "reminder":
        head = f"{_hm(o['start_iso'])} ⏰ {o['title']}"
    elif o.get("all_day"):
        head = f"tutto il giorno · {o['title']}"
    else:
        head = f"{_hm(o['start_iso'])}–{_hm(o['end_iso'])} {o['title']}"
    extra = [o["location"]] if o.get("location") else []
    if o.get("repeat"):
        extra.append({"daily": "ogni giorno", "weekly": "ogni settimana", "monthly": "ogni mese", "yearly": "ogni anno"}[o["repeat"]["freq"]])
    if "id" in o and o.get("cal", "aurora") == "aurora":
        extra.append(f"id {o['id']}" + (f", occorrenza {o['at']}" if o.get("repeat") else ""))
    elif o.get("cal"):
        extra.append(f"calendario {o['cal']}, sola lettura")
    return f"  {head}" + (f" ({'; '.join(extra)})" if extra else "")


def agenda(occ: list[dict], today: date, first: date, days: int, failed: list[str] | None = None) -> str:
    rows, cur = [f"Oggi è {date_it(today)}.", f"Agenda dal {first:%d/%m/%Y} per {days} giorni:"], None
    for o in occ:
        d = datetime.fromisoformat(o["start_iso"]).date()
        if d != cur:
            cur = d
            rows.append(f"\n{date_it(d)}" + (" (oggi)" if d == today else " (domani)" if d == today + timedelta(days=1) else ""))
        rows.append(line(o))
    if len(rows) == 2:
        rows.append("nessun impegno")
    if failed:
        rows.append(f"(non letti: {', '.join(failed)})")
    return "\n".join(rows)


def alert_text(d: dict, now: datetime) -> str:
    o, m = d["item"], d["minutes"]
    start = datetime.fromisoformat(o["start_iso"])
    icon = "⏰" if o.get("kind") == "reminder" else "📅"
    if o.get("all_day"):
        when_s = "oggi" if start.date() == now.date() else f"{date_it(start.date())}"
    else:
        left = round((start - now).total_seconds() / 60)
        if left <= 0:
            when_s = f"adesso ({start:%H:%M})" if left > -5 else f"era alle {start:%H:%M}"
        elif left < 60:
            when_s = f"tra {left} minuti ({start:%H:%M})"
        elif start.date() == now.date():
            when_s = f"alle {start:%H:%M}"
        else:
            when_s = f"{date_it(start.date())} alle {start:%H:%M}"
    if m == 0 and not o.get("all_day") and abs((start - now).total_seconds()) < 300:
        when_s = f"adesso ({start:%H:%M})"
    return f"{icon} {o['title']} — {when_s}" + (f" · {o['location']}" if o.get("location") else "")


# ---- files ------------------------------------------------------------------------------------------------------------
def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(s: str) -> list[str]:
    """RFC 5545 3.1: lines of at most 75 octets, continued with a space."""
    out, b = [], s.encode()
    while len(b) > 75:
        cut = 75 if not out else 74
        while cut and (b[cut] & 0xC0) == 0x80:                        # never inside a UTF-8 character
            cut -= 1
        out.append(b[:cut].decode())
        b = b[cut:]
    out.append(b.decode())
    return [out[0]] + [" " + x for x in out[1:]]


def to_ics(rows: list[dict], z) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tzid = getattr(z, "key", "")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//A.U.R.O.R.A.//Aurora calendar//IT", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Aurora"]
    for it in rows:
        s, e = datetime.strptime(it["start"], cal_store.FMT), datetime.strptime(it["end"], cal_store.FMT)
        if it["all_day"]:
            ds, de = f"DTSTART;VALUE=DATE:{s:%Y%m%d}", f"DTEND;VALUE=DATE:{e:%Y%m%d}"
        elif tzid:
            ds, de = f"DTSTART;TZID={tzid}:{s:%Y%m%dT%H%M%S}", f"DTEND;TZID={tzid}:{e:%Y%m%dT%H%M%S}"
        else:
            u = lambda d: d.replace(tzinfo=z).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")   # noqa: E731
            ds, de = f"DTSTART:{u(s)}", f"DTEND:{u(e)}"
        ev = ["BEGIN:VEVENT", f"UID:{it['id']}@aurora", f"DTSTAMP:{stamp}", ds, de, f"SUMMARY:{_esc(it['title'])}"]
        ev += [f"LOCATION:{_esc(it['location'])}"] if it.get("location") else []
        ev += [f"DESCRIPTION:{_esc(it['notes'])}"] if it.get("notes") else []
        ev += ["CATEGORIES:REMINDER"] if it["kind"] == "reminder" else []
        if it.get("repeat"):
            r = cal_store._rule(it["repeat"])
            ev.append("RRULE:" + ";".join(f"{k}={v}" for k, v in r.items()))
            for x in it.get("skip") or []:
                xd = datetime.strptime(x, cal_store.FMT)
                ev.append(f"EXDATE;VALUE=DATE:{xd:%Y%m%d}" if it["all_day"] else
                          f"EXDATE;TZID={tzid}:{xd:%Y%m%dT%H%M%S}" if tzid else
                          f"EXDATE:{xd.replace(tzinfo=z).astimezone(timezone.utc):%Y%m%dT%H%M%SZ}")
        for m in it.get("alerts") or []:
            ev += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(it['title'])}", f"TRIGGER:-PT{m}M", "END:VALARM"]
        ev.append("END:VEVENT")
        for x in ev:
            lines += _fold(x)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def from_ics(text: str, z) -> tuple[list[dict], int]:
    """(item specs, how many repeats were too complex and kept as their first date only)."""
    out, simplified = [], 0
    for ev in txt_ical.parse(text, z):
        s, e = ev["start"].astimezone(z), ev["end"].astimezone(z)
        spec = {"title": ev.get("summary") or "(senza titolo)", "start": s.strftime(cal_store.FMT), "end": e.strftime(cal_store.FMT),
                "all_day": ev["all_day"], "location": ev.get("location", ""), "notes": ev.get("description", ""),
                "alerts": [], "by": "import"}
        if ev["all_day"]:                                             # a DATE is the same day wherever you read it
            spec["start"] = ev["start"].strftime("%Y-%m-%dT00:00")
            spec["end"] = ev["end"].strftime("%Y-%m-%dT00:00")
        rule = ev.get("rrule") or {}
        freq = rule.get("FREQ", "").lower()
        complex_rule = any(k in rule for k in ("BYSETPOS", "BYMONTHDAY", "BYMONTH", "BYHOUR")) or (freq != "weekly" and "BYDAY" in rule)
        if rule and freq in cal_store.FREQS and not complex_rule:
            rep = {"freq": freq, "interval": int(rule.get("INTERVAL", "1") or 1)}
            if rule.get("COUNT", "").isdigit():
                rep["count"] = int(rule["COUNT"])
            if rule.get("UNTIL"):
                rep["until"] = f"{rule['UNTIL'][:4]}-{rule['UNTIL'][4:6]}-{rule['UNTIL'][6:8]}"
            if "BYDAY" in rule:
                rep["days"] = [d[-2:] for d in rule["BYDAY"].split(",") if d[-2:] in cal_store.WEEKDAYS]
            spec["repeat"] = rep
            spec["skip"] = [x.astimezone(z).strftime(cal_store.FMT) for x in ev.get("exdates", ())]
        elif rule:
            simplified += 1
        out.append(spec)
    return out, simplified
