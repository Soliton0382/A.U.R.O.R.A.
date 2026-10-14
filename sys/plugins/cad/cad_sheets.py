# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Patent drawing sheets from the line drawings (ROADMAP 100), as the offices ask for them:

  EPO, Rule 46 EPC: A4; margins at least top 2.5 cm, left 2.5 cm, right 1.5 cm, bottom 1 cm, no frame; black lines,
  no colour; figures numbered «Fig. 1» in Arabic numerals; sheets numbered «1/3» at the top centre, not in the margin;
  reference signs at least 0.32 cm high, joined to their part by a thin line; no text but what is indispensable.
  (USPTO 37 CFR 1.84 asks the same in spirit, with its own margins: top 2.5 cm, left 2.5, right 1.5, bottom 1.0 cm
  on A4 — the same numbers.)

Every sheet is a 300 dpi A4 bitmap; the PDF is those pages (Pillow), each 210 × 297 mm."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DPI = 300
A4 = (2480, 3508)                                    # 210 × 297 mm at 300 dpi
MM = DPI / 25.4
MARGIN = {"top": round(25 * MM), "left": round(25 * MM), "right": round(15 * MM), "bottom": round(10 * MM)}
SIGN_H = round(4.0 * MM)                             # reference signs 4 mm high (≥ 3.2 mm)
FIG_H = round(5.0 * MM)
FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/arial.ttf")


def font(px: int) -> ImageFont.FreeTypeFont:
    for f in FONTS:
        if Path(f).is_file():
            return ImageFont.truetype(f, px)
    return ImageFont.load_default(size=px)


def crop(lines: np.ndarray, pad: int = 12) -> tuple[np.ndarray, tuple[int, int]]:
    """The drawing without its empty border; (image, the offset taken away) to move the anchors with it."""
    ys, xs = np.nonzero(lines < 128)
    if not len(xs):
        return lines, (0, 0)
    y0, x0 = max(ys.min() - pad, 0), max(xs.min() - pad, 0)
    return lines[y0:ys.max() + pad, x0:xs.max() + pad], (x0, y0)


def label(img: np.ndarray, anchors: list[tuple[int, int] | None], signs: list[int]) -> Image.Image:
    """Reference signs beside the drawing, each joined to a point inside its part by a thin straight line."""
    h, w = img.shape
    room = 3 * SIGN_H
    canvas = Image.new("L", (w + 2 * room, h), 255)
    canvas.paste(Image.fromarray(img), (room, 0))
    d, f = ImageDraw.Draw(canvas), font(SIGN_H)
    used: list[int] = []
    for a, s in sorted(((a, s) for a, s in zip(anchors, signs) if a), key=lambda x: x[0][1]):
        x, y = a[0] + room, a[1]
        left = a[0] < w / 2
        while any(abs(y - u) < SIGN_H * 1.4 for u in used):     # never two signs on one another
            y += SIGN_H
        used.append(y)
        tx = room // 4 if left else w + room + room // 6
        tw = d.textlength(str(s), font=f)
        d.text((tx, y - SIGN_H // 2), str(s), font=f, fill=0)
        start = (tx + tw + 8, y) if left else (tx - 8, y)
        d.line([start, (x, a[1])], fill=0, width=3)
    return canvas


# each office's drawing sheets (patent/rules.py has the sources): margins in mm, the paper
OFFICES = {"EP": ({"top": 25, "left": 25, "right": 15, "bottom": 10}, (210.0, 297.0)),
           "IT": ({"top": 25, "left": 25, "right": 25, "bottom": 25}, (210.0, 297.0)),
           "US": ({"top": 25, "left": 25, "right": 15, "bottom": 10}, (215.9, 279.4))}


def sheet(figures: list[tuple[Image.Image, str]], number: int, total: int, office: str = "EP") -> Image.Image:
    """One page: the figures stacked, each scaled to fit with its «Fig. N» under it; «n/total» at the top."""
    mm, paper = OFFICES[office]
    size = (round(paper[0] * MM), round(paper[1] * MM))
    page = Image.new("L", size, 255)
    d = ImageDraw.Draw(page)
    top, left = round(mm["top"] * MM), round(mm["left"] * MM)
    width, height = size[0] - left - round(mm["right"] * MM), size[1] - top - round(mm["bottom"] * MM)
    mark = f"{number}/{total}"
    fm = font(FIG_H)
    d.text((left + width / 2 - d.textlength(mark, font=fm) / 2, top), mark, font=fm, fill=0)
    y = top + 2 * FIG_H
    room = (height - 2 * FIG_H) / len(figures)
    for img, caption in figures:
        box_h = room - 2.4 * FIG_H
        s = min(width / img.width, box_h / img.height, 1.6)
        im = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
        im = im.point(lambda v: 0 if v < 160 else 255)            # black and white only, no greys
        page.paste(im, (int(left + (width - im.width) / 2), int(y + (box_h - im.height) / 2)))
        cy = y + box_h + 0.6 * FIG_H
        d.text((left + width / 2 - d.textlength(caption, font=fm) / 2, cy), caption, font=fm, fill=0)
        y += room
    return page


def pdf(pages: list[Image.Image], path: Path) -> None:
    pages[0].save(path, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
