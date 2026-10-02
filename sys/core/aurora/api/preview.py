# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A PDF's pages as pictures for the WebUI's viewer (doc_preview): how many pages, and one page."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .core import auth, cfg

router = APIRouter()


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
