# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A search done while the person is still speaking (ROADMAP 99; owner, 19 Oct: «servirebbe farla ragionare proprio
mentre le parlo»). The words so far arrive every 1.5 s (the partial transcripts); the same search the answer will ask
is run on them in the background — the latest words only, never a queue — and again on the final transcript before it
comes back as the question; the answer takes the result when its question is the same text, spaces aside. Not the
same words with another case or punctuation: the re-ranker reads the text, and a lower-case variant without its
question mark changed up to half of the twelve memories (M237) — so the answer always gets the recall it would have
made itself. The re-ranker's ~2.1 s over the owner's memory is spent before the answer asks. Other text, or the same
after KEEP_S: searched as always."""
from __future__ import annotations

import re
import threading
import time

KEEP_S = 60.0          # a result waits this long for its question
KEEP_N = 8
WAIT_S = 5.0           # the asker waits at most this for the same search still running


def key(question: str, kw: dict) -> tuple:
    words = re.sub(r"\s+", " ", question).strip()
    return (words, kw.get("translation"), kw.get("candidates"), kw.get("top_k"),
            tuple(sorted(kw.get("sections") or ())), tuple(kw.get("recall") or ()))


class Ahead:
    def __init__(self, search):
        self._search = search                     # search(question, **kw) -> hits
        self._cv = threading.Condition()
        self._next: tuple | None = None           # (key, question, kw): the latest words, not started
        self._running: tuple | None = None
        self._done: dict[tuple, tuple[list, float]] = {}
        self._worker: threading.Thread | None = None

    def _drop_old(self) -> None:
        now = time.monotonic()
        for k in [k for k, (_, at) in self._done.items() if now - at > KEEP_S]:
            del self._done[k]
        while len(self._done) > KEEP_N:
            del self._done[min(self._done, key=lambda k: self._done[k][1])]

    def submit(self, question: str, **kw) -> None:
        """Search these words in the background (returns at once)."""
        if not question.strip():
            return
        k = key(question, kw)
        with self._cv:
            self._drop_old()
            if k in self._done or k == self._running:
                return
            self._next = (k, question, kw)        # newer words replace older ones still waiting
            if self._worker is None:
                self._worker = threading.Thread(target=self._work, daemon=True, name="search-ahead")
                self._worker.start()

    def _work(self) -> None:
        while True:
            with self._cv:
                if self._next is None:
                    self._worker = None
                    return
                k, question, kw = self._next
                self._next, self._running = None, k
            try:
                hits = self._search(question, **kw)
            except Exception:                     # a failed search ahead is only a search not saved
                hits = None
            with self._cv:
                self._running = None
                if hits is not None:
                    self._done[k] = (hits, time.monotonic())
                self._cv.notify_all()

    def take(self, question: str, kw: dict) -> list | None:
        """The result for these words if it was searched ahead (or is being searched: waited for), once; else None."""
        k = key(question, kw)
        with self._cv:
            self._drop_old()
            if self._next is not None and self._next[0] == k:
                self._next = None                 # not started: the asker searches it itself, now
                return None
            end = time.monotonic() + WAIT_S
            while self._running == k and time.monotonic() < end:
                self._cv.wait(end - time.monotonic())
            got = self._done.pop(k, None)
        return got[0] if got else None
