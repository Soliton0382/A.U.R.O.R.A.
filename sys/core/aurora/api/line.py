# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📶 The line (sys_line, aurora-app F2): Aurora's Android app keeps this request open and gets the notifications
without a push service in between. A request waits up to `wait` seconds for an event after `after`; no thread is held
while it waits (it looks at a counter twice a second)."""
from __future__ import annotations

import asyncio
import time

from aurora import sys_line
from fastapi import APIRouter, Depends, Request

from .core import auth, cfg, log

router = APIRouter()


@router.get("/v1/aurora/line", dependencies=[Depends(auth)])
async def line(request: Request, after: str = "", wait: float = 0) -> dict:
    """{"events": [...], "next": the id to send back}. `after` empty: no old news, only the id to start from."""
    if not after:
        dev = getattr(request.state, "device", None) or {}
        log.info("audit: line opened by %s", dev.get("name") or "the API key")
        return {"events": [], "next": await asyncio.to_thread(sys_line.last, cfg)}
    end = time.monotonic() + max(0.0, min(float(wait), sys_line.WAIT_MAX))
    while True:
        seen = sys_line.version
        events = await asyncio.to_thread(sys_line.since, after, cfg)
        if events or time.monotonic() >= end or await request.is_disconnected():
            return {"events": events, "next": events[-1]["id"] if events else after}
        while sys_line.version == seen and time.monotonic() < end:
            await asyncio.sleep(0.5)
