# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Two decks (owner, 10 Oct: «un classico remix su due brani… facendoti decidere un po' tutto»): one tempo, B in A's
key, B's downbeat on A's beat, every choice checked."""
import numpy as np
import pytest

from aurora import aud_analysis as A
from aurora import aud_deck as K
from test_dj import beats


def test_the_choices_are_checked():
    assert K.options({})["transition"] == "bass_swap" and K.options({"bpm": 128})["bpm"] == 128
    for bad in ({"mode": "x"}, {"bars": 5}, {"transition": "scratch"}, {"bpm": 300}, {"gain_a": 40}):
        with pytest.raises(ValueError):
            K.options(bad)


def test_b_is_tuned_to_a_by_the_smallest_shift():
    a = A.Info(1, 120, 9, 0, 9, True)          # A minor → its relative major, C
    assert K.semitones(a, A.Info(1, 120, 9, 0, 0, False)) == 0           # C major: already there
    assert K.semitones(a, A.Info(1, 120, 9, 0, 2, False)) == -2          # D major: two down
    assert K.semitones(a, A.Info(1, 120, 9, 0, 7, False)) == 5            # G major: five up, not seven down


@pytest.mark.parametrize("mode, transition", [("mix", "bass_swap"), ("mix", "echo"), ("mashup", "crossfade")])
def test_one_tempo_one_beat_through_the_transition(mode, transition):
    xa, xb = beats(124, secs=40, seed=2), beats(128, root_hz=293.66, minor=False, secs=40, seed=5)
    y, note = K.blend(xa, xb, {"mode": mode, "transition": transition, "bars": 4})
    i = A.analyze(y)
    assert note["bpm"] == 124.0 and i.steady and abs(i.bpm - 124) < 0.5
    gaps = np.diff(i.beats)
    assert np.max(np.abs(gaps - 60 / 124)) < 0.035                        # no beat out of place, transition included
    assert np.max(np.abs(y)) <= 1.0
