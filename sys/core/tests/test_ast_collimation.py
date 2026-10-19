# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Collimation read from the stars (owner, 19 Oct): the field of an in-focus frame (a side that swells, a coma tail, the
same elongation everywhere) and the defocused star (the secondary's shadow off the ring's middle, the screws learned,
the turns said). Invented stars, drawn here."""
import math

import numpy as np
import pytest

from aurora import ast_donut as D, ast_stars as S

RNG = np.random.default_rng(7)


def star_field(w=600, h=400, n=260, sigma=lambda x, y: 1.3, e=0.0, angle=0.0, tail=0.0):
    img = np.full((h, w), 100.0)
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(n):
        x, y = RNG.uniform(12, w - 12), RNG.uniform(12, h - 12)
        s = sigma(x, y)
        a, b = s * (1 + e), s * (1 - e)
        c, sn = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        win = (slice(int(y) - 10, int(y) + 11), slice(int(x) - 10, int(x) + 11))
        dx, dy = xx[win] - x, yy[win] - y
        u, v = dx * c + dy * sn, -dx * sn + dy * c
        img[win] += 3000 * np.exp(-0.5 * (u * u / (a * a) + v * v / (b * b)))
        if tail:                                            # a faint tail on one side: coma
            img[win] += 900 * np.exp(-0.5 * (((dx - tail * s) ** 2 + dy ** 2) / (1.6 * s) ** 2))
    return img + RNG.normal(0, 5, img.shape)


def analyse(img):
    st = S.stars(img.astype(np.float32), 1e9)
    f = S.field(st, img.shape[1], img.shape[0], 1.0)
    f["verdict"] = S.verdict(f)
    return f


def test_an_even_field_is_said_even():
    f = analyse(star_field())
    assert f["stars"] > 150 and abs(f["fwhm_median"] - 2.3548 * 1.3) < 0.25 and f["e_median"] < 0.08
    assert [v["code"] for v in f["verdict"]] == ["ok"]


def test_a_side_that_swells_is_found_with_its_side():
    f = analyse(star_field(sigma=lambda x, y: 1.1 + 1.0 * (600 - x) / 600))     # worse to the left
    codes = [v["code"] for v in f["verdict"]]
    assert "one_side" in codes and S.way(f["worse_toward_deg"]) == "sinistra"


def test_the_same_elongation_everywhere_without_a_tail_is_tracking():
    f = analyse(star_field(e=0.25, angle=30))
    assert abs(f["one_direction_deg"] - 30) < 6 and "tracking" in [v["code"] for v in f["verdict"]]
    assert "coma" not in [v["code"] for v in f["verdict"]]


def test_a_tail_on_one_side_everywhere_is_coma_not_tracking():
    f = analyse(star_field(tail=1.8))
    codes = [v["code"] for v in f["verdict"]]
    assert "coma" in codes and "tracking" not in codes and S.way(f["tail_deg"]) == "destra"


def donut(off=(0.0, 0.0), w=320, h=240, r=40, hole=0.4, at=None):
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = at or (w / 2, h / 2)
    ring = (np.hypot(xx - cx, yy - cy) <= r) & (np.hypot(xx - cx - off[0] * r, yy - cy - off[1] * r) > hole * r)
    return 50 + 2000 * ring.astype(float) + RNG.normal(0, 4, (h, w))


def test_the_shadow_off_the_middle_is_measured():
    m = D.measure(donut((0.08, -0.05)))
    assert abs(m["off_x"] - 0.08) < 0.01 and abs(m["off_y"] + 0.05) < 0.01 and abs(m["ring"][2] - 40) < 1.5
    assert D.measure(donut())["offset"] < 0.01


@pytest.mark.parametrize("img,word", [(np.full((100, 100), 50.0), "uniforme"),
                                      (None, "ombra")])
def test_what_cannot_be_measured_is_said(img, word):
    if img is None:                                          # a ring without a hole: not defocused enough
        yy, xx = np.mgrid[0:200, 0:200]
        img = 50 + 2000 * (np.hypot(xx - 100, yy - 100) <= 30)
    assert word in D.measure(img)["error"]


def test_screws_learned_then_the_turns_that_centre_the_shadow():
    # two screws: an eighth clockwise of «in basso a destra» moves the shadow +0.02 in x; «in alto» moves it −0.02 in y
    st = {}
    out, st = D.step(D.measure(donut((0.0, 0.0))), st)
    out, st = D.step(D.measure(donut((0.02, 0.0))), st, learn=("in basso a destra", 1))
    assert "in basso a destra" in out["learned"]
    out, st = D.step(D.measure(donut((0.02, -0.04))), st, learn=("in alto", 2))
    out, st = D.step(D.measure(donut((0.06, 0.04))), st)
    plan = {t["screw"]: t["eighths"] for t in out["turns"]}
    # exactly: −3 eighths and +2; each measure's own noise moves a learned screw by some percent
    assert not out["done"] and abs(plan["in basso a destra"] + 3) < 0.6 and abs(plan["in alto"] - 2) < 0.4
    assert "Gira la vite in basso a destra di" in out["say"] and "in senso antiorario" in out["say"]


def test_collimated_or_off_centre_is_said_and_nothing_to_turn():
    out, _ = D.step(D.measure(donut((0.01, 0.0))), {})
    assert out["done"] and "collimato" in out["say"]
    out, _ = D.step(D.measure(donut((0.1, 0.0), at=(60, 60))), {})
    assert not out["done"] and "centrala" in out["say"]


def test_a_night_says_a_side_that_never_changes_even_when_small():
    row = {"file": "2026-01-10_20-00-00_x.xisf", "stars": 900, "fwhm_median": 5.0, "worse_toward_deg": 180, "gradient": 0.2,
           "gradient_err": 0.05, "e_median": 0.1, "tail": 0.003, "verdict": [{"code": "ok", "text": ""}]}
    n = {"date": "2026-01-10", "frames": 4, "scale_known": True, "rows": [row] * 4, "codes": {"ok": 4},
         "worse_side": None, "constant": {"side": "sinistra", "frames": 4, "of": 4, "gradient": [0.2, 0.2], "pct": 4.0}}
    t = S.night_text(n)
    assert "Lo stesso lato peggiore in 4 pose su 4: sinistra" in t and "non c'è" in t and "campo uniforme" in t
