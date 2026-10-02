# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "calendar": the owner's calendars — ICS links read only (Google's "secret address in iCal format", Outlook,
any .ics), and one CalDAV calendar read and written (Nextcloud, iCloud with an app password, Fastmail, Radicale…).
Adding an event is an external action: the owner approves it. The parsing is aurora/txt_ical.py.
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
from aurora import txt_ical
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

ICS = [u.strip() for u in os.environ.get("AURORA_CALENDAR_ICS_URLS", "").split(",") if u.strip()]
DAV = os.environ.get("AURORA_CALDAV_URL", "").strip().rstrip("/") + "/"
AUTH = (os.environ.get("AURORA_CALDAV_USER", ""), os.environ.get("AURORA_CALDAV_PASSWORD", ""))
UA = {"User-Agent": "Aurora/1.0"}
server = MCPServer("calendar", version="1.0")


def _caldav_ics(a: datetime, b: datetime) -> list[str]:
    def z(d: datetime) -> str:
        return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    body = ('<?xml version="1.0" encoding="utf-8"?><C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
            '<D:prop><C:calendar-data/></D:prop><C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT">'
            f'<C:time-range start="{z(a)}" end="{z(b)}"/></C:comp-filter></C:comp-filter></C:filter></C:calendar-query>')
    r = httpx.request("REPORT", DAV, content=body, auth=AUTH, timeout=30,
                      headers={**UA, "Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
    if r.status_code == 401:
        raise ToolError("CalDAV refused the user/password (iCloud and Google need an app password)")
    r.raise_for_status()
    return [html.unescape(m) for m in re.findall(r"<[^>]*calendar-data[^>]*>(.*?)</[^>]*calendar-data>", r.text, re.S)]


def _all(a: datetime, b: datetime) -> tuple[list[dict], list[str]]:
    if not ICS and DAV == "/":
        raise ToolError("no calendar set: an ICS link or a CalDAV address in the plugin's card")
    out, failed = [], []
    for i, url in enumerate(ICS, 1):
        try:
            text = httpx.get(url, headers=UA, timeout=30, follow_redirects=True).raise_for_status().text
            out += [{**e, "cal": f"ics{i}"} for e in txt_ical.events(text, a, b)]
        except httpx.HTTPError as e:
            failed.append(f"ICS {i} ({type(e).__name__})")       # never the address: it may hold a private token
    if DAV != "/":
        try:
            for text in _caldav_ics(a, b):
                out += [{**e, "cal": "caldav"} for e in txt_ical.events(text, a, b)]
        except httpx.HTTPError as e:
            failed.append(f"CalDAV ({type(e).__name__})")
    return sorted(out, key=lambda e: e["start"]), failed


@server.tool()
def calendar_agenda(days: int = 7) -> str:
    """The events of the next days (today included), from every calendar set: time, title, place."""
    a = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    evs, failed = _all(a, a + timedelta(days=max(1, min(days, 60))))
    rows, day = [], None
    for e in evs:
        d = e["start"].astimezone().strftime("%a %d/%m")
        if d != day:
            rows.append(f"\n{d}")
            day = d
        when = "tutto il giorno" if e["all_day"] else f"{e['start'].astimezone():%H:%M}–{e['end'].astimezone():%H:%M}"
        rows.append(f"  {when}  {e['summary']}" + (f" · {e['location']}" if e["location"] else "")
                    + (f" ({e['note']})" if e.get("note") else ""))
    return (f"Agenda dei prossimi {days} giorni:" + ("".join(f"\n{r}" for r in rows) if rows else "\nnessun impegno")
            + (f"\n(non letti: {', '.join(failed)})" if failed else ""))


@server.tool()
def calendar_add_event(title: str, start: str, minutes: int = 60, location: str = "", notes: str = "") -> str:
    """Add an event to the CalDAV calendar. start: "YYYY-MM-DD HH:MM" in local time (an external action: the owner
    confirms it)."""
    if DAV == "/":
        raise ToolError("adding needs a CalDAV calendar (ICS links are read only)")
    try:
        s = datetime.strptime(start.strip(), "%Y-%m-%d %H:%M").astimezone()
    except ValueError:
        raise ToolError('start must be "YYYY-MM-DD HH:MM"') from None
    uid, text = txt_ical.make_event(title, s, s + timedelta(minutes=max(5, min(minutes, 24 * 60))), location, notes)
    r = httpx.put(f"{DAV}{uid.split('@')[0]}.ics", content=text.encode(), auth=AUTH, timeout=30,
                  headers={**UA, "Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
    if r.status_code not in (200, 201, 204):
        raise ToolError(f"CalDAV refused the event: HTTP {r.status_code}")
    return f"event added: {title}, {s:%a %d/%m %H:%M}"


if __name__ == "__main__":
    server.run("stdio")
