# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Activity feed, logs, health, metrics, reflections, images, push and notifications."""
from __future__ import annotations

import asyncio
import json
import time

from aurora import sys_log
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from .core import MAX_ACTIVITY, _activity, _activity_cond, auth, cfg, note, pipeline, quiet

router = APIRouter()


# ---- activity, logs ----------------------------------------------------------------------------
@router.post("/v1/aurora/activity", dependencies=[Depends(auth)])
async def post_activity(request: Request) -> dict:
    """A service reports what it is doing: {"source", "event", "payload"} (shown in the WebUI)."""
    body = await request.json()
    item = note(str(body.get("source", "service"))[:40], str(body.get("event", "note"))[:60], body.get("payload") or {})
    sys_log.trace("activity", item["event"], item["payload"])
    return {"seq": item["seq"]}


@router.get("/v1/aurora/activity", dependencies=[Depends(auth)])
def get_activity(after: int = 0, limit: int = 200) -> list[dict]:
    with _activity_cond:
        return [a for a in _activity if a["seq"] > after][-max(1, min(limit, MAX_ACTIVITY)):]


@router.get("/v1/aurora/activity/stream", dependencies=[Depends(auth)])
async def activity_stream(after: int | None = None):
    """SSE of the activity feed from `after` (default: from now)."""
    def wait(seen: int) -> list[dict]:
        with _activity_cond:
            if not any(a["seq"] > seen for a in _activity):
                _activity_cond.wait(15)
            return [a for a in _activity if a["seq"] > seen]

    async def gen():
        with _activity_cond:
            seen = after if after is not None else (_activity[-1]["seq"] if _activity else 0)
        while True:
            items = await asyncio.to_thread(wait, seen)
            for a in items:
                yield f"data: {json.dumps(a, ensure_ascii=False, default=str)}\n\n"
                seen = a["seq"]
            if not items:
                yield ": keep-alive\n\n"
    return StreamingResponse(quiet(gen()), media_type="text/event-stream")


@router.get("/v1/aurora/logs", dependencies=[Depends(auth)])
def logs(hours: float = 24) -> dict:
    from aurora import sys_logread
    return {**sys_logread.inventory(cfg, hours), "answers": sys_logread.answer_stats(hours, cfg)}


@router.get("/v1/aurora/logs/{component}", dependencies=[Depends(auth)])
def log_tail(component: str, lines: int = 100, level: str | None = None) -> dict:
    from aurora import sys_logread
    try:
        return {"component": component, "lines": sys_logread.tail(component, lines, level, cfg)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/v1/aurora/runs/{run_id}/record", dependencies=[Depends(auth)])
def run_record(run_id: str) -> list[dict]:
    """A past run's events from the trace files (also after a restart of the API)."""
    from aurora import sys_logread
    return sys_logread.run_events(run_id, cfg)


_health_cache: dict = {"at": 0.0, "value": None}


@router.get("/v1/aurora/health", dependencies=[Depends(auth)])
def health_all() -> dict:
    from aurora import sys_health
    if time.time() - _health_cache["at"] > 10:
        _health_cache.update(at=time.time(), value=sys_health.check(cfg))
    return _health_cache["value"]


@router.get("/v1/aurora/reflections", dependencies=[Depends(auth)])
def reflections(type: str | None = None, n: int = 30) -> list[dict]:
    p = pipeline()
    if not p.reader.layout.shards("memory", "reflection"):
        return []
    items = [s for s in p.reader.recent(500, domain="reflection") if type is None or s.extra.get("type") == type]
    return [{"sid": s.sid, "type": s.extra.get("type"), "text": s.text, "created_at": s.created_at,
             "extra": {k: v for k, v in s.extra.items() if k not in ("turns", "fragments")}}
            for s in reversed(items[-max(1, min(n, 200)):])]
