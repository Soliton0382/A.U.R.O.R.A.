# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The polar alignment a night really had, from its guiding (owner, 19 Oct): a drift made from a known error is found
again with its hour angle, a night too short says a lower bound, settling is left out, the calibration's squareness.
Invented drifts and frames."""
import math

from aurora import ast_polar as P


def drift(e_arcmin, toward_h, ha):
    return P.PER_ARCMIN * e_arcmin * math.sin((ha - toward_h) * math.pi / 12)


def test_a_known_error_is_found_again():
    pts = [{"ha": h / 4, "rate": drift(4.0, 2.0, h / 4)} for h in range(-12, 12)]
    f = P.fit(pts)
    assert f["both"] and abs(f["arcmin"] - 4.0) < 0.05 and abs(f["toward_h"] - 2.0) < 0.05 and f["err_arcmin"] < 0.05


def test_noise_makes_the_error_bar_not_the_answer():
    pts = [{"ha": h / 4, "rate": drift(2.0, -3.0, h / 4) + (0.3 if h % 2 else -0.3)} for h in range(-8, 8)]
    f = P.fit(pts)
    assert abs(f["arcmin"] - 2.0) < 1.0 and f["err_arcmin"] > 0.3


def test_a_night_on_one_hour_angle_gives_only_a_lower_bound():
    pts = [{"ha": 0.1 * i, "rate": 0.525} for i in range(6)]           # 2′ seen at the meridian
    f = P.fit(pts)
    assert not f["both"] and f["at_least_arcmin"] == 2.0
    assert P.fit(pts[:2]) is None


def test_windows_sum_the_pulses_and_leave_settling_out():
    rows = [{"t": float(t), "dec_ms": 100 if t % 4 == 0 else 0} for t in range(0, 2000)]   # north 100 ms every 4 s
    skip = {i for i, r in enumerate(rows) if 900 <= r["t"] < 960}
    w = P.windows(rows, skip, 7.5, 1.0)
    # 7.5″/s × 0.1 s every 4 s = 11.25″/min north: the sky drifted south as fast
    assert len(w) == 2 and abs(w[0]["rate"] + 11.25) < 0.1 and w[0]["ha"] > 1.0
    assert w[0]["frames"] < w[1]["frames"]                        # the settling was in the first, its rate still right
    assert P.windows(rows, set(), 7.5, None) == []


def test_squareness_of_the_calibration_and_the_words():
    cal = [{"axis": "RA", "angle": -156.6, "rate": 2.2}, {"axis": "DEC", "angle": -64.9, "rate": 2.3}]
    assert P.square(cal) == 1.7
    n = {"night": "2026-01-01", "fit": {"both": True, "arcmin": 3.1, "err_arcmin": 1.7, "windows": 8, "span_h": 2.0},
         "assistant_arcmin": 7.6, "square_deg": 1.7}
    t = P.text(n)
    assert "3.1′ ± 1.7′" in t and "7.6′" in t and "1.7°" in t and "✅" in t
