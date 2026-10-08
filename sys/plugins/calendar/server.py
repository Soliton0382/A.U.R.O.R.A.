# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "calendar": Aurora's own calendar, always there (aurora/cal_store: appointments and reminders, sealed, the
alerts told by the API), and the user's other calendars beside it when set — ICS links read only (Google's "secret
address in iCal format", Outlook, any .ics) and one CalDAV calendar (Nextcloud, iCloud with an app password,
Fastmail, Radicale…). Writing in Aurora's calendar is local; adding to the CalDAV one is an external action the
owner approves. The dates are the code's (cal_text.when), never the model's arithmetic.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from aurora import cal_external, cal_store, cal_text, sys_config, txt_ical
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("calendar", version="1.0")
NOT_READY = "il calendario non è ancora pronto (la sua chiave la crea Aurora entro un minuto dall'avvio): riprova tra poco"


def _now() -> datetime:
    return datetime.now(cal_store.tz(cfg))


def _when(text: str) -> tuple[str, bool]:
    try:
        return cal_text.when(text, _now())
    except ValueError as e:
        raise ToolError(f"{e} (es. «domani 9:30», «venerdì 18», «12/10 ore 15», «2026-10-12 15:00»)") from None


def _alerts(v) -> list[int]:
    try:
        return [int(x) for x in str(v).replace(" ", "").split(",") if x != ""]
    except ValueError:
        raise ToolError("alert_minutes: minutes before, e.g. 30 or 1440,60") from None


def _repeat(repeat: str, until: str) -> dict | None:
    words = {"ogni giorno": "daily", "giornaliero": "daily", "ogni settimana": "weekly", "settimanale": "weekly",
             "ogni mese": "monthly", "mensile": "monthly", "ogni anno": "yearly", "annuale": "yearly"}
    r = words.get(repeat.strip().lower(), repeat.strip().lower())
    if not r:
        return None
    if r not in cal_store.FREQS:
        raise ToolError(f"repeat: {', '.join(cal_store.FREQS)}")
    out = {"freq": r}
    if until.strip():
        out["until"] = _when(until)[0][:10]
    return out


def _store(fn, *args):
    try:
        return fn(cfg, *args)
    except OSError:
        raise ToolError(NOT_READY) from None
    except KeyError:
        raise ToolError("nessun elemento con questo id: chiedi prima l'agenda (calendar_agenda) per gli id") from None
    except ValueError as e:
        raise ToolError(str(e)) from None


@server.tool()
def calendar_agenda(days: int = 7, start: str = "oggi") -> str:
    """The appointments and reminders from `start` (oggi, domani, a weekday, DD/MM, YYYY-MM-DD) for `days` days, from
    Aurora's calendar (with the ids to change or delete them) and from the user's other calendars when set (read
    only). USE THIS for «cosa ho domani?», «sono libero venerdì?», «quando è il dentista?»."""
    first = datetime.fromisoformat(_when(start)[0]).date()
    days = max(1, min(int(days), 60))
    z = cal_store.tz(cfg)
    a = datetime.combine(first, datetime.min.time(), z)
    b = a + timedelta(days=days)
    occ = _store(cal_store.occurrences, a, b)
    failed = []
    if cal_external.configured(os.environ):
        evs, failed = cal_external.events(os.environ, a, b)
        occ = sorted(occ + cal_external.as_occurrences(evs, z), key=lambda o: o["start_iso"])
    return cal_text.agenda(occ, _now().date(), first, days, failed)


def _said(it: dict) -> str:
    s = datetime.strptime(it["start"], cal_store.FMT)
    when = cal_text.date_it(s.date()) + ("" if it["all_day"] else f" alle {s:%H:%M}")
    alerts = ", ".join("all'ora esatta" if m == 0 else f"{m} min prima" for m in it["alerts"]) or "nessun avviso"
    rep = f"; si ripete: {it['repeat']['freq']}" if it.get("repeat") else ""
    return f"{'promemoria' if it['kind'] == 'reminder' else 'appuntamento'} «{it['title']}» {when} (id {it['id']}; avviso: {alerts}{rep})"


@server.tool()
def calendar_add(title: str, when: str, minutes: int = 60, location: str = "", notes: str = "",
                 alert_minutes: str = "30", repeat: str = "", until: str = "") -> str:
    """Add an appointment to Aurora's calendar. `when`: «domani 10:00», «venerdì 18:30», «12/10 ore 9»,
    «2026-10-12 09:00»; only a day = all day. `minutes`: how long. `alert_minutes`: when to tell the user, minutes
    before (e.g. "30", "1440,60"; "" for none). `repeat`: daily, weekly, monthly, yearly (or «ogni settimana»…),
    `until`: the last day."""
    start, timed = _when(when)
    it = _store(cal_store.add, {"kind": "event", "title": title, "start": start, "all_day": not timed,
                                "minutes": minutes, "location": location, "notes": notes,
                                "alerts": _alerts(alert_minutes) if timed else [], "repeat": _repeat(repeat, until), "by": "chat"})
    return "Aggiunto " + _said(it)


@server.tool()
def calendar_remind(text: str, when: str, repeat: str = "", until: str = "") -> str:
    """A reminder: Aurora tells the user `text` at `when` (a notification and a message in the chat). USE THIS for
    «ricordami domani alle 9 di chiamare Marco», «ogni lunedì alle 8 ricordami la pillola» (repeat: weekly).
    `when` like calendar_add's; with no time, 9:00."""
    start, timed = _when(when)
    if not timed:
        start = start[:11] + "09:00"
    if datetime.strptime(start, cal_store.FMT).replace(tzinfo=cal_store.tz(cfg)) < _now() - timedelta(minutes=1) and not repeat:
        raise ToolError(f"{start.replace('T', ' ')} è già passato: un altro momento?")
    it = _store(cal_store.add, {"kind": "reminder", "title": text, "start": start, "alerts": [0],
                                "repeat": _repeat(repeat, until), "by": "chat"})
    return "Ok, te lo ricorderò: " + _said(it)


@server.tool()
def calendar_change(item_id: str, title: str = "", when: str = "", minutes: int = 0, location: str = "",
                    notes: str = "", alert_minutes: str = "-") -> str:
    """Change an item of Aurora's calendar (its id from calendar_agenda): only what is given changes. `when` moves it
    (the length stays unless `minutes` is given)."""
    old = _store(cal_store.get, item_id.strip())
    if old is None:
        raise ToolError("nessun elemento con questo id: chiedi prima l'agenda (calendar_agenda) per gli id")
    ch: dict = {}
    if title.strip():
        ch["title"] = title
    if when.strip():
        ch["start"], timed = _when(when)
        if old["all_day"] == timed:                                 # from all day to a time, or back
            ch["all_day"] = not timed
    if minutes:
        ch["minutes"] = minutes
    if location.strip():
        ch["location"] = location
    if notes.strip():
        ch["notes"] = notes
    if alert_minutes != "-":
        ch["alerts"] = _alerts(alert_minutes)
    if not ch:
        raise ToolError("nothing to change")
    return "Cambiato: " + _said(_store(cal_store.update, item_id.strip(), ch))


@server.tool()
def calendar_delete(item_id: str, occurrence: str = "") -> str:
    """Delete an item of Aurora's calendar (its id from calendar_agenda); for a repeated one, `occurrence` (the
    "YYYY-MM-DDTHH:MM" the agenda shows) deletes only that time."""
    it = _store(cal_store.get, item_id.strip())
    if it is None:
        raise ToolError("nessun elemento con questo id: chiedi prima l'agenda (calendar_agenda) per gli id")
    left = _store(cal_store.delete, item_id.strip(), occurrence.strip() or None)
    return (f"Tolta l'occorrenza {occurrence} di «{it['title']}»" if left else f"Eliminato «{it['title']}»")


@server.tool()
def calendar_add_event(title: str, start: str, minutes: int = 60, location: str = "", notes: str = "") -> str:
    """Add an event to the user's CalDAV calendar (Nextcloud, iCloud…), not Aurora's: only when the user asks for
    THAT calendar. start: "YYYY-MM-DD HH:MM" in local time (an external action: the owner confirms it)."""
    import httpx
    _, dav, auth = cal_external.settings(os.environ)
    if not dav:
        raise ToolError("adding there needs a CalDAV calendar (ICS links are read only); Aurora's own: calendar_add")
    try:
        s = datetime.strptime(start.strip(), "%Y-%m-%d %H:%M").astimezone()
    except ValueError:
        raise ToolError('start must be "YYYY-MM-DD HH:MM"') from None
    uid, text = txt_ical.make_event(title, s, s + timedelta(minutes=max(5, min(minutes, 24 * 60))), location, notes)
    r = httpx.put(f"{dav}{uid.split('@')[0]}.ics", content=text.encode(), auth=auth, timeout=30,
                  headers={**cal_external.UA, "Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
    if r.status_code not in (200, 201, 204):
        raise ToolError(f"CalDAV refused the event: HTTP {r.status_code}")
    return f"event added: {title}, {s:%a %d/%m %H:%M}"


if __name__ == "__main__":
    server.run("stdio")
