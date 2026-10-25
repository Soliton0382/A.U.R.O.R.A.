# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📞 The call (sys_call, ROADMAP N45): ring the owner's phone, decline, and the call's voice both ways over a WebSocket
on the HTTPS port. In the call: the phone sends 16 kHz PCM; each sentence, cut at its pause, is heard by Whisper and
answered by the chat's own path (remembered, origin "call"); the answer is said sentence by sentence as soon as each is
ready. The owner speaking over her stops her (the phone is told to drop what it has not played yet)."""
from __future__ import annotations

import asyncio
import json
import time

from aurora import sys_call, sys_context
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from .core import _admin, _is_key, auth, cfg, devices, log, start_run

router = APIRouter()
BARGE_FRAMES = 15                                     # 0.3 s of the owner's voice over hers stops her


@router.post("/v1/aurora/call", dependencies=[Depends(auth)])
async def call_ring(request: Request) -> dict:
    """{"reason"} -> the call, ringing on this user's phones (the app's line)."""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    call = await asyncio.to_thread(sys_call.ring, str(body.get("reason") or ""), cfg.now(), request.state.user)
    log.info("audit: call rung %s", call["id"])
    return call


@router.post("/v1/aurora/call/{call_id}/decline", dependencies=[Depends(auth)])
async def call_decline(call_id: str, request: Request) -> dict:
    c = sys_call.calls.get(call_id)
    if not c or c["user"] != request.state.user:
        raise HTTPException(status_code=404, detail="no such call")
    return {"declined": await asyncio.to_thread(sys_call.decline, call_id, cfg.now())}


def _who(ws: WebSocket) -> str | None | bool:
    """The user of the phone's device cookie (or of the API key); False when neither is valid."""
    from aurora.sys_devices import COOKIE
    bearer = ws.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if _is_key(bearer):
        return _admin()
    dev = devices.check(bearer) or devices.check(ws.cookies.get(COOKIE, ""))
    return False if dev is None else (dev.get("user") or _admin())


class _Voice:
    """Her voice in this call: what was sent and until when the phone plays it; a new answer or the owner cuts it."""

    def __init__(self, ws: WebSocket, lang: str) -> None:
        self.ws, self.lang, self.until, self.turn = ws, lang, 0.0, 0

    def speaking(self) -> bool:
        return time.monotonic() < self.until

    async def stop(self) -> None:
        self.turn += 1                                # the sentences of the turn cut are not sent
        if self.speaking():
            self.until = 0.0
            await self.ws.send_text(json.dumps({"type": "flush"}))

    async def say(self, text: str) -> None:
        from aurora import mdl_tts
        turn = self.turn
        for s in sys_call.sentences(text):
            try:
                wav = await asyncio.to_thread(mdl_tts.speak, cfg.now(), s, self.lang)
            except (RuntimeError, ValueError) as e:
                log.warning("call: no voice: %s", e)
                return
            if turn != self.turn:
                return
            pcm = sys_call.pcm16k(wav)
            self.until = max(self.until, time.monotonic()) + len(pcm) / 2 / sys_call.RATE
            await self.ws.send_bytes(pcm)


@router.websocket("/v1/aurora/call/{call_id}/audio")
async def call_audio(ws: WebSocket, call_id: str) -> None:
    user = _who(ws)
    c = sys_call.calls.get(call_id)
    if user is False or not c or c["user"] != user or c["state"] not in ("ringing", "answered"):
        await ws.close(code=4404)
        return
    sys_context.CURRENT.set(user)                     # her answers are this user's (memory, conversation)
    await ws.accept()
    if sys_call.set_state(call_id, "answered", only_from="ringing"):
        from aurora import sys_line                   # the other phones stop ringing
        await asyncio.to_thread(sys_line.post, {"kind": "call_answered", "call": call_id}, cfg.now())
    log.info("audit: call answered %s", call_id)
    lang = str(cfg["AURORA_LANG_DEFAULT"])[:2]
    voice, seg, heard = _Voice(ws, lang), sys_call.Segmenter(), asyncio.Queue()

    async def turns() -> None:                        # one sentence of the owner at a time, in order
        while True:
            audio = await heard.get()
            await _turn(ws, voice, audio, lang)

    worker = asyncio.create_task(turns())
    try:
        await voice.say(f"Ciao, sono Aurora. {c['reason']}")
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text") and json.loads(msg["text"]).get("type") == "hangup":
                break
            if msg.get("bytes"):
                for audio in seg.feed(msg["bytes"]):
                    await heard.put(audio)
                if seg.active and len(seg.frames) >= BARGE_FRAMES and voice.speaking():
                    await voice.stop()                # the owner talks over her: she stops
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        worker.cancel()
        sys_call.set_state(call_id, "ended")
        log.info("audit: call ended %s", call_id)


async def _turn(ws: WebSocket, voice: _Voice, audio, lang: str) -> None:
    """One sentence of the owner: heard, answered as in the chat, said."""
    from aurora import sns_av

    from .core import answer_or_acquire
    try:
        out = await asyncio.to_thread(sns_av.transcribe, audio, lang, cfg.now())
    except RuntimeError as e:
        log.warning("call: not heard: %s", e)
        return
    text = str(out.get("text") or "").strip() if out.get("clear") else ""
    if not text:
        return
    await voice.stop()
    await ws.send_text(json.dumps({"type": "heard", "text": text}))
    run = start_run(text, origin="call",
                    job=lambda q, emit, run_id: answer_or_acquire(q, emit, run_id, remember=True))
    t0, told = time.monotonic(), False
    while not run["done"]:
        await asyncio.sleep(0.2)
        if not told and time.monotonic() - t0 > 4 and not voice.speaking():
            told = True
            await voice.say("Un attimo.")             # a long answer: she says she is on it
    answer = run.get("answer")
    said = str(getattr(answer, "text", answer) or "").strip() or "Scusa, non sono riuscita a rispondere."
    await ws.send_text(json.dumps({"type": "said", "text": said}))
    await voice.say(said)
