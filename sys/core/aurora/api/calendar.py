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

from .core import BASE, auth, cfg, in_thread, log, me, note, plugin_host

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
    out = {k: b[k] for k in keys if k in b}
    if "people" in b:                              # 👥 cal_share: users of this installation, e-mail addresses
        from aurora import cal_share
        out["people"] = cal_share.normalize(b["people"], me(), _names())
    return out


def _base():
    return BASE.base or BASE


def _names() -> list[str]:
    """The users of this installation (one alone before the multi-user: none to invite)."""
    from .users import _users
    try:
        return [u["name"] for u in _users().list()]
    except Exception:  # noqa: BLE001 — no users' store: nobody to invite
        return []


@router.get("/v1/aurora/calendar/people", dependencies=[Depends(auth)])
def calendar_people() -> dict:
    """The users one may invite (owner, 30 Oct: every user sees the others' names, nothing else of them)."""
    return {"users": [n for n in _names() if n != me()]}


def _confirmed(emails: list[str], yes) -> None:
    """Invitations to addresses go only on the person's word in the form (owner, 30 Oct: a notice, «procedere?»)."""
    if emails and not yes:
        raise HTTPException(status_code=409, detail={"confirm_email": emails})


def _mail(item: dict, to: list[str], method: str = "REQUEST") -> dict:
    """The invitation (or its cancellation) from the person's own mailbox (✉️ plugin): {"sent", "failed"}."""
    from aurora import cal_share, sys_disclosure
    if not to:
        return {"sent": [], "failed": []}
    host = plugin_host()
    p = host.get("email")
    if p is None or not p.available:
        return {"sent": [], "failed": [{"to": e, "why": "✉️ e-mail plugin not set up"} for e in to]}
    subject, body, ics = cal_share.invitation(item, _store().tz(cfg), me() or "", cfg.values.get("AURORA_EMAIL_USER") or "", method)
    body = sys_disclosure.mark_text(body, "it", cfg)        # EU AI Act art. 50: sent with an AI assistant
    sent, failed = [], []
    for e in to:
        r = host.call("email", "send_invite", {"to": e, "subject": subject, "body": body, "ics": ics})
        (sent.append(e) if r.get("ok") else failed.append({"to": e, "why": str(r.get("text", ""))[:200]}))
    log.info("audit: %s sent a calendar %s to %d address(es), %d failed", me(), method.lower(), len(sent), len(failed))
    return {"sent": sent, "failed": failed}


@router.post("/v1/aurora/calendar/items", dependencies=[Depends(auth)])
async def calendar_add(request: Request) -> dict:
    from aurora import cal_share
    cs = _store()
    b = await request.json()
    try:
        spec = _spec(b)
        _confirmed([p["email"] for p in spec.get("people", []) if p.get("email")], b.get("confirm_email"))
        it = cs.add(cfg, {**spec, "by": "page"})
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: %s added a calendar %s", me(), it["kind"])
    shared = await in_thread(cal_share.sync, _base(), me(), it)
    return {"item": it, "shared": shared, "mail": await in_thread(_mail, it, cal_share.emails_of(it))}


@router.get("/v1/aurora/calendar/items/{iid}", dependencies=[Depends(auth)])
def calendar_item(iid: str) -> dict:
    it = _store().get(cfg, iid)
    if it is None:
        raise HTTPException(status_code=404, detail="no such item")
    return {"item": it}


@router.put("/v1/aurora/calendar/items/{iid}", dependencies=[Depends(auth)])
async def calendar_change(iid: str, request: Request) -> dict:
    from aurora import cal_share
    cs = _store()
    b = await request.json()
    old = cs.get(cfg, iid)
    if old is None:
        raise HTTPException(status_code=404, detail="no such item")
    try:
        spec = _spec(b)
        if old.get("shared_from"):                 # another's appointment: only its alerts are this person's
            if set(spec) - {"alerts"}:
                raise HTTPException(status_code=403, detail=f"shared by {old['shared_from']['user']}: only your alerts change here")
            return {"item": cs.update(cfg, iid, spec)}
        before = cal_share.emails_of(old)
        _confirmed(cal_share.emails_of({"people": spec.get("people", old.get("people"))}) or before, b.get("confirm_email"))
        it = cs.update(cfg, iid, spec)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such item") from None
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    shared = await in_thread(cal_share.sync, _base(), me(), it, old)
    now = cal_share.emails_of(it)
    mail = await in_thread(_mail, it, now)
    off = await in_thread(_mail, it, [e for e in before if e not in now], "CANCEL")
    return {"item": it, "shared": shared, "mail": {"sent": mail["sent"] + off["sent"], "failed": mail["failed"] + off["failed"]}}


@router.delete("/v1/aurora/calendar/items/{iid}", dependencies=[Depends(auth)])
def calendar_delete(iid: str, occurrence: str | None = None, confirm_email: bool = False) -> dict:
    """The item, or (`occurrence`: its "YYYY-MM-DDTHH:MM") only that occurrence of a repeated one. Another's
    appointment: this person leaves it. One's own with people: their copies follow, the addresses told."""
    from aurora import cal_share
    cs = _store()
    old = cs.get(cfg, iid)
    if old is None:
        raise HTTPException(status_code=404, detail="no such item")
    if not old.get("shared_from"):
        _confirmed(cal_share.emails_of(old), confirm_email)
    try:
        left = cs.delete(cfg, iid, None if old.get("shared_from") else occurrence)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such item") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if old.get("shared_from"):
        cal_share.leave(_base(), me(), old)
        return {"deleted": iid, "item": None, "left": old["shared_from"]["user"]}
    if left:                                       # one occurrence skipped: the copies and the invitation too
        cal_share.sync(_base(), me(), left, old)
        return {"deleted": iid, "item": left, "mail": _mail(left, cal_share.emails_of(left))}
    cal_share.unshare(_base(), me(), old)
    return {"deleted": iid, "item": None, "mail": _mail(old, cal_share.emails_of(old), "CANCEL")}


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
