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
from fastapi.responses import Response, StreamingResponse

from .core import BASE, auth, log, me

router = APIRouter()
PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "astro"            # sys/plugins/astro
SCRIPT, AGENT = PLUGIN / "astro_camera.ps1", PLUGIN / "astro_camera.py"
README = {"LEGGIMI.txt": """Aurora - la camera del PC del telescopio

1. Estrai questa cartella sul PC del telescopio (per esempio accanto allo script dell'inventario).
2. Chiudi il programma del collimatore (tiene occupata la camera).
3. Apri PowerShell in questa cartella e incolla il comando che ti dà la pagina di collimazione
   (Astro > Collimazione > Collimazione dal vivo > Collega il PC). Contiene la tua chiave: tienila per te.
4. La prima volta installa da solo, solo per il tuo utente: Python (con winget, se manca), poi OpenCV e pygrabber
   in una cartella sua (.aurora-camera) accanto a questi file. Servono internet e qualche minuto.
5. Nella pagina scegli la camera e premi Mostra: da li' regoli gain, esposizione, fuoco, zoom e risoluzione,
   da qualsiasi dispositivo. Ctrl+C nella finestra di PowerShell lo ferma.

Lo script non apre porte: manda soltanto. La chiave puo' solo mandare immagini, non legge niente di Aurora.
Se Aurora ha un certificato che il PC non riconosce, aggiungi -Insecure al comando. Solo l'elenco delle camere: -List.
Per togliere tutto: cancella questa cartella (e Python, se l'aveva installato lo script, da Impostazioni > App).
""", "README.txt": """Aurora - the telescope PC's camera

1. Unzip this folder on the telescope PC (beside the inventory script, for one).
2. Close the collimator's own program (it holds the camera).
3. Open PowerShell in this folder and paste the command the collimation page gives
   (Astro > Collimation > Live collimation > Link the PC). It holds your key: keep it to yourself.
4. The first time it installs, for your user only: Python (with winget, if missing), then OpenCV and pygrabber in a
   folder of its own (.aurora-camera) beside these files. It needs the internet and a few minutes.
5. In the page choose the camera and press Show: gain, exposure, focus, zoom and resolution are set from there, from
   any device. Ctrl+C in the PowerShell window stops it.

The script opens no port: it only sends. The key can only send pictures; it reads nothing of Aurora.
If Aurora's certificate is not trusted by the PC, add -Insecure to the command. Only the cameras' list: -List.
To remove it all: delete this folder (and Python, if the script installed it, from Settings > Apps).
"""}
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


@router.get("/v1/aurora/astro/camera/bundle", dependencies=[Depends(auth)])
def camera_bundle():
    """The PC's side zipped: the script that installs and starts, the agent, the instructions."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (SCRIPT, AGENT):
            z.write(f, f"aurora_camera/{f.name}")
        for name, text in README.items():
            z.writestr(f"aurora_camera/{name}", text.replace("\n", "\r\n"))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="aurora_camera.zip"'})


@router.get("/v1/aurora/astro/camera", dependencies=[Depends(auth)])
def camera_status() -> dict:
    return relay().status(me() or "")


@router.put("/v1/aurora/astro/camera", dependencies=[Depends(auth)])
async def camera_choose(request: Request) -> dict:
    """{wanted?, settings?}: the camera the PC should send ("" stops it), and what to ask of it (gain, exposure…)."""
    body = await request.json()
    if "wanted" in body:
        relay().want(me() or "", str(body.get("wanted") or ""))
    if isinstance(body.get("settings"), dict):
        try:
            relay().settings(me() or "", body["settings"])
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
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
    return relay().pc(who, names, body.get("camera"))


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
