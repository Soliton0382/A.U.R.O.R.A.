# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎨 A project's models seen built, 🧮 its simulators (prj_view, prj_sim, ROADMAP N42) and 🖼️ its cover (prj_cover)."""
from __future__ import annotations

import base64

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from .core import auth, cfg

router = APIRouter()


@router.get("/v1/aurora/projects/{name}/scene", dependencies=[Depends(auth)])
def scene(name: str) -> dict:
    from aurora import prj_cover, prj_view
    try:
        return {"models": prj_view.scene(cfg, name), "materials": prj_view.MATERIALS, "cover": prj_cover.kind(cfg, name)}
    except ValueError:
        raise HTTPException(status_code=404, detail="no such project") from None


@router.get("/v1/aurora/projects/{name}/cad/{model}/part/{k}.stl", dependencies=[Depends(auth)])
def part_mesh(name: str, model: str, k: int, exploded: bool = False) -> FileResponse:
    from aurora import prj_view
    try:
        return FileResponse(prj_view.mesh(cfg, name, model, k, exploded), media_type="model/stl")
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="no such part") from None


@router.get("/v1/aurora/projects/{name}/sims", dependencies=[Depends(auth)])
def sims(name: str) -> dict:
    from aurora import prj_sim
    try:
        return {"sims": prj_sim.sims(cfg, name)}
    except ValueError:
        raise HTTPException(status_code=404, detail="no such project") from None


@router.get("/v1/aurora/projects/{name}/cover", dependencies=[Depends(auth)])
def cover(name: str) -> Response:
    from aurora import prj_cover
    try:
        got = prj_cover.get(cfg, name)
    except ValueError:
        got = None
    if got is None:
        raise HTTPException(status_code=404, detail="no cover")
    return Response(got[0], media_type=got[1], headers={"Cache-Control": "private, no-cache"})


@router.put("/v1/aurora/projects/{name}/cover", dependencies=[Depends(auth)])
def cover_set(name: str, body: dict = Body(...)) -> dict:
    """{"image": a data URL or base64 of a PNG/JPEG}: the page's picture as the project's cover."""
    from aurora import prj_cover
    raw = str(body.get("image") or "")
    try:
        data = base64.b64decode(raw.split(",", 1)[1] if raw.startswith("data:") else raw, validate=True)
        return {"bytes": prj_cover.put(cfg, name, data)}
    except (ValueError, base64.binascii.Error) as e:
        raise HTTPException(status_code=422, detail=str(e)[:200]) from None
