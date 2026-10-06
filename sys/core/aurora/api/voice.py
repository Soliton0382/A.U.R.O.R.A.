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
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})
