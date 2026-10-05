# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Health page (owner, 2026-10-05): the user's diet, training and exams, sealed with their own key (hlt_store,
sys_seal). Only the user's own; never to a cloud model; a deletion is final."""
from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from .core import auth, cfg, log, me

router = APIRouter()


def _area(area: str) -> str:
    from aurora import hlt_store
    if area not in hlt_store.AREAS:
        raise HTTPException(status_code=404, detail="no such area")
    return area


@router.get("/v1/aurora/care", dependencies=[Depends(auth)])
def care() -> dict:
    from aurora import hlt_store, sys_seal
    sys_seal._key(cfg, cfg.user, "health")                 # the user's key, made at their first visit
    return {"areas": {a: hlt_store.items(cfg, a) for a in hlt_store.AREAS}}


@router.post("/v1/aurora/care/{area}", dependencies=[Depends(auth)])
async def care_add(area: str, request: Request) -> dict:
    """{"name", "data": base64, "title"?}: a document (PDF, image, text) of the user's, sealed."""
    from aurora import hlt_store
    body = await request.json()
    try:
        data = base64.b64decode(str(body.get("data", "")), validate=True)
        it = hlt_store.add_document(cfg, _area(area), str(body.get("name", "documento")), data, str(body.get("title", "")))
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e) or "data is not valid base64") from None
    log.info("audit: %s added a %s document (sealed, %d bytes)", me(), area, len(data))
    return it


@router.post("/v1/aurora/care/{area}/note", dependencies=[Depends(auth)])
async def care_note(area: str, request: Request) -> dict:
    from aurora import hlt_store
    body = await request.json()
    try:
        return hlt_store.add_note(cfg, _area(area), str(body.get("title", "")), str(body.get("text", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.get("/v1/aurora/care/{area}/{iid}", dependencies=[Depends(auth)])
def care_text(area: str, iid: str) -> dict:
    from aurora import hlt_store
    try:
        return {"text": hlt_store.text(cfg, _area(area), iid)}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/v1/aurora/care/{area}/{iid}/file", dependencies=[Depends(auth)])
def care_file(area: str, iid: str) -> Response:
    from aurora import hlt_store
    try:
        name, data = hlt_store.original(cfg, _area(area), iid)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.delete("/v1/aurora/care/{area}/{iid}", dependencies=[Depends(auth)])
def care_delete(area: str, iid: str) -> dict:
    from aurora import hlt_store
    try:
        hlt_store.delete(cfg, _area(area), iid)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    log.info("audit: %s deleted a %s item for good", me(), area)
    return {"deleted": iid}
