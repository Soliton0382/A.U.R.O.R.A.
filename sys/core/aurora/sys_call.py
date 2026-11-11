# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📞 Aurora calls the owner (ROADMAP N45, aurora-app F3; owner, 25 Oct: «proprio la telefonata telefonata… come una
schermata call classica»). The call rings on the phone through the app's line (sys_line: a "call" event, the app shows
a full-screen ringing call); answered, its voice goes both ways over a WebSocket on the HTTPS port (api/call), with no
third party: 16 kHz mono 16-bit PCM from the phone, cut into sentences at the pauses here (Segmenter), heard by
Whisper, answered by the same path as the chat, said by Aurora's voice and sent back in the same format. Not
answered within RING_S, or declined: a notification with the reason, so nothing is lost."""
from __future__ import annotations

import asyncio
import io
import json
import re
import secrets
import threading
import time
import wave

import numpy as np

from . import sys_config

RATE = 16000                                          # both ways: 16 kHz mono, 16-bit little endian
FRAME = RATE // 50                                    # 20 ms
RING_S = 30                                           # how long it rings before it is a missed call
KEEP_S = 3600                                         # a finished call is forgotten after this

_lock = threading.Lock()
calls: dict[str, dict] = {}


def ring(reason: str, cfg: sys_config.Config, user: str | None) -> dict:
    """A new call to `user`'s phones: on the line at once; missed after RING_S if nobody answers."""
    from . import sys_line
    reason = " ".join(str(reason or "").split())[:300] or "Prova di chiamata"
    call = {"id": secrets.token_hex(8), "user": user, "reason": reason, "state": "ringing", "at": time.time()}
    with _lock:
        for k in [k for k, c in calls.items() if time.time() - c["at"] > KEEP_S]:
            del calls[k]
        calls[call["id"]] = call
    sys_line.post({"kind": "call", "call": call["id"], "title": "📞 Aurora", "body": reason, "ring": RING_S,
                   "tag": f"aurora-call-{call['id']}", "view": "chat"}, cfg)
    threading.Timer(RING_S + 5, _missed, (call["id"], cfg)).start()
    return dict(call)


def dial(user: str | None, assistant: bool = False) -> dict:
    """The owner calls Aurora (owner, 26 Oct: «un tasto cornetta da qualche parte per chiamare aurora»): the app opens
    the call screen at once, nothing rings anywhere; a call never opened is forgotten with the others (KEEP_S).
    `assistant`: the phone's assistant (N68), which listens at once with no greeting: its screen shows it is there."""
    call = {"id": secrets.token_hex(8), "user": user, "reason": "", "state": "dialing", "by": "owner", "at": time.time(),
            "assistant": bool(assistant)}
    with _lock:
        for k in [k for k, c in calls.items() if time.time() - c["at"] > KEEP_S]:
            del calls[k]
        calls[call["id"]] = call
    return dict(call)


def _missed(call_id: str, cfg: sys_config.Config) -> None:
    if set_state(call_id, "missed", only_from="ringing"):
        _tell(calls[call_id], "📞 Chiamata persa", cfg)


def _tell(call: dict, title: str, cfg: sys_config.Config) -> None:
    """What the call was about, as a notification: the line ends the ringing and keeps the reason."""
    from . import sys_line
    sys_line.post({"kind": "call_end", "call": call["id"], "title": title, "body": call["reason"], "view": "chat",
                   "tag": f"aurora-call-{call['id']}"}, cfg)


def set_state(call_id: str, state: str, only_from: str | None = None) -> bool:
    with _lock:
        c = calls.get(call_id)
        if not c or (only_from and c["state"] != only_from):
            return False
        c["state"], c[f"{state}_at"] = state, time.time()
        return True


def decline(call_id: str, cfg: sys_config.Config) -> bool:
    if not set_state(call_id, "declined", only_from="ringing"):
        return False
    _tell(calls[call_id], "📞 Chiamata rifiutata", cfg)
    return True


# ---- the voice coming in: sentences cut at the pauses -------------------------------------------------------------
class Segmenter:
    """20 ms frames in, a whole sentence out when it ends. The floor is learnt from the quietest frames (the line's own
    noise, after the phone's echo canceller), as the WebUI's vad.js does: speech is a few frames well above it."""
    START, END_S, MAX_S, MIN_S, PAUSE_S = 3, 0.8, 20.0, 0.4, 0.3

    def __init__(self) -> None:
        self.buf, self.voiced, self.quiet, self.floor = bytearray(), 0, 0, None
        self.active, self.frames = False, []
        self.end_s = self.END_S                       # shorter once its answer is ready (sys_call_ahead)
        self.maybe = None                             # the voice so far, at the first quiet: it may be over (the guess)

    def rms(self, frame: bytes) -> float:
        x = np.frombuffer(frame, dtype="<i2").astype(np.float32)
        return float(np.sqrt(np.mean(x * x))) if x.size else 0.0

    def feed(self, pcm: bytes) -> list[np.ndarray]:
        """The sentences ended inside these bytes, as float32 in [-1, 1] at 16 kHz (Whisper's input)."""
        self.buf.extend(pcm)
        done = []
        while len(self.buf) >= 2 * FRAME:
            frame, self.buf = bytes(self.buf[:2 * FRAME]), self.buf[2 * FRAME:]
            level = self.rms(frame)
            self.floor = level if self.floor is None else min(level, self.floor * 1.002 + 0.5)   # it may rise slowly
            loud = level > max(3 * self.floor, 300)
            if not self.active:
                self.voiced = self.voiced + 1 if loud else 0
                self.frames = (self.frames + [frame])[-self.START:]
                if self.voiced >= self.START:
                    self.active, self.quiet = True, 0
                continue
            self.frames.append(frame)
            if loud:
                self.end_s = self.END_S               # the owner goes on: a sentence not over after all
            self.quiet = 0 if loud else self.quiet + 1
            seconds = len(self.frames) * FRAME / RATE
            spoken = seconds - self.quiet * FRAME / RATE
            if self.quiet == round(self.PAUSE_S * RATE / FRAME) and spoken >= self.MIN_S:
                self.maybe = np.frombuffer(b"".join(self.frames), dtype="<i2").astype(np.float32) / 32768
            if self.quiet * FRAME / RATE >= self.end_s or seconds >= self.MAX_S:
                if spoken >= self.MIN_S:
                    done.append(np.frombuffer(b"".join(self.frames), dtype="<i2").astype(np.float32) / 32768)
                self.active, self.voiced, self.frames, self.end_s = False, 0, [], self.END_S
        return done


# ---- the voice going out --------------------------------------------------------------------------------------------
def sentences(text: str) -> list[str]:
    """The answer in sentences, each said as soon as it is ready; markdown and links are not read aloud."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", str(text or ""))              # [label](url) -> label
    text = re.sub(r"https?://\S+|[*_`#>|]+", " ", text)
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return [p for p in (" ".join(x.split()) for x in parts) if re.search(r"\w", p)]


END = re.compile(r"[.!?…]+[\"»)]*\s")
LONG = 140                                            # a long sentence still written: said up to its last comma


def ready(buf: str) -> tuple[str, str]:
    """(what can be said now, what waits) of an answer still being written: its complete sentences."""
    cut = max((m.end() for m in END.finditer(buf)), default=0)
    if not cut and len(buf) > LONG and "," in buf[:-1]:
        cut = buf.rindex(",", 0, len(buf) - 1) + 1
    return buf[:cut], buf[cut:]


def pcm16k(wav_bytes: bytes) -> bytes:
    """A WAV (any rate, mono or stereo) as 16 kHz mono 16-bit PCM, the call's format."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, ch, width, raw = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{8 * width}-bit audio: 16-bit expected")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if rate != RATE and x.size:
        n = int(round(x.size * RATE / rate))
        x = np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x)
    return np.clip(x, -32768, 32767).astype("<i2").tobytes()


PHONE_SAID = {"ok": "Fatto.", "no_app": "Sul telefono non c'è un'app per farlo.", "no_contact": "Non trovo quel contatto.",
              "need_contacts": "Consenti l'accesso ai contatti e chiedimelo di nuovo."}
PHONE_SAID_EN = {"ok": "Done.", "no_app": "There is no app on the phone to do it.", "no_contact": "I cannot find that contact.",
                 "need_contacts": "Allow the access to the contacts and ask me again."}


async def phone_now(ws, voice, text: str, lang: str, turn: int, log, model=None, guess=None) -> bool:
    """A command for the phone sent to the app at once: a plain one read by the patterns (agt_phone.quick), any other
    by the local reasoner in one short answer (agt_phone.understand); `guess`: already read while the owner paused
    (sys_call_ahead); said done, or why not. False when it is not one, or the app did not answer (a version without
    phone actions): then Aurora answers as before."""
    from . import agt_phone
    act = guess.act if guess is not None and guess.done else agt_phone.quick(text)
    if not act and model is not None and not (guess is not None and guess.done):
        act = await asyncio.to_thread(agt_phone.understand, model, text)
    if not act:
        return False
    fut = asyncio.get_running_loop().create_future()
    voice.phone[act["id"]] = fut
    await ws.send_text(json.dumps({"type": "phone", "action": act}))
    try:
        result = await asyncio.wait_for(fut, 3)
    except asyncio.TimeoutError:
        voice.phone.pop(act["id"], None)
        return False
    said = (PHONE_SAID if lang == "it" else PHONE_SAID_EN).get(result) or ("Non ci sono riuscita." if lang == "it" else "I could not do it.")
    log.info("call: phone %s → %s", act["action"], result)
    await ws.send_text(json.dumps({"type": "said", "text": f"{agt_phone.said(act)} — {said}"}))
    await voice.say(said if lang == "it" else ("Done." if result == "ok" else said), turn)
    return True


# 🗣️ What is said aloud of a long answer (owner, 2 Nov: «evitare che l'assistente mi dica il resoconto delle attività
# svolte se no il feedback vocale diventa lungo e inutile»): the agent's answer is written for the chat — its steps, its
# timings, its sources. Said in a call, only what the person needs, rewritten by the local reasoner: 0.29–0.54 s on the
# reference machine (M273). The whole text stays written in the conversation.
SHORT = 220                                           # a short answer is said as it is
SPOKEN = """You turn an assistant's written answer into what she says aloud on the phone, in the answer's language.
One or two short spoken sentences: the result or the answer the person needs, nothing else.
Leave out: statistics, timings, sources, tool names, the steps that were done, lists, markdown, emoji, links, offers \
of more help.
Keep any number, time or name the person actually asked for."""


def spoken(model, text: str) -> str:
    """The answer as said in a call: as it is when short and plain, else its spoken gist; the reasoner off: its first
    two sentences."""
    parts = sentences(text)
    plain = len(parts) <= 2 and not re.search(r"^\s*([-*•]|\d+[.)])\s|\*\*|#", str(text), re.M)
    if plain and len(" ".join(parts)) <= SHORT:
        return " ".join(parts)
    if model is not None:
        try:
            out = model.complete(SPOKEN, str(text)[:4000], 90).answer.strip()
            if out:
                return " ".join(sentences(out))
        except Exception:                             # noqa: BLE001 - the reasoner off or failing: the first sentences
            pass
    return " ".join(parts[:2])
