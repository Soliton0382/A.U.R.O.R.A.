# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛟 Assistance (sys_assist): the user opens a window and sees its log; the admin enters the account and leaves it.
Inside, core.auth makes every request of the admin's device the user's and refuses sys_assist.NEVER."""
from __future__ import annotations

from aurora import sys_assist, sys_context, sys_user_config
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import BASE, _admin, auth, log, me, note
from .users import admin_only

router = APIRouter()


def _base():
    return BASE.base or BASE


def tell(user: str, event: str, text: str) -> None:
    """A notification to the user (their own, not the admin's): the assistance began or ended."""
    with sys_context.acting_as(user):
        note("assist", event, {"title": text, "text": text})


def ended(user: str, why: str) -> None:
    """The assistance of a user is over: in their log, and told to them."""
    sys_assist.step(sys_user_config.for_user(_base(), user), _admin() or "", "end", why)
    tell(user, "assist.end", {"revoke": "Hai chiuso l'assistenza: l'amministratore non può più entrare nel tuo account.",
                              "leave": "L'amministratore è uscito dal tuo account.",
                              "time": "L'assistenza è scaduta: l'amministratore non può più entrare nel tuo account."}[why])


def expire_due() -> None:
    """aurora-rem's tick (routines.routine_tick): the windows ended by their time, each user told."""
    for e in sys_assist.expire(_base()):
        ended(e["user"], "time")


@router.get("/v1/aurora/assist", dependencies=[Depends(auth)])
def assist_state(request: Request) -> dict:
    """My window (open until, the admin inside now) and my log; inside an account, the session too."""
    who, base = me(), _base()
    return {"windows": list(sys_assist.WINDOWS), "grant": sys_assist.granted(base, who),
            "inside": sys_assist.inside(base, who), "session": getattr(request.state, "assist", None),
            "admin": who == _admin(), "log": sys_assist.log(sys_user_config.for_user(base, who))}


@router.post("/v1/aurora/assist/grant", dependencies=[Depends(auth)])
async def assist_grant(request: Request) -> dict:
    """{"hours": 8|16|24|48|72}: the user lets the admin in for that long (the disclaimer on the page: the consent)."""
    who = me()
    if who == _admin():
        raise HTTPException(status_code=422, detail="the admin's own account has no assistance")
    body = await request.json()
    try:
        g = sys_assist.grant(_base(), who, int(body.get("hours", 0)))
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    sys_assist.step(sys_user_config.for_user(_base(), who), who, "grant", f"{g['hours']} h")
    log.info("audit: %s opened the assistance for %d h", who, g["hours"])
    return {"grant": g}


@router.post("/v1/aurora/assist/revoke", dependencies=[Depends(auth)])
def assist_revoke() -> dict:
    who = me()
    if not sys_assist.granted(_base(), who):
        return {"revoked": False}
    sys_assist.revoke(_base(), who)
    log.info("audit: %s closed the assistance", who)
    ended(who, "revoke")
    return {"revoked": True}


@router.post("/v1/aurora/assist/enter", dependencies=[Depends(admin_only)])
async def assist_enter(request: Request) -> dict:
    """{"user"}: the admin's device enters that user's account (their window open). A device only: not the API key."""
    dev = getattr(request.state, "device", None)
    if not dev:
        raise HTTPException(status_code=422, detail="from a device of the WebUI, not with the API key")
    user = str((await request.json()).get("user", ""))
    try:
        s = sys_assist.enter(_base(), dev["id"], user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None
    admin = _admin() or ""
    sys_assist.step(sys_user_config.for_user(_base(), user), admin, "enter", dev.get("name", ""))
    log.info("audit: %s entered %s's account (assistance)", admin, user)
    tell(user, "assist.begin", "L'amministratore è entrato nel tuo account per assisterti: ogni passo è nel registro "
                               "della pagina 👥 Utenti → 🛟 Assistenza.")
    return {"session": s}


@router.post("/v1/aurora/assist/leave", dependencies=[Depends(auth)])
def assist_leave(request: Request) -> dict:
    s = getattr(request.state, "assist", None)
    dev = getattr(request.state, "device", None)
    if not s or not dev:
        return {"left": False}
    sys_assist.leave(_base(), dev["id"])
    log.info("audit: %s left %s's account (assistance)", s["by"], s["user"])
    ended(s["user"], "leave")
    return {"left": True}
