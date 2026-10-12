# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🏠 Casa: the devices of the user's Home Assistant on a page of their own (owner, 2026-10-12: «una pagina dedicata nel
menù per home assistant quando risulta attivo… si possono gestire i device che espone»).

The devices with their entities (the plugin's `devices`), the agents that watch each one and Aurora's open proposals for
it (hom_devices), a camera's picture and its description. A command from this page is the user's own click on their
own device — the approval is the click — limited to the simple services of ALLOWED and written in the audit log;
anything else stays with the chat and its approvals.
"""
from __future__ import annotations

import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from aurora.hom_devices import ALLOWED, watching

from .core import auth, cfg, in_thread, log, me, pipeline, plugin_host

router = APIRouter()
ENTITY = re.compile(r"[a-z_]+\.[a-z0-9_]{1,120}")


def _host():
    p = plugin_host().get("homeassistant")
    if p is None or not p.available:
        raise HTTPException(status_code=409, detail="the homeassistant plugin is not on")
    return plugin_host()


def _devices() -> list[dict]:
    out = _host().call("homeassistant", "devices", {})
    if not out["ok"]:
        raise HTTPException(status_code=502, detail=f"Home Assistant: {out['text'][:200]}")
    return json.loads(out["text"])


@router.get("/v1/aurora/home/devices", dependencies=[Depends(auth)])
async def home_devices() -> dict:
    from aurora import sys_routine_advice, sys_routines

    def work():
        ready = {p.name for p in plugin_host().plugins(with_tools=False) if p.available}
        return watching(_devices(), sys_routines.all_routines(cfg), sys_routine_advice.current(cfg, ready)["items"])
    return {"devices": await in_thread(work), "level": int(cfg["AURORA_HA_DEVICE_AGENTS"]), "allowed":
            {k: sorted(v) for k, v in ALLOWED.items()}}


@router.post("/v1/aurora/home/service", dependencies=[Depends(auth)])
async def home_service(request: Request) -> dict:
    """{"entity_id", "service", "data"?}: the user's click on one of their devices."""
    body = await request.json()
    eid, service = str(body.get("entity_id", "")), str(body.get("service", ""))
    domain = eid.split(".", 1)[0]
    if not ENTITY.fullmatch(eid) or service not in ALLOWED.get(domain, ()):
        raise HTTPException(status_code=422, detail=f"not from this page: {domain}.{service}")
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    if domain == "number":
        data = {"value": float(data.get("value", 0))}
    out = await in_thread(lambda: _host().call("homeassistant", "call_service",
                                               {"domain": domain, "service": service, "entity_id": eid, "data": data}))
    log.info("audit: %s ran %s.%s on %s from the 🏠 page: %s", me(), domain, service, eid, "ok" if out["ok"] else "failed")
    if not out["ok"]:
        raise HTTPException(status_code=502, detail=out["text"][:200])
    return {"ok": True, "text": out["text"]}


@router.get("/v1/aurora/home/camera/{entity_id}", dependencies=[Depends(auth)])
async def home_camera(entity_id: str) -> Response:
    """A camera's picture now, straight from Home Assistant (the user's own address and token)."""
    _host()
    if not ENTITY.fullmatch(entity_id) or not entity_id.startswith("camera."):
        raise HTTPException(status_code=422, detail="a camera entity is needed")
    url, token = str(cfg["AURORA_HA_URL"]).rstrip("/"), str(cfg["AURORA_HA_TOKEN"])
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{url}/api/camera_proxy/{entity_id}", headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Home Assistant {r.status_code}")
    return Response(r.content, media_type=r.headers.get("content-type", "image/jpeg"), headers={"Cache-Control": "no-store"})


@router.post("/v1/aurora/home/look", dependencies=[Depends(auth)])
async def home_look(request: Request) -> dict:
    """{"entity_id"}: what the camera sees, in words (Aurora's own vision, on this machine)."""
    eid = str((await request.json()).get("entity_id", ""))
    if not ENTITY.fullmatch(eid) or not eid.startswith("camera."):
        raise HTTPException(status_code=422, detail="a camera entity is needed")
    out = await in_thread(lambda: _host().call("homeassistant", "camera_look", {"entity_id": eid}))
    log.info("audit: %s asked what %s sees", me(), eid)
    return {"ok": out["ok"], "text": out["text"]}


@router.post("/v1/aurora/home/agents/{device_id}", dependencies=[Depends(auth)])
async def home_agents(device_id: str) -> dict:
    """Aurora proposes again the agents for one device (in 🤖 Agenti e routine, with «Applica»)."""
    from aurora import hom_devices, sys_routine_advice

    def work():
        d = next((x for x in _devices() if x.get("id") == device_id), None)
        if d is None:
            raise HTTPException(status_code=404, detail="no such device")
        props = hom_devices.proposals(pipeline()._for("service"), d)
        return {"proposed": sys_routine_advice.remember(cfg, props, reviewed=False), "seen": len(props)}
    return await in_thread(work)
