# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A request the page repeats after a lost connection is answered once (owner, 2026-10-08: «uscendo e rientrando
dalla PWA ora ho questo errore: network error… facciamo un check in modo che non succeda da nessuna parte dove c'è
interazione utente e Aurora»).

The WebUI gives every request that changes something a key of its own (header X-Aurora-Request) and, when the
connection drops — the app sent to the background, the Wi-Fi changing — sends it again with the same key once it is
back. Here:
 - the first request is read whole and its work runs as a task of its own: a client that goes away does not stop it,
   and its answer is kept for TTL seconds;
 - the same key again while the work runs waits for it; after, it gets the kept answer.
So an answer is never lost and a post, a firewall change or a video is never made twice. The key is bound to the
caller's credentials (cookie, Authorization): nobody else can read an answer kept for another. Requests without a key
(third-party clients, GET, uploads larger than MAX_BODY) pass through untouched.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time

TTL = 600
MAX_BODY = 8 * 2**20
KEY = re.compile(rb"[A-Za-z0-9-]{8,64}")


class Replay:
    def __init__(self, app):
        self.app = app
        self.done: dict[tuple, tuple[float, dict, bytes]] = {}
        self.running: dict[tuple, asyncio.Task] = {}

    def _expire(self) -> None:
        now = time.time()
        for k in [k for k, (at, _, _) in self.done.items() if now - at > TTL]:
            del self.done[k]

    @staticmethod
    async def _answer(send, start: dict, body: bytes) -> None:
        try:
            await send(start)
            await send({"type": "http.response.body", "body": body, "more_body": False})
        except (OSError, RuntimeError):              # the caller went away again: the answer stays kept
            pass

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        key = headers.get(b"x-aurora-request", b"")
        size = int(headers.get(b"content-length", b"0") or 0)
        if not KEY.fullmatch(key) or size > MAX_BODY:
            return await self.app(scope, receive, send)
        who = hashlib.sha256(headers.get(b"cookie", b"") + b"\x00" + headers.get(b"authorization", b"")).hexdigest()[:24]
        k = (who, key, scope["method"], scope["path"])
        self._expire()
        if k in self.running:                           # the page asked again while the work runs: wait for it
            try:
                await asyncio.shield(self.running[k])
            except Exception:                           # noqa: BLE001 - the first one failed: this one says so too
                pass
        if k in self.done:
            _, start, body = self.done[k]
            return await self._answer(send, {**start, "headers": start["headers"] + [(b"x-aurora-replayed", b"1")]}, body)

        chunks, more = [], True
        while more:                                     # the whole request first: the work never waits on the caller
            m = await receive()
            if m["type"] == "http.disconnect":
                return
            chunks.append(m.get("body", b""))
            more = m.get("more_body", False)
        body_in = b"".join(chunks)
        given = False

        async def inner_receive():
            nonlocal given
            if not given:
                given = True
                return {"type": "http.request", "body": body_in, "more_body": False}
            await asyncio.Event().wait()                # a caller leaving is never told to the work
            return {"type": "http.disconnect"}

        out: dict = {"start": None, "body": []}

        async def inner_send(msg):
            if msg["type"] == "http.response.start":
                out["start"] = msg
            elif msg["type"] == "http.response.body":
                out["body"].append(msg.get("body", b""))

        task = asyncio.ensure_future(self.app(scope, inner_receive, inner_send))
        self.running[k] = task

        def finished(t: asyncio.Task) -> None:
            self.running.pop(k, None)
            if not t.cancelled() and t.exception() is None and out["start"] is not None:
                self.done[k] = (time.time(), out["start"], b"".join(out["body"]))

        task.add_done_callback(finished)
        await asyncio.shield(task)                      # raises what the work raised: the usual 500
        await asyncio.sleep(0)                          # the done callback has run
        if k in self.done:
            _, start, body = self.done[k]
            await self._answer(send, start, body)
