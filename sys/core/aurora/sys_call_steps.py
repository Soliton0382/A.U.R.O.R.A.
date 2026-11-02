# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🗣️ What she is doing, said aloud while the tools work (owner, 3 Nov: «per evitare che aurora rimanga muta per troppo
tempo quando apre gli strumenti, potrebbe dire cosa sta facendo… procedo, un attimo, accesso al calendario»). A real call
had 66 s of an agent's work in silence (M279), and the owner spoke over it.

Short lines read from a step's name only, never from its arguments or results: what is said can hold nothing private.
At most one line every MIN_GAP_S, never the same twice running; with nothing new for QUIET_S a line says she is still
at it. Both the call and the chat's hands-free conversation say them (event talk.step)."""
from __future__ import annotations

import threading
import time

MIN_GAP_S = 3.0
QUIET_S = 15.0
EVENTS = {"retrieval.hits": ("Cerco tra le mie fonti.", "Searching my sources."), "read.web": ("Leggo in rete.", "Reading the web."),
          "verify.keep": ("Verifico.", "Checking."), "approval.request": ("Mi serve la tua approvazione.", "I need your approval.")}
TOOLS = (                                             # the first that fits the tool's name
    (("calendar",), ("Apro il calendario.", "Opening the calendar.")),
    (("mail",), ("Guardo la posta.", "Checking the mail.")),
    (("weather", "meteo"), ("Guardo il meteo.", "Checking the weather.")),
    (("camera",), ("Guardo le telecamere.", "Checking the cameras.")),
    (("home", "light", "scene"), ("Controllo la casa.", "Checking the house.")),
    (("firewall", "security", "sentinel"), ("Controllo la sicurezza.", "Checking the security.")),
    (("facebook", "instagram", "mastodon", "telegram"), ("Apro i social.", "Opening the social networks.")),
    (("picture", "image"), ("Preparo l'immagine.", "Making the picture.")),
    (("project",), ("Lavoro sul progetto.", "Working on the project.")),
    (("routine",), ("Guardo le routine.", "Checking the routines.")),
    (("people",), ("Guardo tra le persone.", "Looking through the people.")),
    (("note",), ("Guardo le note.", "Checking the notes.")),
    (("news",), ("Leggo le notizie.", "Reading the news.")),
    (("web", "search", "browse", "fetch"), ("Cerco in rete.", "Searching the web.")),
    (("log", "runs"), ("Controllo i log.", "Checking the logs.")),
    (("file", "document"), ("Guardo i file.", "Checking the files.")),
)
ANY_TOOL = ("Uso uno strumento.", "Using a tool.")
STILL = (("Ci sto lavorando.", "Working on it."), ("Ancora un attimo.", "Just a moment more."))


def line(event: str, payload: dict | None) -> tuple[str, str] | None:
    """The (Italian, English) line of a step, or None: a step that says nothing."""
    if event in EVENTS:
        return EVENTS[event]
    if event != "tool.call":
        return None
    name = str((payload or {}).get("name") or "").lower()
    return next((said for words, said in TOOLS if any(w in name for w in words)), ANY_TOOL)


class Steps:
    """The lines of one turn, sent through `emit` as talk.step while the whole path works."""

    def __init__(self, emit, lang: str, clock=time.monotonic) -> None:
        self.emit, self.i, self.clock = emit, 0 if lang == "it" else 1, clock
        self.last, self.said, self.still = clock(), None, 0
        self.lock = threading.Lock()

    def _say(self, said: tuple[str, str]) -> None:
        self.last, self.said = self.clock(), said
        self.emit("talk.step", {"text": said[self.i]})

    def on(self, event: str, payload: dict | None) -> None:
        said = line(event, payload)
        with self.lock:
            if said and said != self.said and self.clock() - self.last >= MIN_GAP_S:
                self._say(said)

    def tick(self) -> None:
        with self.lock:
            if self.clock() - self.last >= QUIET_S:
                self._say(STILL[self.still % len(STILL)])
                self.still += 1

    def watch(self, stop: threading.Event, step_s: float = 1.0) -> None:
        while not stop.wait(step_s):
            self.tick()


def watched(emit, lang: str, job):
    """`job(told)` with its steps said: told is the emit it gives to the whole path."""
    steps, stop = Steps(emit, lang), threading.Event()
    threading.Thread(target=steps.watch, args=(stop,), daemon=True, name="call-steps").start()

    def told(event: str, payload: dict) -> None:
        emit(event, payload)
        steps.on(event, payload)
    try:
        return job(told)
    finally:
        stop.set()
