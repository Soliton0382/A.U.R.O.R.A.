# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔮 A call's answer prepared while the owner may have finished (owner, 3 Nov: «procedere con la previsione della frase
così velocizziamo ancora di più»; ROADMAP 99). A sentence ends after Segmenter.END_S of quiet, and only then was it
heard. Here the first PAUSE_S of quiet is taken as «it may be over»: what was said so far is transcribed and prepared
at once — the command for the phone read, plain talk answered and its first sentence spoken into the clips' cache
(kno_talk.prepare, mdl_tts), a question for the whole path searched in her memory. If the sentence does end there, the
turn starts with all of it done, and the wait is shortened (READY_END_S, a few words at least). If the owner goes on,
the work is dropped: a newer pause starts over, the stream in progress is closed.

Nothing happens on the phone and nothing is remembered from a guess: the action is sent and the turn is written only
when the sentence has really ended (api/call._turn)."""
from __future__ import annotations

import asyncio
import logging

from . import agt_phone, kno_talk, sns_av, sys_call

log = logging.getLogger("aurora.api")
READY_END_S = 0.6                                     # the sentence's end, once its answer is ready (from END_S)
MIN_WORDS = 3                                         # fewer words are too often a sentence still starting
SHORT_WAIT_S = 2.0                                    # how long the turn waits for a guess of the same words


class Prepared:
    def __init__(self, samples: int) -> None:
        self.samples, self.text, self.act, self.done = samples, "", None, False


class Ahead:
    AFTER = round((sys_call.Segmenter.END_S + 0.1) * sys_call.RATE)   # the quiet a sentence can gain after its guess

    def __init__(self, pipeline, cfg, lang: str, seg: "sys_call.Segmenter", speak) -> None:
        self.p, self.cfg, self.lang, self.seg, self.speak = pipeline, cfg, lang, seg, speak
        self.gen, self.now, self.task = 0, None, None

    def pause(self, audio) -> None:
        """The first quiet of a sentence: a guess begun on what was said so far; any guess before it is dropped."""
        self.gen += 1
        self.now = Prepared(len(audio))
        self.task = asyncio.create_task(self._work(self.gen, self.now, audio))

    def stale(self, gen: int) -> bool:
        return gen != self.gen

    async def _work(self, gen: int, out: Prepared, audio) -> None:
        try:
            heard = await asyncio.to_thread(sns_av.transcribe, audio, self.lang, self.cfg)
            out.text = str(heard.get("text") or "").strip() if heard.get("clear") else ""
            if not out.text or self.stale(gen):
                return
            out.act = agt_phone.quick(out.text) or await asyncio.to_thread(agt_phone.understand, self.p.llm, out.text)
            if not out.act and not self.stale(gen):
                recent = await asyncio.to_thread(self.p.reader.recent, kno_talk.RECENT)
                text, handed = await asyncio.to_thread(kno_talk.prepare, self.p, self.cfg, out.text, recent,
                                                       lambda: self.stale(gen))
                if handed and not self.stale(gen):    # the whole path's search, ready before it asks (sol_ahead)
                    self.p.ahead(out.text)
                first = sys_call.sentences(text)[:1]
                if first and not self.stale(gen):     # her first sentence in the clips' cache: said at once
                    await asyncio.to_thread(self.speak, self.cfg, first[0], self.lang)
            out.done = True
            if not self.stale(gen) and len(out.text.split()) >= MIN_WORDS:
                self.seg.end_s = READY_END_S
        except asyncio.CancelledError:
            raise
        except Exception as e:                        # noqa: BLE001 - a guess that fails costs nothing: the turn does it
            log.warning("call: the guess failed: %s", e)

    async def take(self, audio) -> Prepared | None:
        """The sentence has ended: its guess, when it heard the same voice (only quiet added since), waited for shortly."""
        now, task = self.now, self.task
        self.now = self.task = None
        if now is None or not now.samples <= len(audio) <= now.samples + self.AFTER:
            self.gen += 1                             # the owner went on after it: dropped
            return None
        try:
            await asyncio.wait_for(asyncio.shield(task), SHORT_WAIT_S)
        except (asyncio.TimeoutError, OSError, RuntimeError):      # not ready: the turn asks by itself
            pass
        return now if now.text else None
