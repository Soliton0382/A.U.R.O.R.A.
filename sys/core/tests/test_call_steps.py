# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What she is doing, said aloud (sys_call_steps): read from a step's name only, not too often."""
from aurora import sys_call_steps as S


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def stage(lang="it"):
    said, clock = [], Clock()
    return S.Steps(lambda e, p: said.append((e, p["text"])), lang, clock), said, clock


def test_a_tool_is_said_by_its_name_and_never_by_what_it_carries():
    assert S.line("tool.call", {"name": "calendar__events"})[0] == "Apro il calendario."
    assert S.line("tool.call", {"name": "mystery__x", "arguments": "la mia password"}) == S.ANY_TOOL
    assert S.line("answer.final", {"text": "private"}) is None


def test_not_too_often_and_never_the_same_twice_running():
    s, said, clock = stage()
    clock.t = 1.0
    s.on("tool.call", {"name": "mail__list"})
    assert not said                                   # too soon after the turn began
    clock.t = 4.0
    s.on("tool.call", {"name": "mail__list"})
    clock.t = 9.0
    s.on("tool.call", {"name": "mail__read"})         # the same line
    clock.t = 10.0
    s.on("verify.keep", {})
    assert [x[1] for x in said] == ["Guardo la posta.", "Verifico."]


def test_with_nothing_new_she_says_she_is_still_at_it_in_her_language():
    s, said, clock = stage("en")
    clock.t = 14.0
    s.tick()
    assert not said
    clock.t = 15.0
    s.tick()
    clock.t = 31.0
    s.tick()
    assert [x[1] for x in said] == ["Working on it.", "Just a moment more."] and said[0][0] == "talk.step"


def test_the_whole_path_of_a_sentence_says_its_steps(monkeypatch):
    def whole(told):
        told("tool.call", {"name": "calendar__events"})
        return "fatto"
    monkeypatch.setattr(S, "MIN_GAP_S", 0.0)
    seen = []
    assert S.watched(lambda e, p: seen.append((e, p)), "it", whole) == "fatto"
    assert [e for e, _ in seen] == ["tool.call", "talk.step"] and seen[-1][1]["text"] == "Apro il calendario."


def test_an_answer_spoken_over_is_said_afterwards_once():
    o = S.Owed("it")
    o.add("  ")
    assert o.take() == []
    o.add("Domani hai due impegni.")
    assert o.take() == ["Per quello di prima: Domani hai due impegni."] and o.take() == []


def test_the_next_sentence_is_heard_while_a_long_turn_goes_on():
    import asyncio

    async def play():
        heard, free, log = asyncio.Queue(), asyncio.Event(), []
        slow_end = asyncio.Event()

        async def turn(audio):
            log.append(f"start {audio}")
            if audio == "long":
                free.set()                            # it went to the whole path
                await slow_end.wait()
            log.append(f"end {audio}")
        loop = asyncio.create_task(S.in_turn(heard, turn, free))
        await heard.put("short")
        await heard.put("long")
        await heard.put("next")
        for _ in range(20):
            await asyncio.sleep(0)
        assert log == ["start short", "end short", "start long", "start next", "end next"]   # in order, «next» not behind
        slow_end.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert log[-1] == "end long"
        loop.cancel()
    asyncio.run(play())


def test_nothing_she_says_by_habit_is_spelled_letter_by_letter():
    for i in (0, 1):
        for w in S.Nods.WORDS[i] + S.Nods.THINK[i]:
            assert S.sayable(w, "it" if i == 0 else "en") == w, w
    assert S.sayable("Mh mh, certo.", "it") == "Uhm, certo."
    assert S.sayable("Mmm... hm-mh, vediamo", "it") == "Uhm... Uhm, vediamo"
    assert S.sayable("Mm-hm, right", "en") == "Hmm, right"
    for kept in ("Sono caduti 5 mm di pioggia.", "Uhm, mamma mia", "Ohm e amma", "Ehm"):
        assert S.sayable(kept, "it") == kept, kept


def test_a_turn_that_breaks_is_told_and_the_next_is_heard():
    import asyncio

    async def play():
        heard, free, told, log = asyncio.Queue(), asyncio.Event(), [], []

        async def turn(audio):
            if audio == "bad":
                raise NameError("nods_on")
            log.append(audio)

        async def failed(e):
            told.append(str(e))
        loop = asyncio.create_task(S.in_turn(heard, turn, free, failed))
        await heard.put("bad")
        await heard.put("next")
        for _ in range(20):
            await asyncio.sleep(0)
        assert told == ["nods_on"] and log == ["next"]
        loop.cancel()
    asyncio.run(play())


def test_lascia_stare_is_the_whole_sentence_and_nothing_else():
    for yes in ("Lascia stare.", "no, annulla", "basta, grazie", "Never mind", "stop", "ok lascia perdere", "Forget it!"):
        assert S.cancels(yes), yes
    for no in ("basta con il sale nella ricetta", "stop al timer della pasta", "annulla la sveglia di domani", "lascia la luce accesa",
               "non importa quanto costa, trovalo", "cancel my subscription"):
        assert not S.cancels(no), no


def test_a_nod_only_at_a_pause_of_a_long_sentence_not_too_often_never_the_same():
    import random
    clock = Clock()
    n = S.Nods("it", random.Random(1), clock)
    assert n.at_pause(1.0) is None                    # she does not nod at the first words
    said = []
    for t in range(0, 120, 2):
        clock.t = float(t)
        w = n.at_pause(5.0)
        if w:
            said.append((t, w))
    assert said and all(b[0] - a[0] >= n.GAP_S for a, b in zip(said, said[1:]))
    assert all(a[1] != b[1] for a, b in zip(said, said[1:]))


def test_a_correction_is_the_sentence_that_follows_it():
    assert S.corrected("No, volevo dire il calendario di martedì") == "il calendario di martedì"
    assert S.corrected("I meant Tuesday") == "Tuesday"
    assert S.corrected("Che cosa volevo dire ieri?") is None and S.corrected("no") is None
