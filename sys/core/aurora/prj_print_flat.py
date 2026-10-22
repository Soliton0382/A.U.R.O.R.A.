# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖨️ A model's parts laid flat and arranged on the bed (ROADMAP N41, the «later»: «parts laid flat and arranged on
the bed, 3MF with units»).

Each part is turned so that its largest flat face (the triangles of one direction, their areas summed) rests on the
bed (z = 0), and moved to the origin. Then the parts are set in rows on beds of the printer's size, as many beds as
they need; a part larger than the bed is said, not shrunk. Out: each part's STL (binary, mm) and one 3MF per bed
(unit millimeter), which slicers open as a ready plate.
"""
from __future__ import annotations

import io
import struct
import zipfile

import numpy as np

GAP = 5.0                                   # mm between two parts on the bed


def _turn(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The rotation that takes unit vector a onto unit vector b."""
    v, c = np.cross(a, b), float(np.dot(a, b))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:                                         # opposite: half a turn about any perpendicular
        p = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
        p /= np.linalg.norm(p)
        return 2 * np.outer(p, p) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def lay_flat(tri: np.ndarray) -> np.ndarray:
    """The part (n, 3, 3) resting on its largest flat face, its corner at the origin (x, y ≥ 0, z ≥ 0)."""
    if not len(tri):
        return tri
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(n, axis=1)
    keep = area > 1e-12
    unit = n[keep] / area[keep, None]
    keys = np.round(unit, 3)
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    sums = np.bincount(inv.ravel(), weights=area[keep])
    down = uniq[int(np.argmax(sums))]
    down = down / np.linalg.norm(down)
    r = _turn(down, np.array([0.0, 0.0, -1.0]))
    out = tri @ r.T
    return out - out.reshape(-1, 3).min(0)


def arrange(parts: list[np.ndarray], bed: tuple[float, float]) -> tuple[list[np.ndarray], list[int], list[int]]:
    """The laid-flat parts set on as many beds as they need, deepest first, each in the first place it fits (shelves:
    a row of a bed, else a new row, else a new bed — a small part fills the room beside a large one): each part where
    it lies on its bed, the bed it is on (0, 1, …), and which parts are larger than a bed (set alone on their own)."""
    size = [np.ptp(p.reshape(-1, 3), axis=0) if len(p) else np.zeros(3) for p in parts]
    placed: list[np.ndarray] = list(parts)
    plate, too_big = [0] * len(parts), []
    beds: list[list[list[float]]] = []                       # per bed its rows: [y, depth, x used]
    for i in sorted(range(len(parts)), key=lambda i: -float(size[i][1])):
        if not len(parts[i]):
            continue
        w, d = float(size[i][0]), float(size[i][1])
        spot = None
        if w + 2 * GAP > bed[0] or d + 2 * GAP > bed[1]:
            too_big.append(i)
            beds.append([[GAP, d, GAP + w + GAP]])
            spot = (len(beds) - 1, GAP, GAP)
        for b, rows in enumerate(beds if spot is None else []):
            for row in rows:
                if d <= row[1] and row[2] + w + GAP <= bed[0]:
                    spot = (b, row[2], row[0])
                    row[2] += w + GAP
                    break
            if spot is None:
                y = rows[-1][0] + rows[-1][1] + GAP
                if y + d + GAP <= bed[1]:
                    rows.append([y, d, GAP + w + GAP])
                    spot = (b, GAP, y)
            if spot:
                break
        if spot is None:
            beds.append([[GAP, d, GAP + w + GAP]])
            spot = (len(beds) - 1, GAP, GAP)
        plate[i], placed[i] = spot[0], parts[i] + np.array([spot[1], spot[2], 0.0])
    return placed, plate, too_big


def stl_bytes(tri: np.ndarray, name: str = "part") -> bytes:
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    head = name.encode("ascii", "replace")[:80].ljust(80, b" ")
    rec = np.zeros(len(tri), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    rec["n"], rec["v"] = n, tri
    return head + struct.pack("<I", len(tri)) + rec.tobytes()


def three_mf(parts: list[tuple[str, np.ndarray]]) -> bytes:
    """One 3MF (unit millimeter) with every part as an object placed where it lies."""
    objs, items = [], []
    for k, (name, tri) in enumerate(parts, start=1):
        if not len(tri):
            continue
        verts, idx = np.unique(np.round(tri.reshape(-1, 3), 4), axis=0, return_inverse=True)
        idx = idx.reshape(-1, 3)
        v = "".join(f'<vertex x="{a:.4f}" y="{b:.4f}" z="{c:.4f}"/>' for a, b, c in verts)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in idx if len({a, b, c}) == 3)
        safe = name.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
        objs.append(f'<object id="{k}" type="model" name="{safe}"><mesh><vertices>{v}</vertices>'
                    f'<triangles>{t}</triangles></mesh></object>')
        items.append(f'<item objectid="{k}"/>')
    model = ('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="it-IT" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>' + "".join(objs)
             + "</resources><build>" + "".join(items) + "</build></model>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/'
                   'vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/'
                   'vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" '
                   'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", model)
    return buf.getvalue()
