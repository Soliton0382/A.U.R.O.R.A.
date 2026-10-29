# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📻 Internet radio for the player (aud_radio): the directory searched, the user's stations, a station played
through here — its address looked up by its id, a public one only."""
from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .core import auth, cfg, in_thread, log, me

router = APIRouter()
MAX_STREAMS = 2                                   # per user: a radio here, one on the phone
_streams: dict[str, list] = {}                    # per user: the station responses open, the oldest first
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
    # one more than MAX_STREAMS: the oldest is closed, never the new one refused (owner, 29 Oct: «clicco ma non
    # vanno» — a sync body was never closed when the player let it go, its count stayed, every ▶ after two got 429)
    with _lock:
        mine = _streams.setdefault(who, [])
        while len(mine) >= MAX_STREAMS:
            mine.pop(0).close()
        mine.append(r)
    log.info("radio: %s listens to %s", who, name[:80])

    async def body():
        chunks = r.iter_raw(16384)
        try:
            while True:
                chunk = await asyncio.to_thread(next, chunks, None)
                if not chunk:
                    break
                yield chunk
        except Exception:                                   # noqa: BLE001 — closed (a newer radio) or the station gone
            pass
        finally:                                            # the player gone too: Starlette cancels this, it runs
            r.close()
            client.close()
            with _lock:
                if r in _streams.get(who, []):
                    _streams[who].remove(r)
    return StreamingResponse(body(), media_type=r.headers.get("content-type", "audio/mpeg"),
                             headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
