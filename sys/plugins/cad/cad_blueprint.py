# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A dimensioned technical drawing (a «blueprint», ROADMAP 100): not a patent sheet — it carries measures, a title
block and a parts list. A4 landscape at 300 dpi; the three views in one scale, laid out by first-angle projection
(ISO 128-30, the European use: the top view under the front view, the left view on the right of it); overall
dimensions with extension lines and arrows (ISO 129-1), in millimetres; an isometric view; the parts list."""
from __future__ import annotations

import math
import time

import numpy as np
from PIL import Image, ImageDraw

import cad_draw
from cad_sheets import MM, font

PAGE = (round(297 * MM), round(210 * MM))            # A4 landscape
BORDER = round(10 * MM)
TEXT = round(3.5 * MM)                               # ISO 3098: 3.5 mm lettering


def _bbox(tris: list[np.ndarray], view: str) -> tuple[np.ndarray, np.ndarray]:
    r = cad_draw._rot(view)
    pts = np.concatenate([t.reshape(-1, 3) for t in tris]) @ r.T
    return pts[:, :2].min(0), pts[:, :2].max(0)


def _view(tris, view: str, scale: float) -> tuple[Image.Image, tuple[float, float]]:
    """The view's line drawing at `scale` pixels a millimetre, cropped to its outline; (image, its size in mm)."""
    lo, hi = _bbox(tris, view)
    pad = 20
    size = int(max(hi - lo) * scale) + 2 * pad
    frame = {"lo": lo - pad / scale, "scale": scale, "size": size}
    r = cad_draw.render(tris, view, size, frame)
    ys, xs = np.nonzero(r["lines"] < 128)
    img = r["lines"][ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return Image.fromarray(img), tuple((hi - lo).round(1))


def _arrow(d: ImageDraw.ImageDraw, a, b) -> None:
    """A dimension line from a to b with closed arrowheads at both ends."""
    d.line([a, b], fill=0, width=3)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for p, s in ((a, 1), (b, -1)):
        tip = [(p[0] + s * 28 * math.cos(ang + k * 0.28), p[1] + s * 28 * math.sin(ang + k * 0.28)) for k in (-1, 1)]
        d.polygon([p, *tip], fill=0)


def _dims(d, f, box, w_mm: float, h_mm: float) -> None:
    """The overall width under the view and the height on its right, with extension lines."""
    x0, y0, x1, y1 = box
    off = 70
    for x in (x0, x1):
        d.line([(x, y1 + 12), (x, y1 + off + 20)], fill=0, width=2)
    _arrow(d, (x0, y1 + off), (x1, y1 + off))
    t = f"{w_mm:g}"
    d.text(((x0 + x1) / 2 - d.textlength(t, font=f) / 2, y1 + off - TEXT - 12), t, font=f, fill=0)
    for y in (y0, y1):
        d.line([(x1 + 12, y), (x1 + off + 20, y)], fill=0, width=2)
    _arrow(d, (x1 + off, y0), (x1 + off, y1))
    t = f"{h_mm:g}"
    lab = Image.new("L", (int(d.textlength(t, font=f)) + 4, TEXT + 10), 255)
    ImageDraw.Draw(lab).text((2, 0), t, font=f, fill=0)
    d._image.paste(lab.rotate(90, expand=True), (int(x1 + off + 10), int((y0 + y1) / 2 - lab.width / 2)))


def sheet(assembled: list[np.ndarray], parts: list[dict], title: str, project: str) -> Image.Image:
    page = Image.new("L", PAGE, 255)
    d = ImageDraw.Draw(page)
    f, small = font(TEXT), font(round(2.5 * MM))
    d.rectangle([BORDER, BORDER, PAGE[0] - BORDER, PAGE[1] - BORDER], outline=0, width=5)
    # the views' common scale: front + side across, front + top down, inside the left 62% of the sheet
    lf, hf = _bbox(assembled, "front")
    ls, hs = _bbox(assembled, "left")
    lt, ht = _bbox(assembled, "top")
    area_w, area_h = PAGE[0] * 0.62 - 2 * BORDER, PAGE[1] - 2 * BORDER - round(60 * MM)
    need_w = (hf - lf)[0] + (hs - ls)[0]
    need_h = (hf - lf)[1] + (ht - lt)[1]
    px = min((area_w - 520) / need_w, (area_h - 420) / need_h)      # pixels a millimetre on the sheet
    mm_px = MM                                                       # pixels a real millimetre of paper
    ratio = px / mm_px                                               # sheet mm per model mm
    std = [s for s in (5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01) if s <= ratio]
    ratio = std[0] if std else ratio
    px = ratio * mm_px
    views = {v: _view(assembled, v, px) for v in ("front", "top", "left")}
    x0, y0 = BORDER + 120, BORDER + 140
    fimg, fdim = views["front"]
    places = {"front": (x0, y0), "top": (x0, y0 + fimg.height + 240), "left": (x0 + fimg.width + 300, y0)}
    for v, (x, y) in places.items():
        img, (w_mm, h_mm) = views[v]
        page.paste(img, (int(x), int(y)))
        _dims(d, f, (x, y, x + img.width, y + img.height), w_mm, h_mm)
        names = {"front": "Vista frontale / Front", "top": "Vista dall'alto / Top", "left": "Vista da sinistra / Left"}
        d.text((x, y - TEXT - 30), names[v], font=small, fill=0)
    iso = cad_draw.render(assembled, "iso", 900)
    ys, xs = np.nonzero(iso["lines"] < 128)
    iso_img = Image.fromarray(iso["lines"][ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    iso_img.thumbnail((int(PAGE[0] * 0.30), int(PAGE[1] * 0.40)))
    page.paste(iso_img, (int(PAGE[0] * 0.66), BORDER + 140))
    # the title block and the parts list, bottom right (ISO 7200's fields that apply)
    tb_w, row = round(180 * MM), round(7 * MM)
    tx, ty = PAGE[0] - BORDER - tb_w, PAGE[1] - BORDER - row * (5 + len(parts))
    d.rectangle([tx, ty, PAGE[0] - BORDER, PAGE[1] - BORDER], outline=0, width=4)
    rows = [("Pos.", "Denominazione / Name", "Dimensioni mm (L × P × H)")]
    rows += [(str(p["sign"]), p["name"][:40], " × ".join(f"{v:g}" for v in p["size_mm"])) for p in parts]
    for i, (a, b, c) in enumerate(rows):
        y = ty + i * row
        d.line([(tx, y + row), (PAGE[0] - BORDER, y + row)], fill=0, width=2)
        for col, (text, w) in enumerate(((a, 0), (b, 0.12), (c, 0.62))):
            d.text((tx + 12 + w * tb_w, y + 10), text, font=small, fill=0)
    y = ty + len(rows) * row
    fields = [f"{title}  ·  progetto {project}", f"Scala / Scale 1:{1 / ratio:g}" if ratio < 1 else f"Scala / Scale {ratio:g}:1",
              f"Unità / Units: mm  ·  Proiezione del primo diedro (ISO 128-30)  ·  {time.strftime('%d/%m/%Y')}  ·  Foglio 1/1"]
    for i, text in enumerate(fields):
        d.text((tx + 12, y + 10 + i * row), text, font=small if i else f, fill=0)
    return page
