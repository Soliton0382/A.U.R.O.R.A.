# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from types import SimpleNamespace

from aurora import mdl_video as V


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, system, user, max_tokens, think=False):
        self.calls += 1
        return SimpleNamespace(answer=self.reply)


def test_only_a_request_to_create_makes_a_video():
    yes = FakeLLM('{"make": true, "from_picture": true, "prompt": "A red fox runs through snow, camera follows", "title": "La volpe"}')
    assert V.plan(yes, "anima questa foto", has_picture=True) == {"from_picture": True, "title": "La volpe",
                                                                  "prompt": "A red fox runs through snow, camera follows"}
    assert V.plan(yes, "anima questa foto", has_picture=False)["from_picture"] is False   # no picture, none animated
    no = FakeLLM('{"make": false}')
    assert V.plan(no, "cosa succede nel video?", True) is None
    assert V.plan(FakeLLM("not json"), "fammi un video", False) is None
    quiet = FakeLLM('{"make": true, "prompt": "x"}')
    assert V.plan(quiet, "come stai?", False) is None and quiet.calls == 0          # no video word, no reasoner call


def test_the_estimate_follows_the_measure():
    cfg = {"AURORA_VIDEO_SIZE": "1280x704", "AURORA_VIDEO_SECONDS": 5.0, "AURORA_VIDEO_STEPS": 30}
    assert V.estimate_minutes(cfg) == 19                       # 60 + 216 + 30 x 28 = 1116 s
    assert V.estimate_minutes({**cfg, "AURORA_VIDEO_STEPS": 50}) == 28
    assert V.estimate_minutes({**cfg, "AURORA_VIDEO_SECONDS": 2.5}) < 11
