# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own calendar (cal_store, roadmap 68): the page's weeks and months, adding and changing appointments and
reminders, one occurrence skipped, the alerts (a notification and a bubble in the chat, «ok» or «rimanda»), the
whole calendar as an .ics and an .ics imported — each user's own, sealed. The user's other calendars (cal_external)
are shown beside, read only, when the calendar plugin's card has them."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from .core import auth, cfg, in_thread, log, me, note

router = APIRouter()
MAX_DAYS = 62                                       # a month view with its first and last weeks
MAX_IMPORT = 5 * 1024 * 1024


def _store():
    from aurora import cal_store
    cal_store.ready(cfg)
    return cal_store


def _day(v: str | None, default: date) -> date:
    try:
        return date.fromisoformat(v) if v else default
    except ValueError:
        raise HTTPException(status_code=422, detail="a day: YYYY-MM-DD") from None


@router.get("/v1/aurora/calendar", dependencies=[Depends(auth)])
async def calendar(start: str | None = None, end: str | None = None, external: bool = True) -> dict:
    """The occurrences from `start` (default today) to `end` (excluded; default a week later), Aurora's and, when set,
    the other calendars' (read only), with the days the user may not have read."""
    from aurora import cal_external
    cs = _store()
    z = cs.tz(cfg)
    today = datetime.now(z).date()
    a = _day(start, today)
    b = _day(end, a + timedelta(days=7))
    if not 0 < (b - a).days <= MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"from 1 to {MAX_DAYS} days")
    ta, tb = datetime.combine(a, datetime.min.time(), z), datetime.combine(b, datetime.min.time(), z)
    out = {"today": today.isoformat(), "tz": getattr(z, "key", str(z)), "events": cs.occurrences(cfg, ta, tb),
           "external": [], "failed": [], "connected": cal_external.configured(cfg.values)}
    if external and out["connected"]:
        evs, out["failed"] = await in_thread(cal_external.events, cfg.values, ta, tb)
        out["external"] = cal_external.as_occurrences(evs, z)
    return out


def _spec(b: dict) -> dict:
    keys = ("kind", "title", "start", "end", "all_day", "minutes", "location", "notes", "alerts", "repeat")
    return {k: b[k] for k in keys if k in b}


@router.post("/v1/aurora/calendar/items", dependencies=[Depends(auth)])
async def calendar_add(request: Request) -> dict:
    cs = _store()
    try:
        it = cs.add(cfg, {**_spec(await request.json()), "by": "page"})
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: %s added a calendar %s", me(), it["kind"])
    return {"item": it}


@router.get("/v1/aurora/calendar/items/{iid}", dependencies=[Depends(auth)])
def calendar_item(iid: str) -> dict:
    it = _store().get(cfg, iid)
    if it is None:
        raise HTTPException(status_code=404, detail="no such item")
    return {"item": it}


@router.put("/v1/aurora/calendar/items/{iid}", dependencies=[Depends(auth)])
async def calendar_change(iid: str, request: Request) -> dict:
    cs = _store()
    try:
        return {"item": cs.update(cfg, iid, _spec(await request.json()))}
    except KeyError:
        raise HTTPException(status_code=404, detail="no such item") from None
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.delete("/v1/aurora/calendar/items/{iid}", dependencies=[Depends(auth)])
def calendar_delete(iid: str, occurrence: str | None = None) -> dict:
    """The item, or (`occurrence`: its "YYYY-MM-DDTHH:MM") only that occurrence of a repeated one."""
    cs = _store()
    try:
        left = cs.delete(cfg, iid, occurrence)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such item") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return {"deleted": iid, "item": left}


# ---- the alerts -------------------------------------------------------------------------------------------------------
def _alert(d: dict, now: datetime) -> dict:
    from aurora import cal_text
    return {"key": d["key"], "text": cal_text.alert_text(d, now), "item": d["item"], "minutes": d["minutes"]}


@router.get("/v1/aurora/calendar/pending", dependencies=[Depends(auth)])
def calendar_pending() -> dict:
    """The alerts told in the last hours and not answered (the chat shows them when it opens)."""
    cs = _store()
    now = datetime.now(cs.tz(cfg))
    return {"alerts": [_alert(d, now) for d in cs.pending(cfg, now)]}


@router.post("/v1/aurora/calendar/answer", dependencies=[Depends(auth)])
async def calendar_answer(request: Request) -> dict:
    """{"key", "snooze"?: minutes}: an alert done, or told again later."""
    b = await request.json()
    try:
        return {"answer": _store().answer(cfg, str(b.get("key", "")), int(b.get("snooze") or 0))}
    except KeyError:
        raise HTTPException(status_code=404, detail="no such alert") from None
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="snooze: minutes") from None


def remind_now(now: datetime | None = None) -> list[str]:
    """The alerts of this minute for the current user: a notification each and a bubble in the chat."""
    cs = _store()
    now = now or datetime.now(cs.tz(cfg))
    told = []
    for d in cs.due(cfg, now):
        a = _alert(d, now)
        note("calendar", "calendar.alert", {"text": a["text"], "key": d["key"], "kind": d["item"]["kind"]})
        told.append(d["key"])
    return told


def watch_calendar(every_s: int = 30) -> None:
    """Twice a minute, for each user: the alerts whose time came (owner, 2026-10-08). Each user's key is made here,
    so the calendar plugin (in its cage, the state folder read only) finds it."""
    from aurora import sys_context
    from .core import _admin
    from .users import _users
    while True:
        time.sleep(every_s)
        try:
            names = [u["name"] for u in _users().list()] if _admin() else [None]
        except Exception:  # noqa: BLE001 — the watcher never dies
            continue
        for name in names:
            try:
                with sys_context.acting_as(name):
                    remind_now()
            except Exception as e:  # noqa: BLE001 — one user's problem never stops the others'
                log.warning("calendar alert: %s", type(e).__name__)


# ---- files ------------------------------------------------------------------------------------------------------------
@router.get("/v1/aurora/calendar/export.ics", dependencies=[Depends(auth)])
def calendar_export() -> Response:
    """The whole calendar as one .ics: Google Calendar, Outlook and Apple Calendar import it."""
    from aurora import cal_text
    cs = _store()
    text = cal_text.to_ics(cs.items(cfg), cs.tz(cfg))
    return Response(text, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="aurora.ics"'})


@router.post("/v1/aurora/calendar/import", dependencies=[Depends(auth)])
async def calendar_import(request: Request) -> dict:
    """The body is an .ics file: its events added (the ones already here, same title and start, are not doubled)."""
    from aurora import cal_text
    cs = _store()
    raw = await request.body()
    if not raw or len(raw) > MAX_IMPORT:
        raise HTTPException(status_code=422, detail="an .ics of 1 byte to 5 MB")
    try:
        specs, simplified = cal_text.from_ics(raw.decode("utf-8-sig", errors="replace"), cs.tz(cfg))
    except (ValueError, KeyError, IndexError) as e:
        raise HTTPException(status_code=422, detail=f"not a readable .ics: {type(e).__name__}") from None
    have, new = {(r["title"], r["start"]) for r in cs.items(cfg)}, []
    for s in specs:
        k = (str(s["title"]).strip()[:200], s["start"])
        if k not in have:
            have.add(k)
            new.append(s)
    added, bad = cs.add_many(cfg, new)
    same = len(specs) - len(new)
    log.info("audit: %s imported a calendar: %d added, %d already there, %d unreadable", me(), added, same, bad)
    return {"added": added, "already": same, "unreadable": bad, "simplified": simplified}
