# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📞 The call (sys_call, ROADMAP N45): ring the owner's phone, decline, and the call's voice both ways over a WebSocket
on the HTTPS port. In the call: the phone sends 16 kHz PCM; each sentence, cut at its pause, is heard by Whisper and
answered (remembered, origin "call") by the quick path first (kno_talk: plain talk streamed, each sentence said
while the next is written) or, when she hands it on, by the chat's whole path, after a «Guardo subito». The owner
speaking over her stops her (the phone is told to drop what it has not played yet)."""
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


@router.post("/v1/aurora/call/dial", dependencies=[Depends(auth)])
async def call_dial(request: Request) -> dict:
    """The owner calls Aurora from the app: a call ready to be opened, ringing nowhere."""
    call = sys_call.dial(request.state.user)
    log.info("audit: call dialled %s", call["id"])
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

    async def say(self, text: str, turn: int | None = None) -> None:
        """Said sentence by sentence; `turn`: the owner's sentence it answers (cut by a newer one, nothing is said)."""
        from aurora import mdl_tts
        turn = self.turn if turn is None else turn
        for s in sys_call.sentences(text):
            if turn != self.turn:
                return
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
    if user is False or not c or c["user"] != user or c["state"] not in ("ringing", "answered", "dialing"):
        await ws.close(code=4404)
        return
    sys_context.CURRENT.set(user)                     # her answers are this user's (memory, conversation)
    await ws.accept()
    if sys_call.set_state(call_id, "answered", only_from="ringing"):
        from aurora import sys_line                   # the other phones stop ringing
        await asyncio.to_thread(sys_line.post, {"kind": "call_answered", "call": call_id}, cfg.now())
    sys_call.set_state(call_id, "answered", only_from="dialing")      # the owner's own call: nobody else rang
    log.info("audit: call answered %s", call_id)
    lang = str(cfg["AURORA_LANG_DEFAULT"])[:2]
    voice, seg, heard = _Voice(ws, lang), sys_call.Segmenter(), asyncio.Queue()

    async def turns() -> None:                        # one sentence of the owner at a time, in order
        while True:
            audio = await heard.get()
            await _turn(ws, voice, audio, lang)

    worker = asyncio.create_task(turns())
    try:
        await voice.say("Ciao, dimmi pure." if c.get("by") == "owner" else f"Ciao, sono Aurora. {c['reason']}")
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


def _talk(question: str, emit, run_id: str):
    """A call's sentence: the quick path (kno_talk), or the whole one when she hands it on; remembered either way."""
    from aurora import kno_talk
    from aurora.kno_answer import Answer
    from aurora.sol_schema import now_iso

    from .core import answer_or_acquire, pipeline
    p, asked_at, t0 = pipeline(), now_iso(), time.time()
    try:
        text, handed = kno_talk.quick(p, cfg.now(), question, p.reader.recent(kno_talk.RECENT), emit)
    except Exception as e:                            # noqa: BLE001 - the local reasoner off or failing: the whole path
        log.warning("call: quick path failed: %s", e)
        text, handed = "", True
    if handed:
        emit("talk.handoff", {"seconds": round(time.time() - t0, 2), "said": text[:200]})
        return answer_or_acquire(question, emit, run_id, remember=True)
    ans = Answer(run_id, question, text, False, mode="talk", seconds=round(time.time() - t0, 2))
    emit("answer.final", {"text": text, "abstained": False, "sources": [], "seconds": ans.seconds, "mode": "talk"})
    p.remember(question, ans, run_id, emit, None, asked_at)
    emit("run.end", {"seconds": ans.seconds})
    return ans


async def _turn(ws: WebSocket, voice: _Voice, audio, lang: str) -> None:
    """One sentence of the owner: heard, answered (the quick path streamed, or the whole one), said."""
    from aurora import sns_av
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
    turn = voice.turn
    run = start_run(text, origin="call", job=_talk)
    seen, buf, spoken, handed, t0, told = 0, "", False, False, time.monotonic(), False
    while True:
        done = run["done"]                            # read before the events: none written after it is missed
        events = run["events"][seen:]
        seen += len(events)
        for e in events:
            if e["event"] == "talk.delta":
                buf += str(e["payload"].get("text") or "")
            elif e["event"] == "talk.handoff":
                handed = True
                if buf.strip():                       # the start she said before handing on
                    await voice.say(buf, turn)
                buf = ""
                await voice.say("Guardo subito." if lang == "it" else "Let me check.", turn)
        now, buf = sys_call.ready(buf)
        if now.strip():
            await voice.say(now, turn)
            spoken = True
        if done:
            break
        if handed and not told and time.monotonic() - t0 > 12 and not voice.speaking():
            told = True
            await voice.say("Ci sono quasi." if lang == "it" else "Almost there.", turn)
        await asyncio.sleep(0.05)
    if turn != voice.turn:                            # the owner spoke again: this answer is not said
        return
    answer = run.get("answer")
    said = str(getattr(answer, "text", answer) or "").strip() or "Scusa, non sono riuscita a rispondere."
    await ws.send_text(json.dumps({"type": "said", "text": said}))
    await voice.say(said if handed or not spoken else buf, turn)   # streamed: only its last words are left
