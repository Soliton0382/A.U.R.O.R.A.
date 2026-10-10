# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's DJ (owner, 2026-10-05): the analysis on signals whose answer is known, a remix and a mix end to end."""
import shutil

import numpy as np
import pytest

from aurora import aud_analysis as A, aud_dj as D

SR = A.SR
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def beats(bpm, root_hz=220.0, minor=True, secs=30, offset=0.2, seed=2):
    rng = np.random.default_rng(seed)
    t = np.arange(SR * secs) / SR
    third = 2 ** ((3 if minor else 4) / 12)
    x = sum(0.12 * np.sin(2 * np.pi * f * t) for f in (root_hz, root_hz * third, root_hz * 1.5))
    for b in np.arange(offset, secs, 60 / bpm):
        i = int(b * SR)
        n = min(2000, len(x) - i)
        x[i:i + n] += 0.5 * rng.normal(0, 1, n) * np.exp(-np.arange(n) / 300)
    return np.stack([x, x], 1).astype(np.float32)


def choir(secs=48, seed=1):
    """Slow chords sung with a vibrato of ~5.5 Hz, three voices a note: no beat."""
    rng = np.random.default_rng(seed)
    t = np.arange(SR * secs) / SR
    x = np.zeros_like(t)
    for k, chord in enumerate([(62, 66, 69), (67, 71, 74), (69, 73, 76)] * 2):
        seg = (t >= k * 8) & (t < k * 8 + 8)
        for m in chord:
            for _ in range(3):
                f = 440 * 2 ** ((m - 69) / 12) * (1 + rng.normal(0, 0.002))
                v = 5.5 * (1 + rng.normal(0, 0.08))
                x[seg] += 0.05 * np.sin(2 * np.pi * f * t[seg] - (f * 0.006 / v) * np.cos(2 * np.pi * v * t[seg]))
    return np.stack([x, x], 1).astype(np.float32)


def test_tempo_beat_and_key_of_known_signals():
    for bpm, hz, minor, name in ((100, 220.0, True, "A minor"), (128, 261.63, False, "C major"), (140, 196.0, True, "G minor")):
        i = A.analyze(beats(bpm, hz, minor, offset=0.2))
        per = 60 / bpm
        assert abs(i.bpm - bpm) < 0.5 and i.as_dict()["key"] == name and i.steady
        assert abs(((i.first_beat - 0.2 + per / 2) % per) - per / 2) < 0.015           # within one analysis frame


def test_a_choir_has_no_steady_beat():
    assert not A.analyze(choir()).steady


def test_a_remix_follows_the_style_s_tempo_and_never_clips(tmp_path):
    A.save(beats(100, secs=40), tmp_path / "song.mp3")
    out = D.make([tmp_path / "song.mp3"], "trance", tmp_path / "remix.mp3")
    y = A.load(tmp_path / out["file"])
    assert out["tracks"][0]["bpm"] == 138 and abs(A.analyze(y).bpm - 138) < 1.0
    assert np.max(np.abs(y)) <= 1.0 and 25 < out["seconds"] < 40                        # 100 → 138: shorter
    A.save(choir(), tmp_path / "choir.mp3")
    out = D.make([tmp_path / "choir.mp3"], "techno_trance", tmp_path / "choir_remix.mp3")
    assert out["tracks"][0]["steady"] is False and abs(out["seconds"] - 48) < 3          # its own time kept


def test_a_mix_joins_tracks_at_one_tempo(tmp_path):
    for n, bpm in (("a", 120), ("b", 126)):
        A.save(beats(bpm, secs=30, seed=len(n) + bpm), tmp_path / f"{n}.mp3")
    out = D.make([tmp_path / "a.mp3", tmp_path / "b.mp3"], "house", tmp_path / "set.mp3")
    assert [t["bpm"] for t in out["tracks"]] == [124, 124]
    with pytest.raises(ValueError):
        D.make([tmp_path / "a.mp3"], "polka", tmp_path / "x.mp3")


def test_the_drums_follow_a_song_that_moves():
    """Owner, 10 Oct: «ogni tanto esce fuori ritmo». A drummer who drifts 118→121 BPM with ±8 ms of his own: the beats
    are followed one by one (M180: the fixed grid sat 131-216 ms off, on the off-beat; followed: 3 ms)."""
    rng = np.random.default_rng(4)
    t, truth = 0.6, []
    while t < 59:
        truth.append(t + rng.normal(0, 0.008))
        t += 60 / (118 + 3 * t / 60)
    truth = np.array(truth)
    x = np.zeros(int(60 * A.SR), np.float32)
    k = np.arange(int(0.1 * A.SR)) / A.SR
    kick = (np.sin(2 * np.pi * (55 + 90 * np.exp(-k * 30)) * k) * np.exp(-k * 18)).astype(np.float32)
    hat = (rng.standard_normal(1300) * np.exp(-np.arange(1300) / 300)).astype(np.float32) * 0.25
    for a, b in zip(truth[:-1], truth[1:]):
        x[int(a * A.SR):int(a * A.SR) + len(kick)] += kick
        x[int((a + b) / 2 * A.SR):int((a + b) / 2 * A.SR) + len(hat)] += hat          # hats on the off-beat
    info = A.analyze(np.stack([x, x], axis=1))
    assert info.steady and abs(info.bpm - 60 * (len(truth) - 1) / (truth[-1] - truth[0])) < 0.5
    off = np.abs(info.beats[:, None] - truth[None, :]).min(axis=1)
    assert np.median(off) < 0.010 and (off > 0.030).mean() < 0.02
