# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The CAD plugin's drawings (ROADMAP 100): its own renderer (no display), the patent sheets' rules."""
import sys
from pathlib import Path

import numpy as np

CAD = Path(__file__).resolve().parents[2] / "plugins" / "cad"
sys.path.insert(0, str(CAD))
import cad_draw as D  # noqa: E402
import cad_sheets as S  # noqa: E402


def _box(x0, y0, z0, x1, y1, z1):
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return np.array([[v[a], v[b], v[c]] for f in faces for a, b, c in ((f[0], f[1], f[2]), (f[0], f[2], f[3]))])


def test_a_box_drawn_as_lines_with_its_parts_and_anchors():
    base, block = _box(0, 0, 0, 60, 40, 8), _box(20, 10, 30, 40, 30, 50)
    r = D.render([base, block], "iso", 400)
    dark = (r["lines"] < 128).mean()
    assert 0.005 < dark < 0.2                                  # lines, not filled shapes
    a = D.anchors(r["part"], 2)
    assert a[0] and a[1] and a[1][1] < a[0][1]                 # the upper block is drawn higher on the sheet
    top = D.render([base], "top", 400)["lines"]
    ys, xs = np.nonzero(top < 128)
    assert abs((xs.max() - xs.min()) / (ys.max() - ys.min()) - 60 / 40) < 0.05   # from above: 60 × 40, true shape


def test_a_cylinder_s_facets_are_not_edges():
    import math
    n, r, h = 64, 10, 30
    tris = []
    for i in range(n):
        a, b = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        p0, p1 = (r * math.cos(a), r * math.sin(a)), (r * math.cos(b), r * math.sin(b))
        tris += [[(*p0, 0), (*p1, 0), (*p1, h)], [(*p0, 0), (*p1, h), (*p0, h)]]
    img = D.render([np.array(tris, float)], "front", 400)["lines"]
    row = img[200] < 128                                       # across the middle: the two outlines only
    assert 2 <= np.count_nonzero(np.diff(row.astype(int)) == 1) <= 2


def test_the_sheets_follow_the_patent_rules(tmp_path):
    from PIL import Image
    fig = Image.new("L", (800, 600), 255)
    pages = [S.sheet([(fig, "Fig. 1")], 1, 2), S.sheet([(fig, "Fig. 2"), (fig, "Fig. 3")], 2, 2)]
    assert pages[0].size == S.A4 == (2480, 3508)              # A4 at 300 dpi
    px = np.asarray(pages[0])
    m = S.MARGIN
    assert (px[: m["top"]] == 255).all() and (px[:, : m["left"]] == 255).all()       # nothing in the margins
    assert (px[:, -m["right"]:] == 255).all() and (px[-m["bottom"]:] == 255).all()
    assert (px < 128).any()                                   # «1/2» and «Fig. 1» are on it
    S.pdf(pages, tmp_path / "d.pdf")
    assert (tmp_path / "d.pdf").read_bytes()[:4] == b"%PDF"
    assert S.SIGN_H >= round(3.2 * S.MM) and m["top"] >= round(25 * S.MM) and m["right"] >= round(15 * S.MM)
