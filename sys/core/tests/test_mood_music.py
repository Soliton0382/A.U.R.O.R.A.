# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Music in her mood (owner, 2026-10-27): joy from the music made with her, fading over hours; «listening» while the
player plays, gone when it stops or says nothing for LISTEN_S."""
import os
import time

from aurora import kno_mood


def test_joy_grows_with_the_music_made_and_fades(cfg):
    mixes = cfg.path("AURORA_MUSIC_DIR") / "mixes"
    mixes.mkdir(parents=True)
    assert kno_mood.joy(cfg)["value"] == 0.0
    now = time.time()
    (mixes / "song.mp3").write_bytes(b"x")
    (mixes / "song.song.json").write_text("{}")
    j = kno_mood.joy(cfg, now)
    assert j["value"] == 0.5 and "1 canzoni cantate" in j["causes"][0]          # one piece just made: half
    (mixes / "mix.mp3").write_bytes(b"x")
    assert kno_mood.joy(cfg, now)["value"] > 0.6
    later = now + kno_mood.JOY_HALF_H * 3600
    assert kno_mood.joy(cfg, later)["value"] < kno_mood.joy(cfg, now)["value"]   # fading
    old = now - 30 * 3600
    for f in mixes.iterdir():
        os.utime(f, (old, old))
    assert kno_mood.joy(cfg, now)["value"] == 0.0                                # a day gone: no joy from it


def test_listening_is_said_while_the_player_plays(monkeypatch):
    from aurora.sys_config import ConfigError
    import pytest
    try:
        from aurora.api import dj as M
    except ConfigError:
        pytest.skip("no configuration to load the API with")
    M._listening.clear()
    M._listening["a"] = {"title": "Paradiso Rising", "at": time.time()}
    assert M.listening("a")["title"] == "Paradiso Rising" and M.listening("b") is None
    M._listening["a"]["at"] = time.time() - M.LISTEN_S - 1
    assert M.listening("a") is None                                               # silent too long: stopped
