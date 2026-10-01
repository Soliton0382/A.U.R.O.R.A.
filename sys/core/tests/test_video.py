# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import subprocess

import pytest

from aurora import kno_video as V


def test_moments_are_the_start_the_scenes_and_even_fill():
    even = V.pick_times([], 60, 4)
    assert len(even) == 4 and even[0] == 0.0 and even[-1] == 52.5           # the start, then spread to the end
    t = V.pick_times([10.0, 10.4, 30.0], 60, 6)
    assert t[0] == 0.0 and 10.0 in t and 30.0 in t and len(t) <= 6
    assert all(b - a >= 1.0 for a, b in zip(t, t[1:]))                      # no two moments within a second
    cut = V.pick_times([7.0, 14.0], 21, 12)
    assert 7.0 in cut and 14.0 in cut                                        # a cut is never replaced by a filler
    many = V.pick_times([float(i) for i in range(1, 100)], 100, 12)
    assert len(many) == 12 and many[0] == 0.0 and many[-1] > 90               # spread over the whole video
    assert V.pick_times([], 0.5, 12) == [0.0]


def test_cuts_are_peaks_even_between_colours_of_the_same_brightness():
    flat = [(i / 8, 0.00002) for i in range(160)]
    assert V.cuts(flat + [(7.0, 0.0858), (14.0, 0.0867)]) == [7.0, 14.0]          # M48: blue → green → red
    assert V.cuts(flat + [(3.0, 0.45)]) == [3.0]
    busy = [(i / 8, 0.12) for i in range(160)]                                       # a moving camera: no cut everywhere
    assert V.cuts(busy) == [] and V.cuts([]) == []


def test_passages_keep_times_and_split_the_transcript():
    w = {"duration": 125.0, "width": 1920, "height": 1080, "watched_s": 125.0, "frames": [0.0, 60.0], "audio": True,
         "visual": "[00:00] un prato\n[01:00] una casa", "speech": [(i * 5.0, i * 5.0 + 5, "parola " * 40) for i in range(20)]}
    p = V.passages(w, "gita.mp4")
    assert p[0].startswith("VIDEO «gita.mp4»: 02:05 (1920x1080)") and "[01:00] una casa" in p[0]
    assert len(p) > 2 and all(len(x) < 1700 for x in p[1:]) and "[00:05–00:10]" in p[1]
    silent = V.passages({**w, "speech": []}, "muto.mp4")
    assert "no clear speech" in silent[-1]


def test_a_real_file_is_probed_and_its_scenes_found(tmp_path):
    f = tmp_path / "three.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=red:s=320x240:d=3",
                    "-f", "lavfi", "-i", "color=blue:s=320x240:d=3", "-f", "lavfi", "-i", "color=green:s=320x240:d=3",
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", str(f)], check=True)
    info = V.probe(f)
    assert 8.5 < info["duration"] < 9.5 and info["width"] == 320 and not info["audio"]
    scenes = V.scene_changes(f, 9)
    assert len(scenes) == 2 and abs(scenes[0] - 3) < 0.2 and abs(scenes[1] - 6) < 0.2
    assert V.frame(f, 4.0, 1024)[:2] == b"\xff\xd8"                            # a JPEG
    with pytest.raises(ValueError):
        V.probe(tmp_path / "missing.mp4")
