# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""iCalendar (RFC 5545), the part a personal calendar uses: events in a time window, recurrences expanded.

parse(text)              VEVENTs: start, end, all-day, summary, location, description, uid, rrule, exdates
events(text, a, b)       the occurrences between a and b (aware datetimes), sorted
make_event(...)          one VEVENT in a VCALENDAR, for CalDAV PUT

Times: UTC ("...Z"), with TZID (zoneinfo), floating (local time), all-day (DATE). Recurrence: FREQ DAILY / WEEKLY /
MONTHLY / YEARLY with INTERVAL, COUNT, UNTIL, BYDAY (weekly), EXDATE. Not handled (said in the result, never guessed):
BYSETPOS, BYMONTHDAY lists, monthly BYDAY like "2MO" — such an event shows its first occurrence only.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
MAX_OCCURRENCES = 1000                                   # a runaway rule stops here


def _unfold(text: str) -> list[str]:
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _split(line: str) -> tuple[str, dict, str]:
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    return name.upper(), {k.upper(): v.strip('"') for k, _, v in (p.partition("=") for p in params)}, value


def _when(value: str, params: dict, local) -> tuple[datetime, bool]:
    """(aware datetime, all_day)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d.replace(tzinfo=local), True
    d = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return d.replace(tzinfo=timezone.utc), False
    try:
        tz = ZoneInfo(params["TZID"]) if "TZID" in params else local
    except (ZoneInfoNotFoundError, ValueError):
        tz = local
    return d.replace(tzinfo=tz), False


def parse(text: str, local=None) -> list[dict]:
    local = local or datetime.now().astimezone().tzinfo
    events, cur = [], None
    for line in _unfold(text):
        name, params, value = _split(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            cur = {"exdates": set()}
        elif name == "END" and value.upper() == "VEVENT" and cur is not None:
            if "start" in cur:
                if "end" not in cur:
                    cur["end"] = cur["start"] + (timedelta(days=1) if cur["all_day"] else timedelta(0))
                events.append(cur)
            cur = None
        elif cur is not None:
            if name == "DTSTART":
                cur["start"], cur["all_day"] = _when(value, params, local)
            elif name == "DTEND":
                cur["end"], _ = _when(value, params, local)
            elif name == "DURATION":
                m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
                if m and "start" in cur:
                    w, d, h, mi, s = (int(x or 0) for x in m.groups())
                    cur["end"] = cur["start"] + timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
            elif name in ("SUMMARY", "LOCATION", "DESCRIPTION", "UID"):
                cur[name.lower()] = _unescape(value)
            elif name == "RRULE":
                cur["rrule"] = dict(p.partition("=")[::2] for p in value.split(";") if "=" in p)
            elif name == "EXDATE":
                for v in value.split(","):
                    cur["exdates"].add(_when(v, params, local)[0])
    return events


def _occurrences(ev: dict, until: datetime):
    start, rule = ev["start"], ev.get("rrule")
    if not rule:
        yield start
        return
    freq, step = rule.get("FREQ", ""), int(rule.get("INTERVAL", "1") or 1)
    count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
    stop = until
    if rule.get("UNTIL"):
        u, _ = _when(rule["UNTIL"], {}, start.tzinfo)
        stop = min(until, u + (timedelta(days=1) if len(rule["UNTIL"]) == 8 else timedelta(0)))
    unsupported = any(k in rule for k in ("BYSETPOS", "BYMONTHDAY")) or (freq != "WEEKLY" and "BYDAY" in rule)
    if unsupported or freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        ev["note"] = "recurrence not expanded (rule too complex): first occurrence only"
        yield start
        return
    days = sorted(DAYS[d[-2:]] for d in rule.get("BYDAY", "").split(",") if d[-2:] in DAYS) or [start.weekday()]
    n, i = 0, 0
    while n < MAX_OCCURRENCES:
        if freq == "DAILY":
            cands = [start + timedelta(days=i * step)]
        elif freq == "WEEKLY":
            week = start - timedelta(days=start.weekday()) + timedelta(weeks=i * step)
            cands = [week + timedelta(days=d) for d in days]
        elif freq == "MONTHLY":
            y, m = divmod(start.month - 1 + i * step, 12)
            try:
                cands = [start.replace(year=start.year + y, month=m + 1)]
            except ValueError:                           # the 31st in a short month: skipped, as the RFC says
                cands = []
        else:
            try:
                cands = [start.replace(year=start.year + i * step)]
            except ValueError:
                cands = []
        for c in cands:
            if c < start:
                continue
            if c >= stop or (count is not None and n >= count):
                return
            n += 1
            yield c
        i += 1
        if not cands and i > 400 * step:
            return


def events(text: str, a: datetime, b: datetime, local=None) -> list[dict]:
    """Occurrences overlapping [a, b), each {start, end, all_day, summary, location, description, uid, note?}."""
    out = []
    for ev in parse(text, local):
        length = ev["end"] - ev["start"]
        for s in _occurrences(ev, b):
            if s in ev["exdates"] or s + length <= a or s >= b:
                continue
            out.append({"start": s, "end": s + length, "all_day": ev["all_day"], "summary": ev.get("summary", ""),
                        "location": ev.get("location", ""), "description": ev.get("description", ""),
                        "uid": ev.get("uid", ""), **({"note": ev["note"]} if "note" in ev else {})})
    return sorted(out, key=lambda e: e["start"])


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_event(summary: str, start: datetime, end: datetime, location: str = "", description: str = "",
               uid: str | None = None) -> tuple[str, str]:
    """(uid, VCALENDAR text) of one timed event, in UTC."""
    uid = uid or f"{uuid.uuid4()}@aurora"
    z = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")   # noqa: E731
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//A.U.R.O.R.A.//Aurora//EN", "BEGIN:VEVENT", f"UID:{uid}",
             f"DTSTAMP:{z(datetime.now(timezone.utc))}", f"DTSTART:{z(start)}", f"DTEND:{z(end)}",
             f"SUMMARY:{_esc(summary)}"]
    lines += [f"LOCATION:{_esc(location)}"] if location else []
    lines += [f"DESCRIPTION:{_esc(description)}"] if description else []
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return uid, "\r\n".join(lines) + "\r\n"


def as_date(value: date | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.combine(value, time()).astimezone()
