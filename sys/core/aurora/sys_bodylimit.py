# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A request's body has a ceiling, counted on the bytes that arrive (C535, security audit of 9 Nov: a body was read
whole before anyone had checked who sent it — by the replay cache, and by every route that takes its body as an
argument — so a stranger could fill the memory with one request).

The outermost layer of aurora-api:
 - a body up to ANON passes for anyone (a login, a small form);
 - a bigger one, or one of no declared length, asks `cap(path, headers)` first — the caller's credential checked on
   the headers alone, before a byte is read: 0 for a stranger (413 at once), the ceiling for a known caller, None
   for a stream that has no end (the camera's frames, checked piece by piece by its own route);
 - the bytes are counted as they come, whatever Content-Length said: past the ceiling the request ends with 413 and
   the route sees a caller that went away.
Caddy holds the same ceiling in front (net_https: request_body max_size)."""
from __future__ import annotations

import json

ANON = 2**20                      # anyone: 1 MiB
CAP = 256 * 2**20                 # a known caller: the largest upload is a 100 MB track in base64 (about 134 MiB)


class BodyLimit:
    def __init__(self, app, cap=None, anon: int = ANON):
        self.app, self.cap, self.anon = app, cap or (lambda path, headers: 0), anon

    @staticmethod
    async def _refuse(send, limit: int) -> None:
        body = json.dumps({"detail": f"the request is larger than {limit} bytes"}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        try:
            declared = int(headers.get(b"content-length", b"0") or 0)
        except ValueError:
            declared = -1
        limit = self.anon
        if declared < 0 or declared > limit or b"transfer-encoding" in headers:
            limit = self.cap(scope.get("path", ""), headers)
            if limit is None:                           # an endless stream of a known sender: its route counts
                return await self.app(scope, receive, send)
            limit = max(int(limit), self.anon)
            if declared > limit:
                return await self._refuse(send, limit)
        state = {"seen": 0, "over": False, "started": False}

        async def counted():
            if state["over"]:
                return {"type": "http.disconnect"}
            m = await receive()
            if m["type"] == "http.request":
                state["seen"] += len(m.get("body", b""))
                if state["seen"] > limit:
                    state["over"] = True
                    return {"type": "http.disconnect"}  # the route stops reading: nothing more is kept
            return m

        async def guarded(msg):
            if state["over"]:                           # what the route says after: not sent, the 413 is
                return
            if msg["type"] == "http.response.start":
                state["started"] = True
            await send(msg)

        try:
            await self.app(scope, counted, guarded)
        except Exception:                               # noqa: BLE001 - the route's «the caller went away»: ours to answer
            if not state["over"]:
                raise
        if state["over"] and not state["started"]:
            await self._refuse(send, limit)
