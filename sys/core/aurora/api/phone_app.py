# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📱 Aurora's phone app, downloaded from the WebUI (owner, 25 Oct: «il pacchetto apk scaricabile dalla WebUI»): what
is offered (sys_phone_app) and the file. Logged in only, like every page."""
from __future__ import annotations

from aurora import sys_phone_app
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import auth, cfg, log

router = APIRouter()


@router.get("/v1/aurora/app", dependencies=[Depends(auth)])
def app_info(request: Request) -> dict:
    """What is offered, and the phones of this user whose line is open or was (since the API started)."""
    from aurora import sys_line
    return {**sys_phone_app.info(cfg), "lines": sys_line.lines(getattr(request.state, "user", None))}


@router.get("/v1/aurora/app/download", dependencies=[Depends(auth)])
def app_download() -> FileResponse:
    f = sys_phone_app.newest(cfg)
    if f is None:
        raise HTTPException(status_code=404, detail="no app built on this machine yet")
    log.info("audit: phone app downloaded: %s", f.name)
    return FileResponse(f, media_type="application/vnd.android.package-archive", filename=f.name,
                        headers={"Cache-Control": "no-cache"})


# 🖥️ N169 (owner, 27 Nov): Aurora's window for a computer where Aurora is not — the WebUI's window, its address form
# (the Android app's), its notifications; installed by its own script for the user, nothing as root (desk/client)
@router.get("/v1/aurora/app/desk", dependencies=[Depends(auth)])
def desk_download():
    import sys
    from pathlib import Path
    from fastapi.responses import Response
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from desk.client import package
    log.info("audit: desktop app downloaded")
    return Response(package.build(), media_type="application/gzip",
                    headers={"Content-Disposition": 'attachment; filename="aurora-desk-client.tar.gz"', "Cache-Control": "no-cache"})
