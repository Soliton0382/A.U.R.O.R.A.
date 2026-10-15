# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What was found for the question stays in her prompt (C326: a week of session memories pushed out the conversation
of 8 days before that the owner was asking about; she said she did not remember it)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aurora.kno_self import SelfTalk


def mem(sid, days, text, **extra):
    at = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return SimpleNamespace(sid=sid, created_at=at, text=text, extra=extra)


def talk(chars):
    cfg = {"AURORA_MEMORY_RECALL_CHARS": chars, "AURORA_OWNER_NAME": "Owner", "AURORA_ASSISTANT_NAME": "Aurora",
           "AURORA_TIMEZONE": "UTC"}
    return SimpleNamespace(cfg=cfg)


def test_the_conversation_asked_about_wins_over_a_week_of_session_memories():
    old = mem("old", 8, "Abitiamo in affitto: il proprietario non ci rende la cauzione.", role="user")
    week = [mem(f"d{i}", i % 7, f"Sessione {i}: " + "saluti e cielo blu " * 30, type="session_memory")
            for i in range(20)]
    mems = sorted([old, *week], key=lambda s: s.created_at)
    block = SelfTalk._memory_block(talk(3000), mems, ["old"])
    assert "cauzione" in block and len(block) <= 3000
    assert "Sessione" in block                                   # the room left goes to the last days
    lines = block.split("\n")
    assert "cauzione" in lines[0]                               # still shown oldest first


def test_without_hits_the_newest_win_as_before():
    week = [mem(f"d{i}", i, f"Sessione {i}: " + "x" * 400, type="session_memory") for i in range(10)]
    mems = sorted(week, key=lambda s: s.created_at)
    block = SelfTalk._memory_block(talk(1500), mems)
    assert "Sessione 0" in block and "Sessione 9" not in block
