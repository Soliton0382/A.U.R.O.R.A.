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

from .core import _admin, _from_this_machine, _is_key, auth, cfg, devices, is_maintenance_key, log, start_run

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
    """The owner calls Aurora from the app: a call ready to be opened, ringing nowhere; ?as=assistant: the phone's
    assistant, with no greeting."""
    call = sys_call.dial(request.state.user, request.query_params.get("as") == "assistant")
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
    if _is_key(bearer) or (is_maintenance_key(bearer) and _from_this_machine(ws)):
        return _admin()
    dev = devices.check(bearer) or devices.check(ws.cookies.get(COOKIE, ""))
    return False if dev is None else (dev.get("user") or _admin())


class _Voice:
    """Her voice in this call: what was sent and until when the phone plays it; a new answer or the owner cuts it."""

    def __init__(self, ws: WebSocket, lang: str) -> None:
        self.ws, self.lang, self.until, self.turn = ws, lang, 0.0, 0
        self.phone: dict[str, asyncio.Future] = {}   # 📱 an action sent to the app → its answer (N68)
        self.t0, self.guessed = 0.0, False           # 🔮 when the last sentence ended, whether it was guessed
        from aurora import sys_call_steps
        self.free, self.owed, self.long = asyncio.Event(), sys_call_steps.Owed(lang), 0    # 🗣️ never behind a long answer
        self.at_work: dict[int, dict] = {}            # the whole path's runs still going, by their turn
        self.dropped: set[int] = set()                # 🛑 the owner said to leave those
        self.nods, self.lost_at = sys_call_steps.Nods(lang), 0.0   # 👂 while the owner talks; 🤔 the last «non ho capito»

    def speaking(self) -> bool:
        return time.monotonic() < self.until

    async def stop(self) -> None:
        self.turn += 1                                # the sentences of the turn cut are not sent
        if self.speaking():
            log.info("call: cut with %.1f s of her voice left", self.until - time.monotonic())
            self.until = 0.0
            await self.ws.send_text(json.dumps({"type": "flush"}))

    async def nod(self, word: str, within_s: float = 0.5) -> None:
        """A short sign that she is there: never counted as her speaking, so it cuts nothing and is cut by nothing; only
        when its clip is ready at once (they are made when the call opens), else the moment has passed."""
        from aurora import mdl_tts
        try:
            wav = await asyncio.wait_for(asyncio.to_thread(mdl_tts.speak, cfg.now(), word, self.lang), within_s)
            await self.ws.send_bytes(sys_call.pcm16k(wav))
            log.info("call: sign %s", word)
        except (asyncio.TimeoutError, RuntimeError, ValueError) as e:
            log.debug("call: no nod: %s", e)

    async def say(self, text: str, turn: int | None = None) -> None:
        """Said sentence by sentence; `turn`: the owner's sentence it answers (cut by a newer one, nothing is said)."""
        from aurora import mdl_tts
        turn = self.turn if turn is None else turn
        from aurora import sys_call_steps
        for s in sys_call.sentences(sys_call_steps.sayable(text, self.lang)):
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
            if self.t0:                               # no words: the wait after a sentence's end, for M275
                log.info("call: first voice %.2f s after the sentence ended (%s)", time.monotonic() - self.t0,
                         "guessed" if self.guessed else "not guessed")
                self.t0 = 0.0


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

    from aurora import kno_talk, mdl_tts, sys_call_ahead
    from .core import pipeline
    ahead = sys_call_ahead.Ahead(pipeline(), cfg.now(), lang, seg, mdl_tts.speak)   # 🔮 prepared while the owner pauses

    from aurora import sys_call_steps
    nods_on = bool(cfg["AURORA_CALL_NODS"])

    async def clips() -> None:                        # 👂 ready before the first sentence
        for w in voice.nods.words():
            try:
                await asyncio.to_thread(mdl_tts.speak, cfg.now(), w, lang)
            except (RuntimeError, ValueError):
                return
    if nods_on:
        asyncio.create_task(clips())
    asyncio.create_task(asyncio.to_thread(kno_talk.warm, pipeline(), cfg.now(), lang))   # 🔥 no cold first answers (M285)

    async def failed(e: Exception) -> None:           # 🛟 a turn that breaks is told, never silence (C499)
        log.error("call: turn failed: %r", e, exc_info=e)
        await voice.say("Scusa, ho avuto un problema. Riprova." if lang == "it" else "Sorry, something went wrong. Try again.")

    worker = asyncio.create_task(sys_call_steps.in_turn(heard, lambda audio: _turn(ws, voice, audio, lang, ahead), voice.free, failed))
    try:
        if not c.get("assistant"):
            await voice.say("Ciao, dimmi pure." if c.get("by") == "owner" else f"Ciao, sono Aurora. {c['reason']}")
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            j = json.loads(msg["text"]) if msg.get("text") else {}
            if j.get("type") == "hangup":
                break
            if j.get("type") == "phone_result":       # 📱 what the app did with an action (N68)
                f = voice.phone.pop(str(j.get("id", "")), None)
                if f and not f.done():
                    f.set_result(str(j.get("result", "")))
            if msg.get("bytes"):
                said = seg.feed(msg["bytes"])
                if seg.maybe is not None:
                    if not voice.speaking():          # her own voice heard back is no sentence of the owner's
                        ahead.pause(seg.maybe)
                        word = voice.nods.at_pause(len(seg.maybe) / sys_call.RATE) if nods_on else None
                        if word:
                            asyncio.create_task(voice.nod(word))
                    seg.maybe = None
                for audio in said:
                    voice.t0 = time.monotonic()       # the sentence ended: the wait she is measured by
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
        from aurora import sys_call_steps, txt_lang               # 🗣️ never mute for long
        return sys_call_steps.watched(emit, txt_lang.detect(question),
                                      lambda told: answer_or_acquire(question, told, run_id, remember=True))
    ans = Answer(run_id, question, text, False, mode="talk", seconds=round(time.time() - t0, 2))
    emit("answer.final", {"text": text, "abstained": False, "sources": [], "seconds": ans.seconds, "mode": "talk"})
    p.remember(question, ans, run_id, emit, None, asked_at)
    emit("run.end", {"seconds": ans.seconds})
    return ans


async def _turn(ws: WebSocket, voice: _Voice, audio, lang: str, ahead=None) -> None:
    """One sentence of the owner: heard (or guessed already, sys_call_ahead), answered (the quick path streamed, or the
    whole one), said."""
    from aurora import sns_av
    guess = await ahead.take(audio) if ahead else None
    voice.guessed = bool(guess)
    if guess:
        text = guess.text
    else:
        try:
            out = await asyncio.to_thread(sns_av.transcribe, audio, lang, cfg.now())
        except RuntimeError as e:
            log.warning("call: not heard: %s", e)
            return
        text = str(out.get("text") or "").strip() if out.get("clear") else ""
    if not text:
        # 🤔 a real sentence she could not make out, not a noise: asked back, not too often
        if len(audio) >= sys_call.RATE and time.monotonic() - voice.lost_at > 15 and not voice.speaking():
            voice.lost_at = time.monotonic()
            log.info("call: not understood, %.1f s of voice", len(audio) / sys_call.RATE)
            await voice.say("Scusa, non ho capito." if lang == "it" else "Sorry, I didn't catch that.")
        return
    await voice.stop()
    await ws.send_text(json.dumps({"type": "heard", "text": text}))
    turn = voice.turn
    from aurora import sys_call_steps
    if (voice.at_work or voice.owed.items) and sys_call_steps.cancels(text):     # 🛑 «lascia stare»
        for t, r in voice.at_work.items():
            r["cancel"] = True
            voice.dropped.add(t)
        voice.owed.take()
        await voice.say(sys_call_steps.CANCELLED[0 if lang == "it" else 1], turn)
        return
    now_means = sys_call_steps.corrected(text)        # ✏️ «no, volevo dire…»
    if now_means:
        text = now_means
        for t, r in voice.at_work.items():
            r["cancel"] = True
            voice.dropped.add(t)
        voice.owed.take()
    from .core import pipeline
    model = pipeline().llm                            # the local reasoner: the phone's commands, the spoken answer
    if await sys_call.phone_now(ws, voice, text, lang, turn, log, model, guess):   # ⚡ «apri YouTube»: the app at once (N68)
        return
    from .core import _run_lock
    from .core_route import mood_wrap                    # 😠 an insult said in a call: her anger, and local only
    if _run_lock.locked():                            # behind what she is still doing (M279: 23 s in silence)
        await voice.say("Un attimo, finisco quello di prima." if lang == "it" else "One moment, finishing what came before.", turn)
    run = start_run(text, origin="call", job=mood_wrap(text, _talk))
    seen, buf, spoken, handed, thought, t0 = 0, "", False, False, False, time.monotonic()
    while True:
        done = run["done"]                            # read before the events: none written after it is missed
        events = run["events"][seen:]
        seen += len(events)
        for e in events:
            if not e["event"].endswith(".delta"):     # 🧠 the step's name only, for the assistant's brain (N68)
                await ws.send_text(json.dumps({"type": "step", "name": e["event"]}))
            if e["event"] == "talk.delta":
                buf += str(e["payload"].get("text") or "")
            elif e["event"] == "phone.action":         # 📱 what the agent asked of the phone (agt_phone)
                await ws.send_text(json.dumps({"type": "phone", "action": e["payload"]}))
            elif e["event"] == "talk.step" and not voice.speaking():      # 🗣️ what she is doing (sys_call_steps)
                await voice.say(str(e["payload"].get("text") or ""), turn)
            elif e["event"] == "talk.handoff":
                handed = True
                voice.long += 1
                voice.at_work[turn] = run
                voice.free.set()                      # the next sentence need not wait for this answer
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
        # 🤔 no word yet: a sign she is thinking, not her first voice (what she is measured by stays her answer's)
        if cfg["AURORA_CALL_NODS"] and not (thought or spoken or handed or voice.speaking()) and time.monotonic() - t0 > 1.5:
            thought = True
            await voice.nod(voice.nods.thinking())
        await asyncio.sleep(0.05)
    if handed:
        voice.long -= 1
        voice.at_work.pop(turn, None)
    if turn in voice.dropped:                         # 🛑 left: not said, now or later
        voice.dropped.discard(turn)
        return
    if turn != voice.turn and not handed:             # the owner spoke again: plain talk is not said
        return
    answer = run.get("answer")
    said = str(getattr(answer, "text", answer) or "").strip() or "Scusa, non sono riuscita a rispondere."
    await ws.send_text(json.dumps({"type": "said", "text": said}))
    if handed or not spoken:                          # the whole path's answer, written for the chat: its gist said
        said = await asyncio.to_thread(sys_call.spoken, model, said)
    if turn != voice.turn:                            # spoken over: said once she has answered the newer one
        voice.owed.add(said)
    else:
        await voice.say(said if handed or not spoken else buf, turn)   # streamed: only its last words are left
    if not voice.long or turn == voice.turn:
        for line in voice.owed.take():
            await voice.say(line)
