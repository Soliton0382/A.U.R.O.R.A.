# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖨️ A project's models for a 3D printer (prj_print, ROADMAP N41): the list, and one zip per model."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .core import auth, cfg

router = APIRouter()


@router.get("/v1/aurora/projects/{name}/cad", dependencies=[Depends(auth)])
def print_models(name: str) -> dict:
    from aurora import prj_print
    try:
        return {"models": prj_print.models(cfg, name)}
    except ValueError:
        raise HTTPException(status_code=404, detail="no such project") from None


@router.get("/v1/aurora/projects/{name}/cad/{model}/print.zip", dependencies=[Depends(auth)])
def print_zip(name: str, model: str, lang: str = "it") -> Response:
    from aurora import prj_print
    try:
        data = prj_print.bundle(cfg, name, model, lang)
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="no printable model") from None
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}-{model}-stampa3d.zip"'})
