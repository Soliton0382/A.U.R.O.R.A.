# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from aurora import agt_react as R


def test_a_failed_request_of_the_owner_is_diagnosed_once_per_kind_never_in_a_loop(cfg):
    t0 = 1_800_000_000.0
    err = "Error executing tool ig_publish_photo: no Instagram account (request b926e9e408)"
    assert R.should_react(cfg, "approval", err, t0)
    assert not R.should_react(cfg, "approval", err.replace("b926e9e408", "aa7d8a68c5"), t0 + 60)   # same kind
    assert R.should_react(cfg, "approval", err, t0 + R.REPEAT_H * 3600 + 1)                          # hours later
    assert not R.should_react(cfg, "react", "anything", t0)            # a repair never repairs itself
    assert not R.should_react(cfg, "rem", "a dream failed", t0)        # not the owner's request
    assert not R.should_react(cfg, "webui", "  ", t0)


def test_at_most_a_few_repairs_a_day(cfg):
    t0 = 1_800_000_000.0
    started = sum(R.should_react(cfg, "webui", f"KeyError: field_{chr(97 + i)}", t0 + i) for i in range(10))
    assert started == R.PER_DAY
    assert R.should_react(cfg, "webui", "KeyError: field_z", t0 + 86_401)      # the next day
