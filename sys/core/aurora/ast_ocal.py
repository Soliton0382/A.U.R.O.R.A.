# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 A Newtonian's collimation read from a picture of the collimating camera (owner, 19 Oct: «procedi con il secondario
dalla foto dell'OCAL… una tab specifica nella sezione astro dedicata alla collimazione»). A screenshot of its program
or a phone's picture of the screen; the circles the program draws and the screen's moiré are smoothed away. Read only.

What is found, from the light itself (never from the circles the person placed):
  the secondary     the bright disk (the primary's light filling the secondary), its edge fitted with a circle, outliers
                    such as a baffle's screw left out, and with an ellipse: how round it looks (axis ratio, with its
                    uncertainty by bootstrap) — a secondary turned or tilted wrong looks oval
  its shadow        the dark disk inside (the secondary seen in the primary): reported, never judged — with the offset a
                    fast Newtonian's secondary has, its shadow LOOKS off the middle and should
  the primary       the collimator's reflection (the ring inside the shadow) and the primary's centre spot (the dark mark
                    in it): concentric when the primary points at the focuser — their offset, in the secondary's radius
  the drawtube      the outer edge of the light, only when the whole circle is in the picture
A picture places to a few pixels: the verdict is «within what a picture shows», and the stars decide (ast_donut,
ast_stars). Directions are the picture's (right, down…), as the person sees the screen."""
from __future__ import annotations

import base64
import io
import math

import numpy as np
from scipy import ndimage

SIDES = (900, 1100, 1300)         # the picture is worked at these sizes (the long side); their spread is the error
ROUND_OK = 0.99                   # axis ratio of the secondary's outline: round enough
SPOT_OK = 0.03                    # centre spot off the collimator's reflection, × the secondary's radius


def _circle(ys, xs):
    A = np.stack([xs, ys, np.ones_like(xs)], 1).astype(np.float64)
    b = (xs.astype(np.float64) ** 2 + ys.astype(np.float64) ** 2)
    (p, q, c), *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = p / 2, q / 2
    return float(cx), float(cy), float(math.sqrt(max(c + cx * cx + cy * cy, 0.0)))


def _robust(ys, xs, rounds: int = 8):
    """A circle through edge points with the far ones dropped (a screw, a vane): (cx, cy, r, kept, mask)."""
    keep = np.ones(len(xs), bool)
    for _ in range(rounds):
        cx, cy, r = _circle(ys[keep], xs[keep])
        d = np.abs(np.hypot(xs - cx, ys - cy) - r)
        keep = d < max(1.5, 2.5 * float(np.median(d[keep])))
    return cx, cy, r, float(keep.mean()), keep


def _ellipse_ratio(xs, ys) -> float:
    D = np.stack([xs * xs, xs * ys, ys * ys, xs, ys, np.ones_like(xs)], 1)
    a, b, c, d, e, f = np.linalg.svd(D, full_matrices=False)[2][-1]
    M = np.array([[a, b / 2], [b / 2, c]])
    cen = np.linalg.solve(2 * M, [-d, -e])
    k = -(a * cen[0] ** 2 + b * cen[0] * cen[1] + c * cen[1] ** 2 + d * cen[0] + e * cen[1] + f)
    w = np.linalg.eigvalsh(M / k)
    if np.any(w <= 0):
        return float("nan")
    ax = 1 / np.sqrt(w)
    return float(ax.min() / ax.max())


def _edge(mask):
    return np.nonzero(mask & ~ndimage.binary_erosion(mask))


def load(data: bytes, side: int = SIDES[1]):
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    k = side / max(im.size)
    if k < 1:
        im = im.resize((round(im.width * k), round(im.height * k)))
    return im


def analyse(data: bytes) -> dict:
    """The picture's bytes → {"secondary", "shadow", "ocal", "spot", "drawtube", "verdict", "image"} or {"error"}: worked
    at three sizes, the middle one kept, the spread of the spot's offset and of the roundness given as their error."""
    runs = [_one(data, side) for side in SIDES]
    good = [r for r in runs if "error" not in r]
    if len(good) < 2:
        return runs[1] if "error" in runs[1] else (good[0] if good else runs[0])
    out = runs[1] if "error" not in runs[1] else good[0]
    spots = [r["spot"]["off"] for r in good if "spot" in r]
    if "spot" in out and len(spots) >= 2:
        out["spot"]["spread"] = round(max(spots) - min(spots), 4)
    rounds = [r["secondary"]["round"] for r in good]
    out["secondary"]["round_err"] = round(max(out["secondary"]["round_err"] or 0, (max(rounds) - min(rounds)) / 2), 4)
    out["verdict"] = verdict(out)
    out["image"] = drawn(load(data), out)
    return out


def _one(data: bytes, side: int) -> dict:
    try:
        im = load(data, side)
    except Exception as e:                                # noqa: BLE001 — not a picture: said
        return {"error": f"non è un'immagine leggibile ({type(e).__name__})"}
    g = np.asarray(im, dtype=np.float64).mean(axis=2)
    s = ndimage.gaussian_filter(ndimage.median_filter(g, size=7), 2)     # the moiré and the thin drawn lines away
    hist, edges = np.histogram(s, 256)
    p = hist / hist.sum()
    cum, mean = np.cumsum(p), np.cumsum(p * edges[:-1])
    between = (mean[-1] * cum - mean) ** 2 / (cum * (1 - cum) + 1e-12)
    bright = s > edges[int(np.argmax(between))]                          # Otsu
    lab, n = ndimage.label(bright)
    disk = hole = None
    for k in range(1, n + 1):                                # the bright disk with the biggest dark hole: the secondary
        comp = lab == k
        filled = ndimage.binary_fill_holes(comp)
        holes = filled & ~comp
        hl, hn = ndimage.label(holes)
        if not hn:
            continue
        hs = ndimage.sum(holes, hl, range(1, hn + 1))
        if hs.max() > 0.002 * s.size and (hole is None or hs.max() > hole.sum()):
            disk, hole = filled, hl == (int(np.argmax(hs)) + 1)
    if disk is None:
        return {"error": "non trovo il secondario con la sua ombra: serve la vista dal collimatore, a fuoco e intera"}
    ys, xs = _edge(disk)
    cx, cy, r, kept, keep = _robust(ys, xs)
    if kept < 0.6 or r < 40:
        return {"error": "il bordo del secondario non è abbastanza visibile per misurarlo"}
    rng = np.random.default_rng(0)
    idx = np.nonzero(keep)[0]
    ex, ey = xs[idx].astype(np.float64), ys[idx].astype(np.float64)
    ratio = _ellipse_ratio(ex, ey)
    boots = [_ellipse_ratio(ex[j], ey[j]) for j in (rng.choice(len(idx), len(idx)) for _ in range(60))]
    boots = [b for b in boots if b == b]
    sec = {"x": round(cx, 1), "y": round(cy, 1), "r": round(r, 1), "round": round(ratio, 4),
           "round_err": round(float(np.std(boots)), 4) if boots else None}
    hy, hx = _edge(hole)
    sx, sy, sr, _, _ = _robust(hy, hx)
    shadow = {"x": round(sx, 1), "y": round(sy, 1), "r": round(sr, 1)}
    out = {"size": [im.width, im.height], "secondary": sec, "shadow": shadow}
    # the collimator's reflection: the brighter ring inside the shadow; the centre spot: the darkest blob inside it
    yy, xx = np.mgrid[0:s.shape[0], 0:s.shape[1]]
    inside = np.hypot(xx - sx, yy - sy) < 0.85 * sr
    vals = s[inside]
    ring = inside & (s > np.percentile(vals, 70))
    rl, rn = ndimage.label(ring)
    if rn:
        rm = ndimage.binary_fill_holes(rl == (int(np.argmax(ndimage.sum(ring, rl, range(1, rn + 1)))) + 1))
        oy, ox = _edge(rm)
        ocx, ocy, ocr, okept, _ = _robust(oy, ox)
        if okept > 0.5 and 0.1 * sr < ocr < 0.9 * sr:
            out["ocal"] = {"x": round(ocx, 1), "y": round(ocy, 1), "r": round(ocr, 1)}
            near = np.hypot(xx - ocx, yy - ocy) < 0.6 * ocr
            dark = near & (s < np.percentile(s[near], 20))
            dl, dn = ndimage.label(dark)
            if dn:
                dm = ndimage.binary_fill_holes(dl == (int(np.argmax(ndimage.sum(dark, dl, range(1, dn + 1)))) + 1))
                py, px = ndimage.center_of_mass(dm)
                out["spot"] = {"x": round(float(px), 1), "y": round(float(py), 1),
                               "off": round(math.hypot(px - ocx, py - ocy) / r, 4),
                               "toward_deg": round(math.degrees(math.atan2(py - ocy, px - ocx)))}
    # the drawtube: the outer edge of the light along rays, only when the circle is whole in the picture
    pts = []
    for a in np.linspace(0, 2 * np.pi, 360, endpoint=False):
        rr = np.arange(int(1.05 * r), int(2.2 * r))
        x, y = (cx + rr * np.cos(a)).astype(int), (cy + rr * np.sin(a)).astype(int)
        ok = (x >= 0) & (x < s.shape[1]) & (y >= 0) & (y < s.shape[0])
        if ok.sum() < 20:
            continue
        v = np.diff(s[y[ok], x[ok]])
        j = int(np.argmin(v))
        if v[j] < -6:
            pts.append((y[ok][j], x[ok][j]))
    if len(pts) > 180:
        P = np.array(pts)
        dx, dy, dr, dkept, _ = _robust(P[:, 0], P[:, 1])
        whole = dx - dr > -2 and dy - dr > -2 and dx + dr < im.width + 2 and dy + dr < im.height + 2
        if dkept > 0.75 and whole:
            out["drawtube"] = {"x": round(dx, 1), "y": round(dy, 1), "r": round(dr, 1),
                               "off": round(math.hypot(cx - dx, cy - dy) / dr, 4),
                               "toward_deg": round(math.degrees(math.atan2(cy - dy, cx - dx)))}
    return out


def verdict(o: dict) -> list[dict]:
    from .ast_stars import way
    sec, out = o["secondary"], []
    err = sec["round_err"] or 0.0
    if sec["round"] >= ROUND_OK - 2 * err:
        out.append({"code": "secondary_round", "ok": True,
                    "text": f"secondario rotondo: assi al {sec['round']:.1%} uno dell'altro (±{err:.2%})"})
    else:
        out.append({"code": "secondary_oval", "ok": False,
                    "text": f"secondario ovale: assi al {sec['round']:.1%} uno dell'altro — rotazione o inclinazione del "
                            "secondario da ritoccare"})
    if "drawtube" in o:
        d = o["drawtube"]
        ok = d["off"] <= 0.03
        out.append({"code": "secondary_place", "ok": ok,
                    "text": f"secondario {'centrato' if ok else 'spostato verso ' + way(d['toward_deg'])} nel drawtube "
                            f"({d['off']:.1%} del raggio del drawtube)"})
    else:
        out.append({"code": "drawtube_unseen", "ok": None,
                    "text": "il bordo del drawtube non è intero nella foto: la posizione del secondario non si giudica"})
    if "spot" in o:
        sp = o["spot"]
        ok = sp["off"] <= SPOT_OK
        pm = f" (±{sp['spread'] / 2:.1%} fra le misure)" if sp.get("spread") is not None else ""
        out.append({"code": "primary", "ok": ok,
                    "text": (f"primario: il salvabuchi è nel riflesso del collimatore, scarto {sp['off']:.1%} del raggio "
                             f"del secondario{pm} — entro quello che una foto può vedere; il giudice finale sono le stelle"
                             if ok else
                             f"primario: il salvabuchi è spostato verso {way(sp['toward_deg'])} di {sp['off']:.1%} del "
                             "raggio del secondario rispetto al riflesso del collimatore — viti del primario")})
    else:
        out.append({"code": "spot_unseen", "ok": None, "text": "non trovo il salvabuchi nel riflesso del collimatore"})
    out.append({"code": "shadow", "ok": None,
                "text": "l'ombra del secondario non si giudica: con il secondario decentrato di un Newton veloce appare "
                        "spostata, ed è giusto"})
    return out


def drawn(im, o: dict) -> str:
    """The picture with what was found drawn on it: a JPEG as a data URL."""
    from PIL import ImageDraw
    pic = im.copy()
    d = ImageDraw.Draw(pic)
    for key, col in (("secondary", (255, 0, 255)), ("shadow", (0, 220, 255)), ("ocal", (255, 140, 0)),
                     ("drawtube", (60, 60, 255))):
        c = o.get(key)
        if c:
            d.ellipse([c["x"] - c["r"], c["y"] - c["r"], c["x"] + c["r"], c["y"] + c["r"]], outline=col, width=3)
            d.line([c["x"] - 8, c["y"], c["x"] + 8, c["y"]], fill=col, width=2)
            d.line([c["x"], c["y"] - 8, c["x"], c["y"] + 8], fill=col, width=2)
    if o.get("spot"):
        p = o["spot"]
        d.ellipse([p["x"] - 5, p["y"] - 5, p["x"] + 5, p["y"] + 5], outline=(255, 0, 0), width=3)
    buf = io.BytesIO()
    pic.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
