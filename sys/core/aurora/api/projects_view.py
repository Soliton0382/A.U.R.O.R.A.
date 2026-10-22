# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎨 A project's models seen built and 🧮 its simulators (prj_view, prj_sim, ROADMAP N42)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .core import auth, cfg

router = APIRouter()


@router.get("/v1/aurora/projects/{name}/scene", dependencies=[Depends(auth)])
def scene(name: str) -> dict:
    from aurora import prj_view
    try:
        return {"models": prj_view.scene(cfg, name), "materials": prj_view.MATERIALS}
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
