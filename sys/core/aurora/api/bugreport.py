# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Bug reports (sys_bugreport): the owner describes the bug, Aurora packs the logs needed with private data masked."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import auth, cfg, log

router = APIRouter()


@router.post("/v1/aurora/bugreport", dependencies=[Depends(auth)])
async def bugreport_make(request: Request) -> dict:
    from aurora import sys_bugreport, sys_features, sys_health
    body = await request.json()
    runs = [r for r in body.get("run_ids", []) if isinstance(r, str)]
    try:
        health = await asyncio.to_thread(sys_health.check, cfg)
        feats = {"features": sys_features.report(cfg), "config": sys_features.config_problems(cfg)}
        out = await asyncio.to_thread(sys_bugreport.build, cfg, str(body.get("description", "")), str(body.get("steps", "")),
                                      str(body.get("expected", "")), runs, float(body.get("hours", 6)), health, feats)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log.info("audit: bug report %s written (%d files, %d bytes, masked %s)", out["name"], len(out["files"]), out["bytes"],
             out["masked"])
    return {**out, "url": f"/v1/aurora/bugreports/{out['name']}"}


@router.get("/v1/aurora/bugreports", dependencies=[Depends(auth)])
def bugreports() -> list[dict]:
    from aurora import sys_bugreport
    return [{**r, "url": f"/v1/aurora/bugreports/{r['name']}"} for r in sys_bugreport.listing(cfg)]


@router.get("/v1/aurora/bugreports/{name}", dependencies=[Depends(auth)])
def bugreport_file(name: str):
    if not re.fullmatch(r"aurora-bug-\d{8}-\d{6}\.zip", name):
        raise HTTPException(status_code=404, detail="no such report")
    f = cfg.path("AURORA_BUGREPORT_DIR") / name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such report")
    return FileResponse(f, media_type="application/zip", filename=name)
