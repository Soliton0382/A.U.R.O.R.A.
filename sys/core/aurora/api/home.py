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
    data = r.content
    try:
        from aurora import local        # an installation's own filter of its cameras' pictures, when it has one
        made_safe = getattr(local, "camera_filter", None)
    except ImportError:
        made_safe = None
    if made_safe:
        try:
            data = await in_thread(lambda: made_safe(cfg, entity_id, r.content))
        except Exception as e:          # noqa: BLE001 — a filter that fails shows nothing, never the picture as it came
            raise HTTPException(status_code=502, detail=f"the camera's privacy filter failed: {str(e)[:120]}") from None
    return Response(data, media_type=r.headers.get("content-type", "image/jpeg"), headers={"Cache-Control": "no-store"})


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


@router.get("/v1/aurora/home/scenes", dependencies=[Depends(auth)])
def home_scenes() -> dict:
    """Aurora's own light scenes (hom_scenes): saved, and which are running."""
    from aurora import hom_scenes
    _host()
    return {"scenes": hom_scenes.load(cfg)["scenes"], "running": hom_scenes.running(me() or "")}


@router.post("/v1/aurora/home/scenes", dependencies=[Depends(auth)])
async def home_scene_save(request: Request) -> dict:
    """The guided editor of the 🏠 page: {"name", "lights", "switches", "colours", "every_s", "mode", "brightness",
    "minutes", "was"?} — any user's own scene on their own devices; `was` renames one."""
    from aurora import hom_scenes
    _host()
    b = await request.json()
    try:
        out = hom_scenes.save(cfg, str(b.get("name", "")), b.get("lights") or [], b.get("colours") or [],
                              b.get("every_s", 5), str(b.get("mode", "chase")), b.get("brightness", 80),
                              b.get("minutes", 0), b.get("switches") or [])
    except (hom_scenes.SceneError, TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    was = hom_scenes.key(str(b.get("was", "")))
    if was and was != hom_scenes.key(out["name"]):
        hom_scenes.stop_scene(cfg, was, me() or "")
        data = hom_scenes.load(cfg)
        data["scenes"].pop(was, None)
        hom_scenes._save(cfg, data)
    log.info("home scene %s saved by %s", out["name"], me())
    return out


@router.post("/v1/aurora/home/scenes/{name}/{action}", dependencies=[Depends(auth)])
async def home_scene(name: str, action: str, request: Request) -> dict:
    """▶ / ⏹ from the page: the user's own click (like a switch), written in the log. {"lights"}: the lights to try it
    on (a scene holds no lights of its own: the automations choose them)."""
    from aurora import hom_scenes
    _host()
    try:
        body = await request.json()
    except ValueError:
        body = {}
    try:
        if action == "start":
            lights = [str(x) for x in (body or {}).get("lights") or []][:hom_scenes.MAX_LIGHTS]
            out = hom_scenes.start(cfg, name, me() or "", log=log, lights=lights or None)
        elif action in ("stop", "off"):
            lights = [str(x) for x in (body or {}).get("lights") or [] if hom_scenes.ENTITY.fullmatch(str(x))]

            def stop():
                done = hom_scenes.stop_scene(cfg, name, me() or "", action == "off")
                if lights:                              # the lights it was tried on: a white one is over at once
                    hom_scenes.stop_on(cfg, lights, me() or "")
                    if action == "off":
                        hom_scenes._ha(cfg, "light/turn_off", {"entity_id": lights})
                return done or bool(lights)
            out = {"stopped": await in_thread(stop)}
        elif action == "delete":
            hom_scenes.stop_scene(cfg, name, me() or "")
            data = hom_scenes.load(cfg)
            out = {"deleted": data["scenes"].pop(hom_scenes.key(name), None) is not None}
            hom_scenes._save(cfg, data)
        else:
            raise HTTPException(status_code=404, detail="start, stop, off or delete")
    except hom_scenes.SceneError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    log.info("home scene %s: %s by %s", name, action, me())
    return out


@router.get("/v1/aurora/home/automations", dependencies=[Depends(auth)])
async def home_automations() -> dict:
    """🪄 The user's automations on every device (hom_auto), each with today's time when it has one."""
    from aurora import hom_auto
    _host()

    def work():
        autos = hom_auto.load(cfg)["automations"]
        try:
            sun = hom_auto._sun(cfg) if any(a["when"]["type"] in ("sunrise", "sunset") for a in autos) else None
        except (httpx.HTTPError, KeyError, ValueError):
            sun = None                                 # Home Assistant away: the list still shown, without the sun
        out = []
        for a in autos:
            try:
                at = hom_auto.at_today(cfg, a, sun) if (sun or a["when"]["type"] in ("manual", "time")) else None
            except (httpx.HTTPError, KeyError, ValueError):
                at = None
            out.append({**a, "today": at.strftime("%H:%M") if at else None})
        return {"automations": out, "sun": {k: v.strftime("%H:%M") for k, v in (sun or {}).items()}}
    return await in_thread(work)


@router.post("/v1/aurora/home/automations", dependencies=[Depends(auth)])
async def home_automation_save(request: Request) -> dict:
    """The guided editor: {"id"?, "name", "enabled", "when", "actions"} — any user's own, on their own devices."""
    from aurora import hom_auto
    _host()
    try:
        out = hom_auto.save(cfg, await request.json())
    except (hom_auto.AutoError, TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("home automation %s saved by %s", out["name"], me())
    return out


@router.post("/v1/aurora/home/automations/{aid}/{action}", dependencies=[Depends(auth)])
async def home_automation(aid: str, action: str) -> dict:
    """▶ (run now), on / off, delete: the user's own click, written in the log."""
    from aurora import hom_auto
    _host()
    a = next((x for x in hom_auto.load(cfg)["automations"] if x["id"] == aid), None)
    if a is None:
        raise HTTPException(status_code=404, detail="unknown automation")
    if action == "run":
        out = await in_thread(lambda: hom_auto.run(cfg, a, me() or "", log))
    elif action in ("on", "off"):
        out = hom_auto.save(cfg, {**a, "enabled": action == "on"})
    elif action == "delete":
        out = {"deleted": hom_auto.delete(cfg, aid)}
    else:
        raise HTTPException(status_code=404, detail="run, on, off or delete")
    log.info("audit: home automation %s: %s by %s", a["name"], action, me())
    return out
