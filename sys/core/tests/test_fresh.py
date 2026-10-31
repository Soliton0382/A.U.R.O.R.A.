# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌅 The morning restart (owner, 1 Nov): once a day after the night's work, only when nothing would be lost or broken
(sys_fresh)."""
import logging
import time
from datetime import datetime

import pytest

from aurora import sys_ethics, sys_fresh, sys_health

LOG = logging.getLogger("test")


@pytest.fixture
def clean(cfg, monkeypatch):
    cfg.values.update(AURORA_REM_DREAM_HOURS="2-6", AURORA_LLM_BACKEND="cloud")
    state = {"ethics": (True, ""), "gpu": ""}
    monkeypatch.setattr(sys_ethics, "integrity", lambda *a, **k: state["ethics"])
    monkeypatch.setattr(sys_health, "gpu_job", lambda cfg: state["gpu"])
    cfg.path("AURORA_STATUS_DIR").mkdir(parents=True, exist_ok=True)
    return state


def test_the_window_opens_at_the_end_of_the_dreams_for_three_hours(cfg, clean):
    hours = [h for h in range(24) if sys_fresh.in_window(cfg, datetime(2026, 11, 1, h, 30))]
    assert hours == [6, 7, 8]
    cfg.values.update(AURORA_REM_DREAM_HOURS="22-23")                   # across midnight
    assert [h for h in range(24) if sys_fresh.in_window(cfg, datetime(2026, 11, 1, h))] == [0, 1, 23]


def test_each_thing_that_would_be_lost_or_broken_is_said(cfg, clean):
    now = time.time()
    assert sys_fresh.why_not(cfg, [], False, now) is None
    assert sys_fresh.why_not(cfg, [{"origin": "rem", "done": False, "started": now - 9}], False, now) == "1 run(s) open"
    assert "10 minutes" in sys_fresh.why_not(cfg, [{"origin": "webui", "done": True, "started": now - 120}], False, now)
    assert sys_fresh.why_not(cfg, [{"origin": "webui", "done": True, "started": now - 900}], False, now) is None
    assert sys_fresh.why_not(cfg, [{"origin": "routine", "done": True, "started": now - 60}], False, now) is None
    assert sys_fresh.why_not(cfg, [], True, now) == "a backup is running"
    clean["gpu"] = "a painting"
    assert sys_fresh.why_not(cfg, [], False, now) == "the GPU: a painting"
    clean["ethics"] = (False, "sys_ethics.py changed")                   # C430: the API would not start again
    assert sys_fresh.why_not(cfg, [], False, now).startswith("ethics code")


def test_the_local_reasoner_answering_waits(cfg, clean, monkeypatch):
    cfg.values.update(AURORA_LLM_BACKEND="local", AURORA_LLM_HOST="127.0.0.1", AURORA_LLM_PORT=1)

    class R:
        def json(self):
            return [{"is_processing": False}, {"is_processing": True}]
    monkeypatch.setattr(sys_fresh.httpx, "get", lambda *a, **k: R())
    assert sys_fresh.why_not(cfg, [], False) == "the local reasoner is answering"


def test_once_a_day_after_the_night_and_a_wait_said_once(cfg, clean, caplog):
    done, asks = [], []
    morning = datetime(2026, 11, 1, 6, 5)

    def ask():
        asks.append(1)
        return "1 run(s) open" if len(asks) == 1 else None
    caplog.set_level(logging.INFO, "test")
    said = sys_fresh.tick(cfg, morning, False, "", ask, lambda: done.append(1), LOG)
    assert said == "the night's work still going" and not asks and not done        # REM still had a task
    said = sys_fresh.tick(cfg, morning, True, said, ask, lambda: done.append(1), LOG)
    assert said == "1 run(s) open" and not done
    said = sys_fresh.tick(cfg, morning, True, said, ask, lambda: done.append(1), LOG)
    assert said == "" and done == [1]
    sys_fresh.tick(cfg, morning.replace(hour=7), True, "", ask, lambda: done.append(1), LOG)
    assert done == [1]                                                  # once a day
    assert sum("waits" in r.message for r in caplog.records) == 2


def test_outside_the_window_never_and_a_window_without_a_clean_moment_skips_the_day(cfg, clean, caplog):
    done = []
    caplog.set_level(logging.INFO, "test")
    assert sys_fresh.tick(cfg, datetime(2026, 11, 1, 14), True, "", lambda: None, lambda: done.append(1), LOG) == ""
    assert not done and not sys_fresh.done_today(cfg, datetime(2026, 11, 1, 14))
    sys_fresh.tick(cfg, datetime(2026, 11, 1, 9, 1), True, "1 run(s) open", lambda: None, lambda: done.append(1), LOG)
    assert not done and sys_fresh.done_today(cfg, datetime(2026, 11, 1, 9, 1))
    assert any("skipped today: 1 run(s) open" in r.message for r in caplog.records)


def test_the_api_not_answering_never_restarts_blind(cfg, clean):
    done = []

    def ask():
        raise OSError("connection refused")
    said = sys_fresh.tick(cfg, datetime(2026, 11, 1, 6), True, "", ask, lambda: done.append(1), LOG)
    assert said.startswith("the check failed") and not done
