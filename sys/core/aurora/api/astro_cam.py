# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📡 The telescope PC's camera relayed (ast_camrelay; owner, 19 Oct: «un server da installare nel mini PC in modo che
invii in streaming quello che vede la camera che si sceglie»). Two sides:
  the PC (its script, astro_camera.ps1) — with the camera key in X-Aurora-Camera, never a login: tells its cameras and
    hears which one is wanted (/pc), sends that one's frames (/push);
  the person's pages — logged in: make the key and download the script, choose the camera, see the last frame or the
    stream (the live collimation)."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from .core import BASE, auth, log, me

router = APIRouter()
SCRIPT = Path(__file__).resolve().parents[3] / "plugins" / "astro" / "astro_camera.ps1"   # sys/plugins/astro
STREAM_S = 1800                      # a page's stream ends after this; the page opens it again
_relay = None


def relay():
    global _relay
    if _relay is None:
        from aurora.ast_camrelay import Relay
        _relay = Relay((BASE.base or BASE).path("AURORA_STATUS_DIR"))
    return _relay


def _pc(request: Request) -> str:
    """The person whose camera key the PC holds; 401 otherwise."""
    who = relay().who(request.headers.get("x-aurora-camera", "").strip())
    if not who:
        raise HTTPException(status_code=401, detail="camera key missing or unknown")
    return who


@router.post("/v1/aurora/astro/camera/key", dependencies=[Depends(auth)])
def camera_key(request: Request) -> dict:
    """A new camera key for this person (the old one stops working), given once, with the PC's command."""
    key = relay().new_key(me() or "")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    url = f"{proto}://{request.headers.get('host', '')}"
    log.info("audit: %s made a camera key", me())
    return {"key": key, "url": url,
            "command": f"powershell -ExecutionPolicy Bypass -File .\\{SCRIPT.name} -Url {url} -Key {key}"}


@router.get("/v1/aurora/astro/camera/script", dependencies=[Depends(auth)])
def camera_script():
    return FileResponse(SCRIPT, media_type="text/plain", filename=SCRIPT.name)


@router.get("/v1/aurora/astro/camera", dependencies=[Depends(auth)])
def camera_status() -> dict:
    return relay().status(me() or "")


@router.put("/v1/aurora/astro/camera", dependencies=[Depends(auth)])
async def camera_choose(request: Request) -> dict:
    """{wanted}: the camera the PC should send ("" stops it)."""
    name = str((await request.json()).get("wanted") or "")
    relay().want(me() or "", name)
    return relay().status(me() or "")


@router.get("/v1/aurora/astro/camera/frame", dependencies=[Depends(auth)])
def camera_frame():
    frame, _ = relay().last(me() or "")
    if frame is None:
        raise HTTPException(status_code=404, detail="no live frame: is the PC's script running with a camera chosen?")
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/v1/aurora/astro/camera/stream", dependencies=[Depends(auth)])
async def camera_stream(request: Request):
    """The frames as they come, multipart/x-mixed-replace (an <img> shows it); ends when the camera stops."""
    user, r = me() or "", relay()

    async def frames():
        seen, start, quiet = -1, time.time(), time.time()
        while time.time() - start < STREAM_S and not await request.is_disconnected():
            n = r.number(user)
            if n != seen:
                frame, _ = r.last(user)
                if frame is not None:
                    seen, quiet = n, time.time()
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode()
                           + b"\r\n\r\n" + frame + b"\r\n")
            elif time.time() - quiet > 30:
                return
            await asyncio.sleep(0.04)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/v1/aurora/astro/camera/pc")
async def camera_pc(request: Request) -> dict:
    """{devices}: the PC's cameras; answered with the one wanted."""
    who = _pc(request)
    body = await request.json()
    names = body.get("devices")
    names = names if isinstance(names, list) else [names] if isinstance(names, str) and names else []   # one: a string
    return {"wanted": relay().devices(who, names)}


@router.post("/v1/aurora/astro/camera/push")
async def camera_push(request: Request) -> dict:
    """The wanted camera's frames, mpjpeg in one long POST; ends (and the PC's ffmpeg with it) when another is chosen."""
    from aurora.ast_camrelay import Frames
    who = _pc(request)
    r, parser, n = relay(), Frames(), 0
    wanted = r.wanted(who)
    try:
        async for chunk in request.stream():
            for frame in parser.feed(chunk):
                r.put(who, frame)
                n += 1
            if r.wanted(who) != wanted:
                break
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"frames": n}
