# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📱 Aurora's phone app, downloaded from the WebUI (owner, 25 Oct: «il pacchetto apk scaricabile dalla WebUI»): what
is offered (sys_phone_app) and the file. Logged in only, like every page."""
from __future__ import annotations

from aurora import sys_phone_app
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .core import auth, cfg, log

router = APIRouter()


@router.get("/v1/aurora/app", dependencies=[Depends(auth)])
def app_info() -> dict:
    return sys_phone_app.info(cfg)


@router.get("/v1/aurora/app/download", dependencies=[Depends(auth)])
def app_download() -> FileResponse:
    f = sys_phone_app.newest(cfg)
    if f is None:
        raise HTTPException(status_code=404, detail="no app built on this machine yet")
    log.info("audit: phone app downloaded: %s", f.name)
    return FileResponse(f, media_type="application/vnd.android.package-archive", filename=f.name,
                        headers={"Cache-Control": "no-cache"})
