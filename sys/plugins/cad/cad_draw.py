# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Line drawings from a 3D model, for patent sheets (ROADMAP 100): no display, no GPU.

OpenSCAD writes each part's geometry (STL: it needs no screen); here the triangles are projected (orthographic) into a
z-buffer that keeps, per pixel, the depth, the face's normal and the part. A line is drawn where the depth jumps (a
silhouette), the part changes, or the surface turns by more than CREASE degrees (an edge) — a cylinder's facets, a few
degrees apart, stay smooth. Black lines on white, as the patent offices ask (EPO Rule 46, 37 CFR 1.84)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

CREASE = 30.0                    # degrees: a turn of the surface beyond this is an edge
VIEWS = {                        # where the viewer stands, looking at the object; z is up on the sheet
    "iso": (1.0, -1.0, 1.0), "front": (0.0, -1.0, 0.0), "top": (0.0, 0.0, 1.0), "side": (1.0, 0.0, 0.0)}


def load_stl(path: Path) -> np.ndarray:
    """(n, 3, 3) triangles of an ASCII or binary STL."""
    data = Path(path).read_bytes()
    if data[:5].lower() == b"solid" and b"facet" in data[:400]:
        v = [list(map(float, line.split()[1:4])) for line in data.decode(errors="replace").splitlines()
             if line.strip().startswith("vertex")]
        return np.asarray(v, dtype=np.float64).reshape(-1, 3, 3)
    n = int.from_bytes(data[80:84], "little")
    rec = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    return rec["v"].astype(np.float64)


def _rot(view: str) -> np.ndarray:
    """Rows: the sheet's right, its up, and the way toward the viewer."""
    v = np.asarray(VIEWS[view], dtype=float)
    v /= np.linalg.norm(v)
    right = np.cross([0.0, 0.0, 1.0], v)
    if np.linalg.norm(right) < 1e-9:                     # seen from above: x right, y up
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    return np.stack([right, np.cross(v, right), v])


def render(parts: list[np.ndarray], view: str, size: int = 1600, frame=None) -> dict:
    """{"lines": uint8 image (0 = line), "part": int map (-1 background), "frame"}. `frame`: the same scale and origin
    as another render (the parts' pictures of one figure must align)."""
    r = _rot(view)
    tris = [p @ r.T for p in parts]
    pts = np.concatenate([t.reshape(-1, 3) for t in tris]) if tris else np.zeros((1, 3))
    if frame is None:
        lo, hi = pts[:, :2].min(0), pts[:, :2].max(0)
        scale = (size * 0.9) / max(hi - lo)
        frame = {"lo": lo - (size / scale - (hi - lo)) / 2, "scale": scale, "size": size}
    lo, scale, size = frame["lo"], frame["scale"], frame["size"]
    depth = np.full((size, size), -np.inf)
    part = np.full((size, size), -1, dtype=np.int32)
    normal = np.zeros((size, size, 3))
    for k, t in enumerate(tris):
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        xy = (t[:, :, :2] - lo) * scale
        xy[:, :, 1] = size - 1 - xy[:, :, 1]                     # image rows go down
        for (a, b, c), z, nn in zip(xy, t[:, :, 2], n):
            x0, x1 = int(max(min(a[0], b[0], c[0]), 0)), int(min(max(a[0], b[0], c[0]) + 1, size - 1))
            y0, y1 = int(max(min(a[1], b[1], c[1]), 0)), int(min(max(a[1], b[1], c[1]) + 1, size - 1))
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-12:
                continue                                          # seen edge-on: its neighbours draw it
            w0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
            w1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
            sub = depth[y0:y1 + 1, x0:x1 + 1]
            win = inside & (zz > sub)
            sub[win] = zz[win]
            part[y0:y1 + 1, x0:x1 + 1][win] = k
            normal[y0:y1 + 1, x0:x1 + 1][win] = nn
    edge = np.zeros((size, size), dtype=bool)
    depth[~np.isfinite(depth)] = -1e9                             # the background: far, and no inf − inf
    # a depth jump beyond what the surface's own slope gives across a pixel is a silhouette (a face seen almost
    # edge-on changes depth fast: not an edge)
    slope = np.minimum(np.hypot(normal[..., 0], normal[..., 1]) / np.maximum(np.abs(normal[..., 2]), 1e-3), 50.0)
    cos = math.cos(math.radians(CREASE))
    for dy, dx in ((0, 1), (1, 0)):
        a, b = (slice(0, size - dy), slice(0, size - dx)), (slice(dy, size), slice(dx, size))
        diff_part = part[a] != part[b]
        both = (part[a] >= 0) & (part[b] >= 0)
        jump = both & (np.abs(depth[a] - depth[b]) > (2.5 + 2 * np.maximum(slope[a], slope[b])) / scale)
        turn = both & ((normal[a] * normal[b]).sum(-1) < cos)
        e = diff_part | jump | turn
        edge[a] |= e
    lines = np.where(edge, 0, 255).astype(np.uint8)
    return {"lines": _thicken(lines), "part": part, "frame": frame}


def _thicken(img: np.ndarray, px: int = 2) -> np.ndarray:
    """Lines px wide: «sufficiently dense and dark, uniformly thick» (EPO Rule 46(2)(b))."""
    out = img.copy()
    for dy in range(px):
        for dx in range(px):
            out[: img.shape[0] - dy, : img.shape[1] - dx] = np.minimum(out[: img.shape[0] - dy, : img.shape[1] - dx],
                                                                     img[dy:, dx:])
    return out


def anchors(part_map: np.ndarray, n: int) -> list[tuple[int, int] | None]:
    """A point well inside each part as drawn (the pixel nearest its centre), where a reference line ends."""
    out = []
    for k in range(n):
        ys, xs = np.nonzero(part_map == k)
        if not len(xs):
            out.append(None)
            continue
        cy, cx = ys.mean(), xs.mean()
        i = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
        out.append((int(xs[i]), int(ys[i])))
    return out
