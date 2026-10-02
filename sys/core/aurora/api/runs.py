# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Runs: ask (with attachments), acquire, the run list, their live events, history."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .core import _runs, answer_or_acquire, auth, cfg, edit_pictures, make_video, picture_intent, pipeline, quiet, start_run, video_busy_answer, wait_events

router = APIRouter()


# ---- native: runs and events -----------------------------------------------------------------
@router.post("/v1/aurora/ask", dependencies=[Depends(auth)])
async def ask(request: Request) -> dict:
    """{"question": str, "attachments": [{"name", "mime", "data": base64}], "remember": true} -> {"run_id"}.

    "remember": false leaves the memory untouched (checks and tests must not become memories)."""
    body = await request.json()
    question = body.get("question", "").strip()
    remember = body.get("remember", True) is not False
    files = []
    if body.get("attachments"):
        from aurora.kno_attach import AttachmentHandler, is_image
        handler = AttachmentHandler(pipeline(), cfg)
        for a in body["attachments"]:
            name = os.path.basename(a.get("name") or "file")
            try:
                data = base64.b64decode(a.get("data", ""), validate=True)
                handler.check(name, data, a.get("mime", ""))
            except (binascii.Error, ValueError) as e:
                raise HTTPException(status_code=422, detail=str(e))
            files.append((name, data, a.get("mime", "")))
        if not question:
            question = ("Descrivi l'immagine." if all(is_image(n, m) for n, _, m in files)
                        else "Di cosa parla questo documento?")
    if not question:
        raise HTTPException(status_code=400, detail="empty question")
    def job(q, emit, run_id):
        attached = []
        if files and remember:                         # kept to show them again in the conversation (sys_uploads)
            from aurora import sys_uploads
            for name, data, mime in files:
                sys_uploads.save(cfg, run_id, name, mime, data)
        from aurora.kno_attach import is_image
        pictures = [(n, d) for n, d, m in files if is_image(n, m)]
        busy = video_busy_answer(q, emit, run_id)
        if busy:
            return busy
        if pictures:                                   # "anima questa foto": a video from the attached picture
            from aurora import mdl_video
            vp = mdl_video.plan(pipeline()._for("route"), q, True)
            if vp:
                return make_video(q, vp, pictures[0] if vp["from_picture"] else None, emit, run_id, remember)
        if pictures and picture_intent(q) == "edit":    # "ritagliala", "in bianco e nero": an edit, not a question
            return edit_pictures(q, pictures, emit, run_id, remember)
        if files:
            from aurora.kno_attach import AttachmentHandler
            attached = AttachmentHandler(pipeline(), cfg).prepare(files, q, emit, run_id)
        if attached or not remember:
            return pipeline().run(q, emit=emit, run_id=run_id, attached=attached, remember=remember)
        return answer_or_acquire(q, emit, run_id)
    return {"run_id": start_run(question, origin="webui", job=job)["id"]}


@router.post("/v1/aurora/acquire", dependencies=[Depends(auth)])
async def acquire(request: Request) -> dict:
    """An external action: the WebUI calls it only on the owner's click (AURORA_CONFIRM_EXTERNAL_ACTIONS)."""
    question = (await request.json()).get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="empty question")

    def job(q, emit, run_id):
        from aurora.kno_acquire import ArxivAgent
        return ArxivAgent(pipeline(), cfg).run(q, emit, run_id)
    return {"run_id": start_run(question, origin="acquire", job=job)["id"]}


@router.get("/v1/aurora/runs", dependencies=[Depends(auth)])
def runs() -> list[dict]:
    return [{"id": r["id"], "question": r["question"], "origin": r["origin"], "started": r["started"],
             "done": r["done"], "events": len(r["events"])} for r in reversed(_runs.values())]


@router.get("/v1/aurora/runs/{run_id}/events", dependencies=[Depends(auth)])
async def run_events(run_id: str, after: int = 0):
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="unknown run")

    async def gen():
        seen = after
        while True:
            events, done = await asyncio.to_thread(wait_events, run, seen)
            for e in events:
                yield f"data: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
            seen += len(events)
            if done and seen >= len(run["events"]):
                yield "event: end\ndata: {}\n\n"
                break
    return StreamingResponse(quiet(gen()), media_type="text/event-stream")
