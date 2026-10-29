# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📻 Internet radio for the player (aud_radio): the directory searched, the user's stations, a station played
through here — its address looked up by its id, a public one only."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .core import auth, cfg, in_thread, log, me

router = APIRouter()
MAX_STREAMS = 2                                   # per user: a radio here, one on the phone
_streams: dict[str, int] = {}
_lock = threading.Lock()


def _folder():
    d = cfg.path("AURORA_MUSIC_DIR")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


@router.get("/v1/aurora/radio", dependencies=[Depends(auth)])
def radio_state() -> dict:
    from aurora import aud_radio
    return {"presets": [{"tag": t, "label": n} for t, n in aud_radio.PRESETS], "favourites": aud_radio.favourites(_folder()),
            "genres": aud_radio.genres()}


@router.get("/v1/aurora/radio/search", dependencies=[Depends(auth)])
async def radio_search(q: str = "", tag: str = "") -> dict:
    from aurora import aud_radio
    if not q.strip() and not tag.strip():
        raise HTTPException(status_code=422, detail="a name or a genre")
    try:
        return {"stations": await in_thread(aud_radio.search, q, tag)}
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None


@router.post("/v1/aurora/radio/favourites", dependencies=[Depends(auth)])
async def radio_keep(request: Request) -> dict:
    """{"station": {id, name, tags}, "on": true|false}."""
    from aurora import aud_radio
    body = await request.json()
    try:
        return {"favourites": aud_radio.keep(_folder(), body.get("station") or {}, bool(body.get("on", True)))}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.get("/v1/aurora/radio/{sid}/stream", dependencies=[Depends(auth)])
async def radio_stream(sid: str):
    from aurora import aud_radio, net_public
    who = me() or ""
    try:
        url, name = await in_thread(aud_radio.stream_url, sid)
        client, r = await in_thread(net_public.open_stream, url, False, 20, aud_radio.UA)
    except (ValueError, RuntimeError, net_public.Refused) as e:
        raise HTTPException(status_code=404 if isinstance(e, ValueError) else 502, detail=str(e)) from None
    except Exception as e:                                   # noqa: BLE001 — the station is down: said
        raise HTTPException(status_code=502, detail=f"the station does not answer: {type(e).__name__}") from None
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith(("audio/", "application/ogg", "video/mp2t")):
        r.close()
        client.close()
        raise HTTPException(status_code=502, detail=f"the station answered {r.status_code} {r.headers.get('content-type', '')}")
    with _lock:
        if _streams.get(who, 0) >= MAX_STREAMS:
            r.close()
            client.close()
            raise HTTPException(status_code=429, detail=f"at most {MAX_STREAMS} radios at once")
        _streams[who] = _streams.get(who, 0) + 1
    log.info("radio: %s listens to %s", who, name[:80])

    def body():
        try:
            for chunk in r.iter_raw(16384):
                yield chunk
        finally:
            r.close()
            client.close()
            with _lock:
                _streams[who] = max(0, _streams.get(who, 1) - 1)
    return StreamingResponse(body(), media_type=r.headers.get("content-type", "audio/mpeg"),
                             headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
