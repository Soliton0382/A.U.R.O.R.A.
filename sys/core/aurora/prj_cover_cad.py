# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖼️ A CAD model's cover made on the server (prj_cover, ROADMAP N43; owner, 23 Oct: «miniature ci sono (non per
tutti purtroppo)»): a project whose only picture is its model gets one before the realistic view is ever opened.

The parts' STL (part_<k>.stl) seen from the same side as the page's first view, each in its material (prj_view),
lit by a key and a fill light; triangles painted far to near at twice the size, then made smaller (smooth edges).
Not the page's renderer (no shadows, no reflections): the realistic view replaces it the first time it is drawn.
"""
from __future__ import annotations

import io
import math
import struct
from pathlib import Path

import numpy as np

MAX_TRI = 60_000


def load_stl(f: Path) -> np.ndarray:
    """The triangles of an STL, text or binary: (n, 3, 3) in mm."""
    raw = f.read_bytes()
    if len(raw) >= 84:
        n = struct.unpack_from("<I", raw, 80)[0]
        if 84 + 50 * n == len(raw) and b"facet" not in raw[:300]:
            rec = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
                                count=n, offset=84)
            return rec["v"].astype(np.float64)
    vals = [float(x) for line in raw.decode("ascii", "replace").splitlines() if line.strip().startswith("vertex")
            for x in line.split()[1:4]]
    a = np.array(vals[: len(vals) - len(vals) % 9], dtype=np.float64)
    return a.reshape(-1, 3, 3)


def render(folder: Path, parts: list[dict], looks: dict, w: int = 960, h: int = 540) -> bytes | None:
    """The model in folder as a JPEG, or None when it has no part to draw."""
    from PIL import Image, ImageDraw
    tris, cols = [], []
    for k, p in enumerate(parts):
        f = folder / f"part_{k}.stl"
        if not f.is_file():
            continue
        t = load_stl(f)
        if not len(t):
            continue
        base, metal, rough = looks.get(p.get("material") or "", looks["plastic_light"])
        tris.append(t)
        cols.append(np.repeat([[*base, metal, rough]], len(t), axis=0))
    if not tris:
        return None
    t, c = np.concatenate(tris), np.concatenate(cols)
    if len(t) > MAX_TRI:                                    # a very fine model: every n-th triangle is enough here
        step = math.ceil(len(t) / MAX_TRI)
        t, c = t[::step], c[::step]
    # the page's first view: turned −0.9 rad about z, looked at from 0.55 rad above (z up, OpenSCAD's)
    yaw, pitch = -0.9, 0.55
    eye = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    right = np.cross([0, 0, 1], eye)
    right /= np.linalg.norm(right)
    up = np.cross(eye, right)
    centre = (t.reshape(-1, 3).max(0) + t.reshape(-1, 3).min(0)) / 2
    p = t - centre
    x, y, depth = p @ right, p @ up, p @ eye
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    n[(n @ eye) < 0] *= -1                                  # the side that faces the eye
    key = np.array([0.55, -0.55, 0.83]); key /= np.linalg.norm(key)
    fill = np.array([-0.44, 0.44, 0.45]); fill /= np.linalg.norm(fill)
    base, metal, rough = c[:, :3], c[:, 3:4], c[:, 4:5]
    dif = np.clip(n @ key, 0, 1)[:, None] * 0.85 + np.clip(n @ fill, 0, 1)[:, None] * 0.25 + 0.08
    half = (key + eye) / np.linalg.norm(key + eye)
    spec = np.clip(n @ half, 0, 1)[:, None] ** (2 + 60 * (1 - rough)) * (0.25 + 0.75 * metal)
    col = base * dif * (1 - 0.6 * metal) + base * metal * (0.25 + 0.5 * np.clip(n[:, 2:3], 0, 1)) + spec
    col = np.clip(col / (1 + col), 0, 1) ** (1 / 2.2) * 1.05               # tone map, screen gamma
    S = 2
    W, H = w * S, h * S
    span = max(x.max() - x.min(), (y.max() - y.min()) * W / H) or 1.0
    scale = 0.82 * W / span
    px, py = W / 2 + x * scale, H / 2 - y * scale
    img = Image.new("RGB", (W, H))
    grad = np.linspace(0, 1, H)[:, None]
    bg = (np.array([46, 47, 52]) * (1 - grad) + np.array([22, 23, 26]) * grad).astype(np.uint8)
    img.paste(Image.fromarray(np.repeat(bg[:, None, :], W, axis=1).reshape(H, W, 3)))
    d = ImageDraw.Draw(img)
    for i in np.argsort(depth.mean(1)):                     # far to near
        rgb = tuple(int(255 * min(v, 1)) for v in col[i])
        d.polygon([(px[i, j], py[i, j]) for j in range(3)], fill=rgb, outline=rgb)
    img = img.resize((w, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()
