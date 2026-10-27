# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's DJ set (aud_set; owner, 2026-10-27): the Camelot wheel, the order a DJ would play, each track in on the
beat of the one ending, and the timeline the console draws."""
import json

import numpy as np
import pytest

from aurora import aud_analysis as A, aud_deck as D, aud_set as S
from aurora.aud_analysis import SR


def _info(key, minor, bpm=128.0, seconds=60.0):
    beat = 60.0 / bpm
    return A.Info(seconds=seconds, bpm=bpm, confidence=9.0, first_beat=0.0, key=key, minor=minor,
                  beats=np.arange(0, seconds, beat), variation=0.01)


def test_the_camelot_wheel():
    assert S.label(0, False) == "8B" and S.label(9, True) == "8A"           # C major, A minor
    assert S.label(7, False) == "9B" and S.label(4, True) == "9A"           # G major, E minor
    assert S.distance((8, "B"), (8, "B")) == 0
    assert S.distance((8, "B"), (9, "B")) == 1 and S.distance((8, "B"), (8, "A")) == 1
    assert S.distance((12, "B"), (1, "B")) == 1                              # the wheel closes
    assert S.distance((8, "B"), (2, "B")) == 6


def test_the_order_goes_round_the_wheel_from_the_first_track():
    infos = [_info(0, False), _info(6, False), _info(7, False), _info(9, True)]   # C, F#, G, A minor
    assert S.order(infos) == [0, 2, 3, 1]          # 8B → 9B (a fifth) → 8A (its relative) → 2B (a clash): last


def test_a_set_joins_each_track_on_the_beat_near_its_end(monkeypatch, tmp_path):
    tracks = [np.full((60 * SR, 2), v, np.float32) for v in (0.2, 0.4, 0.6)]
    infos = iter([_info(0, False), _info(7, False), _info(9, True)])
    monkeypatch.setattr(A, "analyze", lambda x: next(infos))
    monkeypatch.setattr(D, "shift", lambda x, r, s: x)
    audio, plan = S.build(tracks, ["uno", "due", "tre"], keep_order=True, bars=8)
    t = plan["tracks"]
    assert [x["name"] for x in t] == ["uno", "due", "tre"] and plan["bpm"] == 128.0
    assert "transition" not in t[0] and t[1]["transition"]["kind"] == "bass_swap"      # 8B → 9B: neighbours
    beat = 60 / 128
    # the transition starts on a bar of the track ending, 8 bars of it still to play after the overlap
    assert t[1]["transition"]["from"] == pytest.approx(round(t[1]["transition"]["from"] / (4 * beat)) * 4 * beat, abs=0.02)
    assert t[0]["end"] == t[1]["transition"]["to"] and t[1]["start"] == t[1]["transition"]["from"]
    assert 60 - t[0]["end"] >= 8 * 4 * beat - 0.05
    assert plan["seconds"] == pytest.approx(len(audio) / SR, abs=0.1) and len(plan["peaks"]) == S.PEAKS
    assert np.max(np.abs(audio)) <= 0.951
    with pytest.raises(ValueError):
        S.build(tracks[:1], ["uno"])


def test_make_keeps_the_timeline_beside_the_mp3(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "load", lambda p, s=None: np.zeros((10 * SR, 2), np.float32))
    monkeypatch.setattr(S, "build", lambda tr, names, keep, bars, emit: (np.zeros((SR, 2), np.float32),
                                                                         {"bpm": 128, "seconds": 1, "tracks": [], "peaks": [0.0]}))
    monkeypatch.setattr(A, "save", lambda y, out, title="": out.write_bytes(b"mp3"))
    r = S.make([tmp_path / "a.mp3", tmp_path / "b.mp3"], tmp_path / "set.mp3")
    assert r["file"] == "set.mp3" and "peaks" not in r
    assert json.loads((tmp_path / "set.json").read_text())["peaks"] == [0.0]
