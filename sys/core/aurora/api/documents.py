# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Documents Aurora wrote (PDF...), downloadable."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import auth, cfg, log

router = APIRouter()


# ---- documents ----------------------------------------------------------------------------------
@router.post("/v1/aurora/documents/pdf", dependencies=[Depends(auth)])
async def create_pdf(request: Request) -> dict:
    """{"title", "text" (Markdown)} -> a PDF in AURORA_DOCUMENTS_DIR, marked as AI-generated."""
    from aurora import doc_pdf, txt_lang
    body = await request.json()
    text, title = str(body.get("text", "")).strip(), str(body.get("title", "")).strip() or "Documento di Aurora"
    if not text:
        raise HTTPException(status_code=400, detail="empty document")
    try:
        p = await asyncio.to_thread(doc_pdf.create, title[:120], text, txt_lang.detect(text), cfg)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"name": p.name, "url": f"/v1/aurora/documents/{p.name}", "bytes": p.stat().st_size}


@router.get("/v1/aurora/documents", dependencies=[Depends(auth)])
def documents() -> list[dict]:
    d = cfg.path("AURORA_DOCUMENTS_DIR")
    files = sorted(d.glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True) if d.is_dir() else []
    return [{"name": f.name, "bytes": f.stat().st_size, "url": f"/v1/aurora/documents/{f.name}"} for f in files[:200]]


@router.get("/v1/aurora/documents/{name}", dependencies=[Depends(auth)])
def document(name: str):
    import re
    if not re.fullmatch(r"[a-z0-9-]+\.pdf", name):
        raise HTTPException(status_code=404, detail="no such document")
    f = cfg.path("AURORA_DOCUMENTS_DIR") / name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such document")
    # inline: the WebUI shows it in its viewer; the viewer's download button saves it (the link's download attribute)
    return FileResponse(f, media_type="application/pdf", filename=name, content_disposition_type="inline")


@router.delete("/v1/aurora/documents/{name}", dependencies=[Depends(auth)])
def document_delete(name: str) -> dict:
    """Only a PDF Aurora wrote (its metadata say Creator: Aurora): never one of the owner's own documents."""
    from aurora import doc_pdf
    f = cfg.path("AURORA_DOCUMENTS_DIR") / name
    if not re.fullmatch(r"[a-z0-9-]+\.pdf", name) or not f.is_file():
        raise HTTPException(status_code=404, detail="no such document")
    if not doc_pdf.made_by_aurora(f):
        raise HTTPException(status_code=403, detail="not a document Aurora wrote: delete it from its folder")
    from aurora import sys_trash
    tid = sys_trash.discard(cfg, f, "document")
    log.info("audit: document %s deleted (%s)", name, f"trash {tid}" if tid else "removed")
    return {"deleted": name, "trash": tid}
