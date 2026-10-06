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


_reading: dict[str, str] = {}                        # exam id -> "reading" | "N values" | "error: ..."


def read_values(doc_id: str) -> None:
    """The exam's values read by the LOCAL model (pipeline().llm: never a cloud model), in a thread of this user."""
    from aurora import hlt_labs, sys_context
    from .core import pipeline
    _reading[doc_id] = "reading"

    def work():
        try:
            _reading[doc_id] = f"{len(hlt_labs.extract(cfg, doc_id, pipeline().llm))} values"
        except Exception as e:                            # noqa: BLE001 — told on the page, the document stays
            _reading[doc_id] = f"error: {type(e).__name__}"
            log.warning("exam values not read: %s", type(e).__name__)
    sys_context.start(work, name="exam-values")


@router.get("/v1/aurora/health/values", dependencies=[Depends(auth)])
def health_values() -> dict:
    """Each test over time (hlt_labs.series), and which exams are being read now."""
    from aurora import hlt_labs
    return {"series": hlt_labs.series(cfg), "reading": dict(_reading)}


@router.post("/v1/aurora/health/values/read/{doc_id}", dependencies=[Depends(auth)])
def health_values_read(doc_id: str) -> dict:
    """Read an exam's values again (a model that missed some, an exam added before this existed)."""
    from aurora import hlt_store
    if not any(i["id"] == doc_id for i in hlt_store.items(cfg, "exams")):
        raise HTTPException(status_code=404, detail="no such exam")
    read_values(doc_id)
    return {"reading": doc_id}


@router.put("/v1/aurora/health/values/{vid}", dependencies=[Depends(auth)])
async def health_value_fix(vid: str, request: Request) -> dict:
    from aurora import hlt_labs
    try:
        return hlt_labs.correct(cfg, vid, await request.json())
    except KeyError:
        raise HTTPException(status_code=404, detail="no such value") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.delete("/v1/aurora/health/values/{vid}", dependencies=[Depends(auth)])
def health_value_delete(vid: str) -> dict:
    from aurora import hlt_labs
    if not hlt_labs.remove(cfg, vid=vid):
        raise HTTPException(status_code=404, detail="no such value")
    return {"deleted": vid}


@router.get("/v1/aurora/care/doctors", dependencies=[Depends(auth)])
def doctors() -> dict:
    from aurora import hlt_doctor, sys_seal
    sys_seal._key(cfg, cfg.user, "health")
    return {"doctors": hlt_doctor.load(cfg), "days": list(hlt_doctor.DAYS)}


@router.put("/v1/aurora/care/doctors", dependencies=[Depends(auth)])
async def doctors_save(request: Request) -> dict:
    """{"doctors": [{role, name, phone, address, booking, notes, hours: {mon: {am, pm}...}}]}: all the cards, sealed."""
    from aurora import hlt_doctor
    body = await request.json()
    if not isinstance(body.get("doctors"), list):
        raise HTTPException(status_code=422, detail="doctors: a list")
    cards = hlt_doctor.save(cfg, body["doctors"])
    log.info("audit: %s saved %d doctors' cards (sealed)", me(), len(cards))
    return {"doctors": cards}


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
    if area == "exams":                                  # its values read by the local model, in the background
        read_values(it["id"])
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
        if area == "exams":
            from aurora import hlt_labs
            hlt_labs.remove(cfg, doc=iid)                 # its values go with it
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    log.info("audit: %s deleted a %s item for good", me(), area)
    return {"deleted": iid}
