# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The user's other calendars, read only: ICS links (Google's "secret address in iCal format", Outlook's published
calendar, any .ics) and one CalDAV calendar (Nextcloud, iCloud with an app password, Fastmail, Radicale…).

Shared by the calendar page (the API) and the calendar plugin (the chat): the settings are the plugin's,
AURORA_CALENDAR_ICS_URLS and AURORA_CALDAV_*, read from `values` (the API's cfg.values, the plugin's environment).
An ICS text is kept 10 minutes: the page moving between weeks does not download a calendar each time. A failure names
the calendar by its number, never by its address (it may hold a private token).
"""
from __future__ import annotations

import html
import re
import threading
import time
from datetime import datetime, timezone

from . import txt_ical

UA = {"User-Agent": "Aurora/1.0"}
KEEP_S = 600
_cache: dict[str, tuple[float, str]] = {}
_lock = threading.Lock()


def settings(values) -> tuple[list[str], str, tuple[str, str]]:
    ics = [u.strip() for u in str(values.get("AURORA_CALENDAR_ICS_URLS") or "").split(",") if u.strip()]
    dav = str(values.get("AURORA_CALDAV_URL") or "").strip().rstrip("/")
    return ics, (dav + "/" if dav else ""), (str(values.get("AURORA_CALDAV_USER") or ""), str(values.get("AURORA_CALDAV_PASSWORD") or ""))


def configured(values) -> bool:
    ics, dav, _ = settings(values)
    return bool(ics or dav)


def _ics_text(url: str) -> str:
    import httpx
    with _lock:
        hit = _cache.get(url)
    if hit and time.time() - hit[0] < KEEP_S:
        return hit[1]
    text = httpx.get(url, headers=UA, timeout=30, follow_redirects=True).raise_for_status().text
    with _lock:
        _cache[url] = (time.time(), text)
        for k in [k for k, v in _cache.items() if time.time() - v[0] > KEEP_S]:
            del _cache[k]
    return text


def _z(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Refused(Exception):
    """CalDAV said no to the user and password."""


def caldav_ics(dav: str, auth: tuple[str, str], a: datetime, b: datetime) -> list[str]:
    import httpx
    body = ('<?xml version="1.0" encoding="utf-8"?><C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
            '<D:prop><C:calendar-data/></D:prop><C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT">'
            f'<C:time-range start="{_z(a)}" end="{_z(b)}"/></C:comp-filter></C:comp-filter></C:filter></C:calendar-query>')
    r = httpx.request("REPORT", dav, content=body, auth=auth, timeout=30,
                      headers={**UA, "Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
    if r.status_code == 401:
        raise Refused("CalDAV refused the user/password (iCloud and Google need an app password)")
    r.raise_for_status()
    return [html.unescape(m) for m in re.findall(r"<[^>]*calendar-data[^>]*>(.*?)</[^>]*calendar-data>", r.text, re.S)]


def events(values, a: datetime, b: datetime) -> tuple[list[dict], list[str]]:
    """(occurrences in [a, b) — {start, end, all_day, summary, location, description, uid, cal, note?} — and the
    calendars that could not be read)."""
    import httpx
    ics, dav, auth = settings(values)
    out, failed = [], []
    for i, url in enumerate(ics, 1):
        try:
            out += [{**e, "cal": f"ics{i}"} for e in txt_ical.events(_ics_text(url), a, b)]
        except (httpx.HTTPError, ValueError) as e:
            failed.append(f"ICS {i} ({type(e).__name__})")
    if dav:
        try:
            for text in caldav_ics(dav, auth, a, b):
                out += [{**e, "cal": "caldav"} for e in txt_ical.events(text, a, b)]
        except Refused:
            failed.append("CalDAV (user/password refused)")
        except (httpx.HTTPError, ValueError) as e:
            failed.append(f"CalDAV ({type(e).__name__})")
    return sorted(out, key=lambda e: e["start"]), failed


def as_occurrences(evs: list[dict], z) -> list[dict]:
    """The external events in cal_store's occurrence shape (read only: no id), in Aurora's zone `z` (an event written
    in UTC or in another zone shows at the hour of here), for the page and the agenda."""
    def at(d: datetime, all_day: bool) -> str:
        return d.replace(tzinfo=z).isoformat() if all_day else d.astimezone(z).isoformat()   # a DATE is the same day
    return [{"kind": "event", "title": e["summary"] or "(senza titolo)", "all_day": e["all_day"], "location": e["location"],
             "notes": e.get("description", ""), "start_iso": at(e["start"], e["all_day"]), "end_iso": at(e["end"], e["all_day"]),
             "cal": e["cal"], **({"note": e["note"]} if e.get("note") else {})} for e in evs]
