# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎙️ The quick path of a spoken turn (owner, 29 Oct 2026: «mentre parlo lei già comincia a capire… una cosa molto più
naturale di adesso»; ROADMAP, the voice that listens while you speak).

A call's sentence went through the whole answer path: measured on the reference machine, 10–34 s from the end of the
speech to her first sound, of which Whisper 0.13–0.16 s and the first sentence's voice 0.7–0.9 s; the rest the
translation, the memories, the vault and the thinking (the reasoner alone gives a first sentence in 0.16–0.27 s).

Here a one-token choice (ROUTE, the reasoner's decide: 0.09 s median) sorts the sentence: plain talk — greetings,
feelings, jokes, opinions, everyday advice — is answered by the reasoner at once, with no thinking, from her character,
the day and the call's last turns, and streamed: each sentence said while the next is written. Anything to check or
do — facts, the web, a memory older than the call, the person's data, a device, a sum — goes to the whole path, which
answers it as in the chat; a lean to SEARCH under SURE still talks (everyday advice sat at 0.65). The vault's rule
stands, no fact said from her training: one she starts on anyway is cut at HANDOFF and handed on. The turn is
remembered like any other (mode «talk»). The local reasoner off (a GPU job) or failing: the whole path, as before.

quick(p, cfg, question, recent, emit)   (the answer, handed on), streamed as «talk.delta» events (api/call: the job)
"""
from __future__ import annotations

from datetime import timedelta

from . import sns_clock, sys_config, sys_persona, txt_lang

HANDOFF = "⏩"
RECENT = 6                                            # the call's last turns she sees
MAX_TOKENS = 220                                      # a spoken answer: a few sentences
SURE = 0.7                                            # P(SEARCH) above it: the whole path

ROUTE = ("You sort what a person says to their assistant on a phone call. Answer with one word.\n"
         "TALK: small talk, greetings, thanks, goodbyes, feelings, how are you, jokes, compliments, opinions and tastes, "
         "common-sense advice about everyday life, asking to repeat or about what was just said in this call — anything a "
         "friend answers at once without checking anything.\n"
         "SEARCH: anything that needs checking or doing: facts (science, numbers, dates, news, sport, the weather, "
         "people, places), explanations of a subject, a calculation, what was said in an earlier conversation, the "
         "person's own data (mail, calendar, appointments, flights, reminders, the house, devices, accounts), an action "
         "to perform.\nWhen unsure, SEARCH.")

STYLE = {
    "it": ("\n\nSEI AL TELEFONO CON {owner}: parli, non scrivi. Rispondi come in una conversazione vera: una o due frasi "
           "brevi, naturali, niente elenchi, niente markdown, niente emoji, niente link. Nessun fatto, numero o data "
           f"detto a memoria: se ti accorgi che servirebbe, scrivi {HANDOFF} e fermati."),
    "en": ("\n\nYOU ARE ON THE PHONE WITH {owner}: you speak, you do not write. Answer as in a real conversation: one or "
           "two short, natural sentences, no lists, no markdown, no emoji, no links. No fact, number or date said from "
           f"memory: if you find one is needed, write {HANDOFF} and stop."),
}


def system(cfg: sys_config.Config, recent: list, lang: str) -> str:
    from . import kno_self                                # the rule on greeting again, one for both routes
    today = sns_clock.now(cfg)
    days = "; ".join(f"{label} = {sns_clock.DAYS_IT[d.weekday()]} {d:%Y-%m-%d}" for label, d in
                     (("oggi", today), ("ieri", today - timedelta(days=1))))
    return (sys_persona.identity(cfg) + f"\n\nCALENDAR: {days}, now {today:%H:%M}."
            + (f"\n\nTHIS CONVERSATION SO FAR:\n{_turns(recent)}" if recent else "")
            + (kno_self.NO_GREETING if kno_self.going_on(recent) else "")
            + kno_self.people_block(cfg, "en" if lang == "en" else "it")
            + STYLE["en" if lang == "en" else "it"].replace("{owner}", str(cfg["AURORA_OWNER_NAME"])))


def _turns(recent: list) -> str:
    return "\n".join(f"{'Owner' if t.extra.get('role') == 'user' else 'Aurora'}: {t.text[:400]}" for t in recent[-RECENT:])


def talk(model, question: str, recent: list) -> bool:
    """Whether the sentence is plain talk (the quick path); unsure or unreadable: no."""
    last = _turns(recent[-2:])
    user = (f"EARLIER IN THE CALL:\n{last}\n\n" if last else "") + f"THE PERSON SAYS: {question}"
    sure = getattr(model, "decide", lambda *a: None)(ROUTE, user, ["TALK", "SEARCH"])
    if sure is None:
        return model.complete(ROUTE, user, 3).answer.strip().upper().startswith("TALK")
    return sure["SEARCH"] <= SURE


def quick(p, cfg: sys_config.Config, question: str, recent: list, emit) -> tuple[str, bool]:
    """(the answer, handed on): plain talk streamed as «talk.delta»; anything else handed on at once. Always the
    local reasoner, whatever the Models page gives «self»: a cloud model took 4.2 s for the choice alone (one token
    read from its probabilities only here) and the masking before each sentence; the whole path keeps the owner's."""
    model = p.llm
    if not talk(model, question, recent):
        return "", True
    parts = []
    for kind, piece in model.stream(system(cfg, recent, txt_lang.detect(question)), question, MAX_TOKENS, think=False):
        if kind != "answer" or not piece:
            continue
        if not parts:
            piece = piece.lstrip()
            if not piece:
                continue
        if HANDOFF in piece:                          # a fact after all: what she said stays, the rest goes on
            piece = piece.split(HANDOFF, 1)[0]
            if piece.strip():
                parts.append(piece)
                emit("talk.delta", {"text": piece})
            return "".join(parts).strip(), True
        parts.append(piece)
        emit("talk.delta", {"text": piece})
    text = "".join(parts).strip()
    return text, not text                             # nothing said: the whole path answers
