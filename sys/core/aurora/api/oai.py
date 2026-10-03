# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""OpenAI-compatible API: the model list and chat completions (stream or not)."""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .core import answer_or_acquire, auth, cfg, final_text, quiet, start_run, text_of, trace_line, wait_events

router = APIRouter()


# ---- OpenAI-compatible -------------------------------------------------------------------
@router.get("/health")
def health() -> dict:
    """Public: alive, and how the WebUI's login looks (the API key, or users with password and code)."""
    return {"status": "ok", "login": "users" if str(cfg["AURORA_USER_MODE"]) == "multi" else "key"}


@router.get("/v1/models", dependencies=[Depends(auth)])
def models() -> dict:
    return {"object": "list", "data": [{"id": "aurora", "object": "model", "owned_by": "aurora"}]}


@router.post("/v1/chat/completions", dependencies=[Depends(auth)])
async def chat_completions(request: Request):
    body = await request.json()
    users = [m for m in body.get("messages", []) if m.get("role") == "user"]
    if not users:
        raise HTTPException(status_code=400, detail="no user message")
    question = text_of(users[-1].get("content"))            # every message is the first one
    run = start_run(question, origin="openai", job=lambda q, emit, run_id: answer_or_acquire(q, emit, run_id))
    cid, created = f"chatcmpl-{run['id']}", int(time.time())

    def chunk(delta: dict, finish: str | None = None) -> str:
        return "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": created, "model": "aurora",
                                      "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]},
                                     ensure_ascii=False) + "\n\n"

    if not body.get("stream"):
        after, reasoning = 0, []
        while True:
            events, done = await asyncio.to_thread(wait_events, run, after)
            after += len(events)
            reasoning += [line for e in events if (line := trace_line(e))]
            if done and after >= len(run["events"]):
                break
        return JSONResponse({"id": cid, "object": "chat.completion", "created": created, "model": "aurora",
                             "choices": [{"index": 0, "finish_reason": "stop",
                                          "message": {"role": "assistant", "content": final_text(run["answer"]),
                                                      "reasoning_content": "".join(reasoning)}}]})

    async def gen():
        yield chunk({"role": "assistant"})
        after = 0
        while True:
            events, done = await asyncio.to_thread(wait_events, run, after)
            after += len(events)
            for e in events:
                line = trace_line(e)
                if line:
                    yield chunk({"reasoning_content": line})
            if done and after >= len(run["events"]):
                break
        yield chunk({"content": final_text(run["answer"])})
        yield chunk({}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(quiet(gen()), media_type="text/event-stream")
