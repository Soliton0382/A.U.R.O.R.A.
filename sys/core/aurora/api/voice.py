# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's voice made on this machine (mdl_tts): for the devices with no voice of their own."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .core import auth, cfg, log

router = APIRouter()


@router.get("/v1/aurora/tts", dependencies=[Depends(auth)])
def tts_state() -> dict:
    from aurora import mdl_tts
    return mdl_tts.available(cfg)


@router.post("/v1/aurora/tts", dependencies=[Depends(auth)])
async def tts(request: Request) -> Response:
    """{"text", "lang"} -> audio/wav, spoken on this machine's CPU."""
    from aurora import mdl_tts
    body = await request.json()
    try:
        data = await run_in_threadpool(mdl_tts.speak, cfg, str(body.get("text", "")), str(body.get("lang", "it")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except RuntimeError as e:
        log.warning("tts: %s", e)
        raise HTTPException(status_code=503, detail=str(e)) from None
    if body.get("format") == "mp3":                   # the WebUI: 5.5x lighter on a phone (M125: 1.5 MB → 274 KB, 0.10 s)
        mp3 = await run_in_threadpool(_mp3, data)
        if mp3:
            return Response(mp3, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})


def _mp3(wav: bytes) -> bytes | None:
    """The WAV as a 64 kb/s mono MP3 (ffmpeg); None when ffmpeg is missing or fails: the WAV goes instead."""
    import subprocess
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-b:a", "64k",
                              "-f", "mp3", "pipe:1"], input=wav, capture_output=True, timeout=60)
        return out.stdout if out.returncode == 0 and out.stdout else None
    except (OSError, subprocess.SubprocessError):
        return None
