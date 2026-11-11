# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Notifications and push: each user's choices, the history, the browsers' subscriptions and the delivery count
(moved out of api/routines, 12 Nov, which had passed 500 lines)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import _admin, auth, cfg, log, me
from .routines import _reader

router = APIRouter()


@router.get("/v1/aurora/notifications", dependencies=[Depends(auth)])
def notifications() -> dict:
    from aurora import sys_push
    lang = _reader()
    admin = me() == _admin()                        # each user their own choice; the machine's kinds the admin's
    return {"prefs": sys_push.prefs(cfg), "presets": sys_push.PRESETS, "subscriptions": sys_push.count(cfg),
            "chat_suggested": sys_push.CHAT_SUGGESTED,
            "kinds": [{"id": k, "label": v[lang], "it": v["it"], "en": v["en"]} for k, v in sys_push.KINDS.items()
                      if admin or k not in sys_push.MACHINE]}


@router.get("/v1/aurora/notifications/history", dependencies=[Depends(auth)])
def notifications_history(n: int = 200) -> list[dict]:
    from aurora import sys_push
    return sys_push.history(cfg, max(1, min(n, 500)))


@router.put("/v1/aurora/notifications", dependencies=[Depends(auth)])
async def notifications_set(request: Request) -> dict:
    from aurora import sys_push
    p = sys_push.set_prefs(cfg, await request.json())
    log.info("audit: notifications: push %s, webui %s, chat %s, masked %s", ",".join(p["push"]) or "-",
             ",".join(p["webui"]) or "-", ",".join(p["chat"]) or "-", ",".join(p["masked"]) or "-")
    return {"prefs": p}


@router.get("/v1/aurora/push", dependencies=[Depends(auth)])
def push_info() -> dict:
    from aurora import sys_push
    return {"public_key": sys_push.public_key(cfg), "subscriptions": sys_push.count(cfg),
            "events": [e.strip() for e in cfg["AURORA_PUSH_EVENTS"].split(",") if e.strip()]}


@router.post("/v1/aurora/push-ack")
async def push_ack(request: Request) -> dict:
    """The service worker got a push: no key (it has none), the push's random id is the proof (sys_push.ack)."""
    from aurora import sys_push
    try:
        body = json.loads((await request.body())[:2048])
    except ValueError:
        raise HTTPException(status_code=422, detail="bad body")
    return {"counted": await asyncio.to_thread(sys_push.ack, body.get("id"), body.get("endpoint", ""), cfg)}


@router.get("/v1/aurora/push/delivery", dependencies=[Depends(auth)])
def push_delivery(days: float = 7) -> dict:
    from aurora import sys_push
    return sys_push.delivery(cfg, max(1.0, min(days, 90)))


@router.post("/v1/aurora/push/{action}", dependencies=[Depends(auth)])
async def push_action(action: str, request: Request) -> dict:
    from aurora import sys_push
    body = await request.json() if action != "test" else {}
    if action == "subscribe":
        dev = getattr(request.state, "device", None)
        try:
            n = sys_push.subscribe(body.get("subscription"), (dev or {}).get("name") if isinstance(dev, dict) else None, cfg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        log.info("audit: push subscription added (%d in all)", n)
        return {"subscriptions": n}
    if action == "unsubscribe":
        n = sys_push.unsubscribe(str(body.get("endpoint", "")), cfg)
        log.info("audit: push subscription removed (%d left)", n)
        return {"subscriptions": n}
    if action == "test":
        msg = sys_push.message("test", {"text": "Aurora"}, cfg)
        from aurora import sys_line
        await asyncio.to_thread(sys_line.post, msg, cfg)              # the app's line too (aurora-app F2)
        return await asyncio.to_thread(sys_push.send, msg, cfg)
    raise HTTPException(status_code=404, detail="unknown action")
