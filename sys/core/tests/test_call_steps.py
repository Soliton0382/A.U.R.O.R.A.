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
