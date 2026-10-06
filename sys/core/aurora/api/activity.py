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

from .core import MAX_ACTIVITY, _activity, _activity_cond, _run_lock, auth, cfg, log, me, mine, note, pipeline, quiet

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
    who = me()
    with _activity_cond:
        return [a for a in _activity if a["seq"] > after and mine(a, who)][-max(1, min(limit, MAX_ACTIVITY)):]


@router.get("/v1/aurora/activity/stream", dependencies=[Depends(auth)])
async def activity_stream(after: int | None = None):
    """SSE of the activity feed from `after` (default: from now): the requesting user's items only."""
    who = me()                                          # taken now, in the request: the stream keeps it

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
                seen = a["seq"]
                if mine(a, who):
                    yield f"data: {json.dumps(a, ensure_ascii=False, default=str)}\n\n"
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


@router.get("/v1/aurora/soak", dependencies=[Depends(auth)])
def soak(days: int = 14) -> list[dict]:
    """The daily snapshots of the soak (aurora-rem writes one a day): memory and restarts per service, logs, swaps."""
    from aurora import sys_soak
    return sys_soak.days(cfg, max(1, min(days, 60)))


_down: set[str] = set()


def watch_health(every_s: int = 120) -> None:
    """Every two minutes: a check that went down (a service, the disk) is told to the admin, and when all is fine
    again (owner, 2026-10-04: no alert existed, a stopped service was seen only on the Status page)."""
    from aurora import sys_context, sys_health
    from .core import _admin
    while True:
        time.sleep(every_s)
        try:
            items = health_all()["items"]
            change = sys_health.health_change(items, _down)
            if change:
                with sys_context.acting_as(_admin()):
                    note("health", change[0], {"text": change[1]})
            _down.clear()
            _down.update(i["name"] for i in items if i["level"] == "down")
        except Exception:  # noqa: BLE001 — the watcher never dies
            continue


@router.get("/v1/aurora/video/status", dependencies=[Depends(auth)])
def video_status() -> dict:
    """A video (or another GPU job with the reasoner stopped) in progress: title, start, expected end, a percent that is
    the time gone over the time estimated — an estimate, said as such in the chat (owner, 2026-10-06)."""
    from .core import gpu_busy
    v = gpu_busy()
    if not v:
        return {"busy": False}
    span = max(60.0, v["ready_at"] - v["started"])
    return {"busy": True, "title": v["title"], "started": v["started"], "ready_at": v["ready_at"],
            "percent": max(1, min(99, round(100 * (time.time() - v["started"]) / span)))}


@router.get("/v1/aurora/health", dependencies=[Depends(auth)])
def health_all() -> dict:
    from aurora import sys_health
    if time.time() - _health_cache["at"] > 10:
        _health_cache.update(at=time.time(), value=sys_health.check(cfg))
    return _health_cache["value"]


@router.get("/v1/aurora/answers/stats", dependencies=[Depends(auth)])
def answers_stats(days: float = 7) -> dict:
    """Questions on knowledge answered and declined in the last days, from the user's own conversation (owner,
    2026-10-05: accuracy and honesty are what people ask first; an abstention is Aurora saying she does not know)."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=max(1.0, min(days, 90)))).isoformat()
    turns = [t for t in pipeline().reader.recent(2000) if t.extra.get("role") == "assistant"
             and t.extra.get("mode", "knowledge") == "knowledge" and t.created_at >= since]
    declined = sum(1 for t in turns if t.extra.get("abstained"))
    return {"days": days, "questions": len(turns), "answered": len(turns) - declined, "declined": declined,
            "declined_pct": round(100 * declined / len(turns), 1) if turns else None}


@router.get("/v1/aurora/memory/about-me", dependencies=[Depends(auth)])
def about_me(n: int = 100) -> list[dict]:
    """What Aurora remembers of the user (owner, 2026-10-05, from what people ask of an AI: a memory they control):
    her long-term memories of their conversations, newest first, each with what it came from."""
    p = pipeline()
    if not p.reader.layout.shards("memory", "reflection"):
        return []
    items = [s for s in p.reader.recent(1000, domain="reflection") if s.extra.get("type") == "session_memory"]
    return [{"source_id": s.source_id, "text": s.text, "created_at": s.created_at,
             "turns": len(s.extra.get("turns") or [])} for s in reversed(items[-max(1, min(n, 500)):])]


@router.delete("/v1/aurora/memory/about-me", dependencies=[Depends(auth)])
def forget(source_id: str) -> dict:
    """Forget one memory of the user's for good (the memory and its index rows); only a session memory of theirs."""
    p = pipeline()
    mine = {s.source_id for s in p.reader.recent(1000, domain="reflection") if s.extra.get("type") == "session_memory"}
    if source_id not in mine:
        raise HTTPException(status_code=404, detail="no such memory")
    with _run_lock:
        sids = p.writer.remove_source("reflection", source_id)
        p.indexer.drop("reflection", sids)
    log.info("audit: a memory forgotten at the user's request (%d solitons)", len(sids))
    return {"forgotten": len(sids)}


@router.get("/v1/aurora/reflections", dependencies=[Depends(auth)])
def reflections(type: str | None = None, n: int = 30) -> list[dict]:
    p = pipeline()
    if not p.reader.layout.shards("memory", "reflection"):
        return []
    items = [s for s in p.reader.recent(500, domain="reflection") if type is None or s.extra.get("type") == type]
    return [{"sid": s.sid, "type": s.extra.get("type"), "text": s.text, "created_at": s.created_at,
             "extra": {k: v for k, v in s.extra.items() if k not in ("turns", "fragments")}}
            for s in reversed(items[-max(1, min(n, 200)):])]
