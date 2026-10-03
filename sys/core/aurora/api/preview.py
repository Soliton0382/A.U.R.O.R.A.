# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A PDF's pages as pictures for the WebUI's viewer (doc_preview): how many pages, and one page."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import auth, cfg

router = APIRouter()


@router.post("/v1/aurora/artifacts/open", dependencies=[Depends(auth)])
async def artifact_open(request: Request) -> dict:
    """{"url": an artifact's file url} -> {"url": its sandboxed page, valid 10 minutes} (doc_artifact)."""
    from aurora import doc_artifact
    try:
        tok = doc_artifact.open_token(cfg, str((await request.json()).get("url", "")))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"url": f"/v1/preview/{tok}/", "seconds": doc_artifact.TTL_S}


@router.get("/v1/aurora/preview", dependencies=[Depends(auth)])
async def preview_info(url: str) -> dict:
    from aurora import doc_preview
    try:
        path = doc_preview.resolve(cfg, url)
        return {"pages": await asyncio.to_thread(doc_preview.pages, path), "name": path.name}
    except doc_preview.PreviewError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/v1/aurora/preview/page", dependencies=[Depends(auth)])
async def preview_page(url: str, n: int = 1):
    from aurora import doc_preview
    try:
        png = await asyncio.to_thread(doc_preview.page_png, cfg, doc_preview.resolve(cfg, url), n)
    except doc_preview.PreviewError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
