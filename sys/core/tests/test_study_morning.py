# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Studying at night what she could not answer, and the good morning that tells it (owner, 2026-10-05)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aurora import kno_morning, kno_study

NOW = datetime.now(timezone.utc)


def turn(role, text, rid, hours_ago=2, **extra):
    return SimpleNamespace(text=text, created_at=(NOW - timedelta(hours=hours_ago)).isoformat(),
                           extra={"role": role, "run_id": rid, **extra})


class P:
    def __init__(self, turns):
        self.reader = SimpleNamespace(recent=lambda n, domain="conversation": turns if domain == "conversation" else [],
                                      layout=SimpleNamespace(shards=lambda *a: []))


def test_the_declined_questions_are_studied_once(cfg):
    turns = [turn("user", "Cos'è la decoerenza quantistica? [fonti]", "r1"), turn("assistant", "Non lo so", "r1", abstained=True),
             turn("user", "Che ore sono?", "r2"), turn("assistant", "Le 10", "r2", mode="self"),
             turn("user", "Chi era Eratostene?", "r3", hours_ago=24 * 9), turn("assistant", "Non lo so", "r3", hours_ago=24 * 9, abstained=True),
             turn("user", "Cos'è la decoerenza quantistica?", "r4"), turn("assistant", "Non lo so", "r4", abstained=True)]
    got = kno_study.pending(P(turns), cfg)
    assert [g["question"] for g in got] == ["Cos'è la decoerenza quantistica?"]      # once; not the old one, not "self"
    pic = turns + [turn("user", "What color is in this image?", "r5"), turn("assistant", "Non lo so", "r5", abstained=True)]
    assert "What color is in this image?" not in [g["question"] for g in kno_study.pending(P(pic), cfg)]
    kno_study._mark(cfg, "r1", {"learned": True})
    assert [g["run_id"] for g in kno_study.pending(P(turns), cfg)] == ["r4"]         # r1 studied; the same question again


def test_the_good_morning_says_only_what_happened():
    quiet = {"dream": "", "learned": [], "not_yet": [], "blocked": 0, "links_today": 0, "concepts": 0, "documents": 0, "passages": 0}
    assert "Notte tranquilla" in kno_morning.compose(quiet, "Ada", "Aurora")
    night = {**quiet, "learned": ["Cos'è la decoerenza quantistica?"], "not_yet": ["X"], "documents": 12, "passages": 340,
             "blocked": 1, "dream": "un fiume di stelle"}
    text = kno_morning.compose(night, "Ada", "Aurora")
    assert text.startswith("☀️ Buongiorno, Ada!") and "ora so rispondere su «Cos'è la decoerenza quantistica?»" in text
    assert "12 documenti nuovi (340 passaggi)" in text and "fermato un attacco" in text and "Su una domanda" in text and "🧠" not in text
    assert "Good morning" in kno_morning.compose(night, "Ada", "Aurora", "en_US")
