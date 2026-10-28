# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎓 The DJ learns a style from a radio (aud_learn): the pattern of a known beat read back, the style kept as numbers
and used by the remix, the audio heard never written."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import aud_dj, aud_learn
from aurora import aud_synth as S
from aurora.aud_analysis import SR


def _beat(bpm: float, bars: int = 40) -> np.ndarray:
    """Four on the floor, claps on 2 and 4, open hats and the bass on the off-beats: the DJ's own synth."""
    step = 60 / bpm / 4
    x = np.zeros((int(bars * 16 * step * SR) + SR, 2), np.float32)
    k, c, h = S.kick(), S.clap(), S.hat(True)
    for b in range(bars):
        for s in range(16):
            t = (b * 16 + s) * step + 0.3
            if s % 4 == 0:
                S.place(x, k, t)
            if s in (4, 12):
                S.place(x, c, t)
            if s in (2, 6, 10, 14):
                S.place(x, h, t)
                S.place(x, S.bass_note(55.0, step * 1.5), t)
    return x


@pytest.mark.parametrize("bpm", [124.0, 138.0])
def test_a_known_beat_is_read_back(bpm):
    st = aud_learn.learn(_beat(bpm))
    assert abs(st["bpm"] - bpm) < 1.0
    assert st["kick"] == [0, 4, 8, 12] and st["clap"] == [4, 12]
    assert st["hat"] == [2, 6, 10, 14] and st["bass"] == [2, 6, 10, 14]


def test_a_listen_with_a_change_of_track_learns_from_its_steady_part():
    rng = np.random.default_rng(2)
    noise = lambda s: rng.normal(0, 0.1, (int(SR * s), 2)).astype(np.float32)       # noqa: E731
    st = aud_learn.learn(np.concatenate([noise(35), _beat(132.0, bars=36), noise(35)]))
    assert abs(st["bpm"] - 132.0) < 1.0 and st["kick"] == [0, 4, 8, 12] and st["clap"] == [4, 12]


def test_no_steady_beat_no_style():
    noise = np.random.default_rng(1).normal(0, 0.1, (SR * 40, 2)).astype(np.float32)
    with pytest.raises(ValueError, match="no steady beat"):
        aud_learn.learn(noise)


def test_the_style_is_kept_offered_used_and_forgotten(cfg, monkeypatch):
    folder = cfg.path("AURORA_MUSIC_DIR")
    monkeypatch.setattr(aud_dj, "_learned", lambda: aud_learn.load(folder))
    st = aud_learn.learn(_beat(128.0))
    sid = aud_learn.save(folder, "Trance di prova", st, "Radio di prova")
    assert sid == "learned-trance-di-prova" and oct((folder / aud_learn.FILE).stat().st_mode)[-3:] == "600"
    assert any(s["id"] == sid and s["learned"] for s in aud_dj.styles("it"))
    y, note = aud_dj.remix(_beat(110.0, bars=12), sid)
    assert note["bpm"] == pytest.approx(st["bpm"], abs=0.5) and len(y) > 0
    assert aud_learn.delete(folder, sid) and sid not in aud_learn.load(folder)
    with pytest.raises(ValueError):
        aud_dj.find(sid)


def test_a_listen_is_decoded_in_memory_and_nothing_is_written(tmp_path, monkeypatch):
    mp3 = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2",
                          "-i", "pipe:0", "-f", "mp3", "pipe:1"], input=_beat(128.0, 8).tobytes(), capture_output=True).stdout
    from aurora import aud_radio, net_public

    class Stream:
        status_code, headers = 200, {"content-type": "audio/mpeg"}

        def iter_raw(self, n):
            for i in range(0, len(mp3), n):
                yield mp3[i:i + n]

        def close(self):
            pass
    monkeypatch.setattr(aud_radio, "stream_url", lambda sid: ("https://radio.example/stream", "Radio di prova"))
    monkeypatch.setattr(net_public, "open_stream", lambda *a, **k: (SimpleNamespace(close=lambda: None), Stream()))
    monkeypatch.chdir(tmp_path)
    x, name = aud_learn.record("abc", 45)
    assert name == "Radio di prova" and x.shape[1] == 2 and len(x) > SR * 5
    assert not list(tmp_path.iterdir())                 # nothing of the stream on the disk


def test_a_style_learnt_goes_into_a_song_in_words_and_several_blend(monkeypatch):
    from aurora import aud_song_style
    a = aud_learn.learn(_beat(128.0))
    b = {**a, "bpm": 140.0, "pad": True, "pump": 0.5}
    monkeypatch.setattr(aud_dj, "_learned", lambda: {"learned-a": a, "learned-b": b})
    words = aud_learn.describe(a)
    assert "four-on-the-floor kick" in words and "claps on two and four" in words and "off-beat" in words
    r = aud_song_style.resolve({"learned": ["learned-a", "learned-b"]})
    assert r["bpm"] == 134 and "blend these rhythms" in r["brief"] and "strong sidechain pumping" in r["brief"]
    with pytest.raises(ValueError, match="unknown"):
        aud_song_style.check({"learned": ["learned-nope"]})
