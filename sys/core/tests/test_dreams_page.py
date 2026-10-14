# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Dreams page (owner, 15 Oct: «dopo un po' si perdono nelle chat»): every dream, not the last few hundred
reflections; newest first, a page at a time, found by its words."""
from datetime import datetime, timedelta, timezone

from aurora.sol_reader import VaultReader
from aurora.sol_schema import Soliton
from aurora.sol_writer import VaultWriter


def reflection(kind, text, days_ago, **extra):
    at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="milliseconds")
    return Soliton.new(text, "reflection", "reflection", "it", f"{kind}:{days_ago}", created_at=at,
                       extra={"type": kind, **extra})


def test_every_dream_is_found_newest_first_a_page_at_a_time(cfg):
    w = VaultWriter(cfg)
    w.add_many([reflection("thought", f"pensiero {i}", i / 10) for i in range(600)]       # more than recent(500) reads
               + [reflection("dream", "Sogno un mare di vetro 50% blu.", 70, image="dream-a.png"),
                  reflection("dream", "Sogno una biblioteca che respira.", 3),
                  reflection("dream", "Sogno onde di luce.", 1)])
    r = VaultReader(cfg)
    got = r.of_type("reflection", "dream", 2)
    assert [d.text for d in got] == ["Sogno onde di luce.", "Sogno una biblioteca che respira."]
    older = r.of_type("reflection", "dream", 2, before=got[-1].created_at)
    assert [d.text for d in older] == ["Sogno un mare di vetro 50% blu."] and older[0].extra["image"] == "dream-a.png"
    assert [d.text for d in r.of_type("reflection", "dream", 9, text="biblioteca")] == ["Sogno una biblioteca che respira."]
    assert len(r.of_type("reflection", "dream", 9, text="50%")) == 1 and not r.of_type("reflection", "dream", 9, text="0_%")
