# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🗣️ What she is doing, said aloud while the tools work (owner, 3 Nov: «per evitare che aurora rimanga muta per troppo
tempo quando apre gli strumenti, potrebbe dire cosa sta facendo… procedo, un attimo, accesso al calendario»). A real call
had 66 s of an agent's work in silence (M279), and the owner spoke over it.

Short lines read from a step's name only, never from its arguments or results: what is said can hold nothing private.
At most one line every MIN_GAP_S, never the same twice running; with nothing new for QUIET_S a line says she is still
at it. Both the call and the chat's hands-free conversation say them (event talk.step)."""
from __future__ import annotations

import re
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


# 🛑 «lascia stare»: the whole sentence and nothing else, so that «basta con il sale nella ricetta» stays a question; and
# only while something is at work or owed (api/call._turn): otherwise it is an ordinary sentence
CANCEL = re.compile(r"(?:(?:no|ok|niente|anzi|okay),? )*(?:annulla|lascia stare|lascia perdere|lasciamo stare|lasciamo perdere|"
                    r"lascia|fermati|ferma|stop|basta|basta cosi|basta così|non importa|non fa niente|dimentica|"
                    r"cancel|cancel it|never mind|nevermind|forget it|stop it|that's enough)(?: grazie| thanks)?")
CANCELLED = ("Ok, lascio stare.", "Okay, dropping it.")


def cancels(text: str) -> bool:
    return bool(CANCEL.fullmatch(re.sub(r"[^\w' ]", "", str(text)).strip().lower()))


# ✏️ «no, volevo dire…»: what comes after it is the sentence, and what she was doing for the one before is left
CORRECTION = re.compile(r"(?:no,? |scusa,? |anzi,? )*(?:volevo dire|intendevo|mi correggo|i meant|i mean|sorry,? i meant)[,:]? +(.+)", re.I | re.S)


def corrected(text: str) -> str | None:
    m = CORRECTION.fullmatch(str(text).strip())
    return m.group(1).strip() if m else None


# 🔤 What the voice spells letter by letter (owner, 4 Nov: «emma acca emme acca»; the phonemes, C500): «mh», «mhm», «hm»,
# «mmm», in the reasoner's answers too. Not a measure: «5 mm» stays.
SPELLED = re.compile(r"(?<!\d)(?<!\d )\b(?:m+h+m*|h+m+|m{2,})(?:[ -](?:m+h+m*|h+m+|m{2,}))*\b", re.I)


def sayable(text: str, lang: str) -> str:
    return SPELLED.sub("Uhm" if lang == "it" else "Hmm", str(text))


class Nods:
    """👂 «sì… ok… uhm» while the owner talks (owner, 3 Nov: «come farebbe una persona quando le parli»), at some of the
    pauses inside a long sentence: after SPOKEN_S of speech, at most one every GAP_S, one pause in two, never the same
    twice running. They say she is listening, nothing more; nothing is understood from them, nothing is remembered."""
    SPOKEN_S, GAP_S, CHANCE = 2.5, 6.0, 0.5
    WORDS = (("Sì.", "Ok.", "Uhm.", "Capito.", "Certo."), ("Yes.", "Okay.", "Hmm.", "I see.", "Right."))
    THINK = (("Vediamo…", "Uhm…", "Allora…"), ("Let me see…", "Hmm…", "Well…"))

    def __init__(self, lang: str, rng=None, clock=time.monotonic) -> None:
        import random
        self.i, self.rng, self.clock = 0 if lang == "it" else 1, rng or random.Random(), clock
        self.last, self.word = -1e9, None

    def words(self) -> tuple[str, ...]:
        return self.WORDS[self.i] + self.THINK[self.i]

    def at_pause(self, spoken_s: float) -> str | None:
        if spoken_s < self.SPOKEN_S or self.clock() - self.last < self.GAP_S or self.rng.random() >= self.CHANCE:
            return None
        self.word = self.rng.choice([w for w in self.WORDS[self.i] if w != self.word])
        self.last = self.clock()
        return self.word

    def thinking(self) -> str:
        return self.rng.choice(self.THINK[self.i])


class Owed:
    """🗣️ What she still owes: an answer of the whole path whose sentence the owner spoke over (owner, 3 Nov: «quel tocco
    in più»; M279: 66 s of an agent's work, its answer never said). Said once the turn in progress has ended."""
    LEAD = ("Per quello di prima: ", "About what you asked before: ")

    def __init__(self, lang: str) -> None:
        self.i, self.items = 0 if lang == "it" else 1, []

    def add(self, text: str) -> None:
        if text.strip():
            self.items.append(text.strip())

    def take(self) -> list[str]:
        out, self.items = [self.LEAD[self.i] + t for t in self.items], []
        return out


async def in_turn(heard, turn, free, failed=None) -> None:
    """One sentence of the owner at a time, in order, but never behind a long answer: once a turn has gone to the whole
    path (`free` set) the next sentence is heard at once, and that turn ends by itself. `failed(e)`: a turn that broke,
    so that it is told and not lost in silence (C499)."""
    import asyncio
    running: set = set()

    async def guarded(audio) -> None:
        try:
            await turn(audio)
        except Exception as e:
            if failed is None:
                raise
            try:
                await failed(e)
            except Exception:               # the call itself is gone: nobody left to tell
                pass

    while True:
        audio = await heard.get()
        free.clear()
        task = asyncio.create_task(guarded(audio))
        running.add(task)
        task.add_done_callback(running.discard)
        wait = asyncio.create_task(free.wait())
        await asyncio.wait({task, wait}, return_when=asyncio.FIRST_COMPLETED)
        wait.cancel()
