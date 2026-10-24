# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌍 The interpreter's one call (kno_interpret, ROADMAP N44): a sentence recorded by the page (or typed), heard in the
speaker's language and translated into the other. Nothing is remembered."""
from __future__ import annotations

import base64
import binascii
import time

from aurora import sys_features
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .core import auth, cfg, log, pipeline

router = APIRouter()


@router.post("/v1/aurora/interpret", dependencies=[Depends(auth)])
async def interpret(request: Request) -> dict:
    """{"from", "to", "data" (base64 audio) or "text", "before": [the last lines]} -> {"heard", "text", "seconds"}."""
    from aurora import kno_interpret, sns_av
    body = await request.json()
    try:
        src, dst = kno_interpret.check(body.get("from"), body.get("to"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    before = body.get("before") if isinstance(body.get("before"), list) else []
    seconds, heard = {}, str(body.get("text") or "").strip()[:2000]
    if body.get("data"):
        try:
            sys_features.need(cfg, "speech", src)
        except sys_features.Missing as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        try:
            data = base64.b64decode(str(body["data"]), validate=True)
        except binascii.Error:
            raise HTTPException(status_code=422, detail="data is not valid base64") from None
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="audio larger than 20 MB")
        t0 = time.time()
        try:
            audio = await run_in_threadpool(sns_av.decode, data, cfg)
            out = await run_in_threadpool(sns_av.transcribe, audio, src, cfg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from None
        seconds["hear"] = round(time.time() - t0, 2)
        heard = str(out.get("text") or "").strip() if out.get("clear") else ""
    if not heard:
        return {"heard": "", "text": "", "from": src, "to": dst, "seconds": seconds}
    t0 = time.time()
    try:
        text = await run_in_threadpool(kno_interpret.translate, pipeline()._for("translate"), heard, src, dst, before)
    except Exception as e:                            # noqa: BLE001 — the model's failure, said to the page
        log.warning("interpreter: translation failed: %s", e)
        raise HTTPException(status_code=503, detail=f"translation failed: {e}") from None
    seconds["translate"] = round(time.time() - t0, 2)
    log.info("audit: interpreter %s → %s, %d characters", src, dst, len(heard))
    return {"heard": heard, "text": text, "from": src, "to": dst, "seconds": seconds}
