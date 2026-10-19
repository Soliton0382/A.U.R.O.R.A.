# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The stars of one frame across the field: what the optics and the tracking did (owner, 19 Oct: «io segui guide da
anni ma non sono mai riuscito a dire: oh finalmente è collimato perfettamente… costruiscilo partendo dalle pose vecchie
col cassetto»). Read only, the frame as the camera wrote it.

A colour camera's 2×2 cells are summed into one pixel (every filter, the narrowband's red alone included): the stars are
found on it above the background, the saturated and the crowded left out, and each is measured by its adaptive
second moments (a Gaussian weight fitted to the star, as the shape measures of the sky surveys do) — size (FWHM),
ellipticity and the angle of its long axis. Then the field:
  the 3 × 3 sectors      median FWHM and ellipticity, the corners against the centre
  the best point         where FWHM(x, y) = a + b·x + c·y + d·(x² + y²) is least — in a collimated, square train it is
                         the centre; a tilt or a primary off its axis moves it, and one side swells
  radial or tangential   in the corners, along the radius or across it: the spacing of the corrector (back focus) when
                         it is the same in the four corners
  one direction          the same angle everywhere and a field otherwise even: tracking or guiding, not the optics
Sizes in arcseconds with the frame's scale (2 × the camera's: a cell is two pixels). The thresholds are what the night's
own scatter allows: a difference within it is said to be the seeing's."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

SIGMA = 6.0                  # a star's peak above the background, in the background's noise
BOX = 7                      # half the cutout, in cells
MIN_STARS = 30
FIT_COLS, FIT_ROWS = 8, 6     # the grid whose medians the field's shape is fitted to


def cells(raw: np.ndarray) -> np.ndarray:
    """A colour frame's 2×2 cells summed (a mono frame passes as it is when told so by the caller)."""
    h, w = raw.shape[0] // 2 * 2, raw.shape[1] // 2 * 2
    a = raw[:h, :w].astype(np.float32)
    return a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]


def background(img: np.ndarray, block: int = 64) -> tuple[np.ndarray, float]:
    """A smooth background (the median of blocks, spread back) and the noise around it."""
    h, w = img.shape
    gh, gw = max(1, h // block), max(1, w // block)
    grid = np.median(img[:gh * block, :gw * block].reshape(gh, block, gw, block), axis=(1, 3))
    bg = ndimage.zoom(grid, (h / gh, w / gw), order=1)[:h, :w]
    res = img - bg
    noise = 1.4826 * float(np.median(np.abs(res - np.median(res))))
    return bg, max(noise, 1e-6)


def _moments(cut: np.ndarray) -> tuple[float, float, float, float, float] | None:
    """Adaptive Gaussian-weighted second moments: (x, y, Ixx, Iyy, Ixy) in the cutout, or None."""
    n = cut.shape[0]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    cx = cy = (n - 1) / 2
    sxx = syy = 1.5
    sxy = 0.0
    for _ in range(12):
        det = sxx * syy - sxy * sxy
        if det <= 1e-6:
            return None
        dx, dy = xx - cx, yy - cy
        q = (syy * dx * dx - 2 * sxy * dx * dy + sxx * dy * dy) / det
        w = np.exp(-0.5 * q) * cut
        tot = w.sum()
        if tot <= 0:
            return None
        ncx, ncy = (w * xx).sum() / tot, (w * yy).sum() / tot
        dx, dy = xx - ncx, yy - ncy
        mxx, myy, mxy = (w * dx * dx).sum() / tot, (w * dy * dy).sum() / tot, (w * dx * dy).sum() / tot
        # the weighted moments of a Gaussian under a Gaussian weight of the same shape are half its own
        sxx, syy, sxy, cx, cy = 2 * mxx, 2 * myy, 2 * mxy, ncx, ncy
        if not (0 < cx < n - 1 and 0 < cy < n - 1) or sxx <= 0 or syy <= 0:
            return None
    return cx, cy, sxx, syy, sxy


def _core(cut: np.ndarray) -> tuple[float, float] | None:
    """The centre of the star's core: its brightest 3 × 3 cells weighted, sub-cell."""
    j = int(np.argmax(cut))
    y, x = divmod(j, cut.shape[1])
    if not (1 <= y < cut.shape[0] - 1 and 1 <= x < cut.shape[1] - 1):
        return None
    win = cut[y - 1:y + 2, x - 1:x + 2]
    t = win.sum()
    if t <= 0:
        return None
    yy, xx = np.mgrid[-1:2, -1:2]
    return x + float((win * xx).sum() / t), y + float((win * yy).sum() / t)


def stars(img: np.ndarray, saturation: float, limit: int = 3000) -> list[dict]:
    """[{x, y, fwhm (cells), e, angle (deg, 0 = along x), peak}] of the frame's measurable stars."""
    bg, noise = background(img)
    res = img - bg
    peaks = (res == ndimage.maximum_filter(res, size=2 * BOX + 1)) & (res > SIGMA * noise)
    ys, xs = np.nonzero(peaks)
    order = np.argsort(-res[ys, xs])
    h, w = img.shape
    out = []
    for i in order:
        y, x = int(ys[i]), int(xs[i])
        if not (BOX <= y < h - BOX and BOX <= x < w - BOX):
            continue
        if img[y, x] >= saturation:
            continue
        cut = res[y - BOX:y + BOX + 1, x - BOX:x + BOX + 1]
        if (cut > 0.5 * res[y, x]).sum() > 0.25 * cut.size:      # a nebula's knot or a blend, not a star
            continue
        m = _moments(np.clip(cut, 0, None))
        if not m:
            continue
        cx, cy, ixx, iyy, ixy = m
        cc = _core(np.clip(cut, 0, None))
        tr = ixx + iyy
        e = math.sqrt((ixx - iyy) ** 2 + 4 * ixy * ixy) / tr
        fwhm = 2.3548 * math.sqrt(tr / 2)
        if not 0.8 <= fwhm <= 2 * BOX:
            continue
        out.append({"x": x - BOX + cx, "y": y - BOX + cy, "fwhm": fwhm, "e": e,
                    "angle": math.degrees(0.5 * math.atan2(2 * ixy, ixx - iyy)), "peak": float(res[y, x]),
                    # the whole star's centre from its core's, in FWHMs: a tail on one side (coma) moves it, a trail
                    # or an ellipse does not
                    "tail": ((cx - cc[0]) / fwhm, (cy - cc[1]) / fwhm) if cc else (0.0, 0.0)})
        if len(out) >= limit:
            break
    return out


def _orient(sel: list[dict]) -> tuple[float, float]:
    """The mean of e·(cos 2θ, sin 2θ): its length (how much the stars agree on a direction) and its angle."""
    if not sel:
        return 0.0, 0.0
    cx = sum(s["e"] * math.cos(math.radians(2 * s["angle"])) for s in sel) / len(sel)
    cy = sum(s["e"] * math.sin(math.radians(2 * s["angle"])) for s in sel) / len(sel)
    return math.hypot(cx, cy), math.degrees(0.5 * math.atan2(cy, cx))


def field(st: list[dict], w: int, h: int, scale: float) -> dict:
    """The field's map and what it says. `scale`: arcseconds a cell."""
    if len(st) < MIN_STARS:
        return {"stars": len(st), "error": f"solo {len(st)} stelle misurabili (ne servono {MIN_STARS})"}
    grid = []
    for gy in range(3):
        row = []
        for gx in range(3):
            sel = [s for s in st if int(3 * s["x"] / w) == gx and int(3 * s["y"] / h) == gy]
            f = sorted(s["fwhm"] for s in sel)
            e = sorted(s["e"] for s in sel)
            row.append({"n": len(sel), "fwhm": round(f[len(f) // 2] * scale, 2) if f else None,
                        "e": round(e[len(e) // 2], 3) if e else None})
        grid.append(row)
    # FWHM(x, y) = a + b·x + c·y + d·(x² + y²), x and y from the centre in units of the half diagonal
    half = math.hypot(w, h) / 2
    xs, ys, fs, ns = [], [], [], []
    for gy in range(FIT_ROWS):                                # the median of each cell of a finer grid
        for gx in range(FIT_COLS):
            sel = [s["fwhm"] for s in st if int(FIT_COLS * s["x"] / w) == gx and int(FIT_ROWS * s["y"] / h) == gy]
            if len(sel) >= 5:
                xs.append(((gx + 0.5) * w / FIT_COLS - w / 2) / half)
                ys.append(((gy + 0.5) * h / FIT_ROWS - h / 2) / half)
                fs.append(float(np.median(sel)) * scale)
                ns.append(len(sel))
    X, Y, F, N = np.array(xs), np.array(ys), np.array(fs), np.array(ns, float)
    A = np.stack([np.ones_like(X), X, Y, X * X + Y * Y], axis=1)
    Wt = np.sqrt(N)
    coef, *_ = np.linalg.lstsq(A * Wt[:, None], F * Wt, rcond=None)
    resid = F - A @ coef
    scatter = float(np.sqrt(np.sum(N * resid ** 2) / max(1.0, N.sum())))
    dof = max(1, len(F) - 4)
    cov = np.linalg.pinv((A * N[:, None]).T @ A) * float(np.sum(N * resid ** 2)) / dof
    a, b, c, d = (float(v) for v in coef)
    grad = math.hypot(b, c)                                   # ″ of FWHM from the centre to the half diagonal
    grad_err = math.sqrt((b * b * cov[1, 1] + c * c * cov[2, 2]) / grad ** 2) if grad > 0 else 0.0
    best = None
    if d > 0:
        bx, by = -b / (2 * d), -c / (2 * d)
        best = {"x": round(bx, 2), "y": round(by, 2), "off": round(math.hypot(bx, by), 2)}
    worse = math.degrees(math.atan2(c, b))                    # the direction the FWHM grows, 0 = +x (right)
    # corners: elongation along the radius (+) or across it (−)
    rad = []
    for s in st:
        dx, dy = s["x"] - w / 2, s["y"] - h / 2
        if math.hypot(dx, dy) > 0.7 * half:
            phi = math.atan2(dy, dx)
            rad.append(s["e"] * math.cos(2 * (math.radians(s["angle"]) - phi)))
    coh, theta = _orient(st)
    tx = float(np.median([s["tail"][0] for s in st]))
    ty = float(np.median([s["tail"][1] for s in st]))
    tails = [math.hypot(*s["tail"]) for s in st]
    e_med = float(np.median([s["e"] for s in st]))
    centre = grid[1][1]["fwhm"]
    corners = [grid[y][x]["fwhm"] for y in (0, 2) for x in (0, 2) if grid[y][x]["fwhm"]]
    return {"stars": len(st), "scale": scale, "grid": grid, "fwhm_median": round(float(np.median(F)), 2),
            "e_median": round(e_med, 3), "centre": centre, "corners": corners,
            "corner_spread": round(max(corners) - min(corners), 2) if corners else None,
            "gradient": round(grad, 2), "gradient_err": round(grad_err, 2), "worse_toward_deg": round(worse),
            "curvature": round(d, 2), "best": best, "scatter": round(scatter, 2),
            "radial": round(float(np.mean(rad)), 3) if rad else None, "corner_stars": len(rad),
            "one_direction": round(coh, 3), "one_direction_deg": round(theta),
            "tail": round(math.hypot(tx, ty), 3), "tail_deg": round(math.degrees(math.atan2(ty, tx))),
            "tail_typical": round(float(np.median(tails)), 3)}


WAY = ["destra", "in basso a destra", "in basso", "in basso a sinistra", "sinistra", "in alto a sinistra", "in alto",
       "in alto a destra"]


def way(deg: float) -> str:
    """An angle on the frame (0 = right, 90 = down: rows grow downward) in words."""
    return WAY[int(((deg % 360) + 22.5) // 45) % 8]


def verdict(f: dict) -> list[dict]:
    """What the field says, each with its numbers: tilt or collimation, spacing, tracking, or nothing beyond the seeing."""
    if "error" in f:
        return [{"code": "few_stars", "text": f["error"]}]
    out = []
    seen = max(2.5 * f["gradient_err"], 0.1 * f["fwhm_median"])          # the night's own noise on the gradient
    if f["gradient"] > seen:
        out.append({"code": "one_side", "text": f"le stelle si gonfiano verso {way(f['worse_toward_deg'])}: "
                    f"+{f['gradient']:.2f}″ di FWHM dal centro al bordo (rumore ±{f['gradient_err']:.2f}″) — tilt del treno "
                    "o primario scollimato"})
    if f["best"] and f["best"]["off"] > 0.25 and f["curvature"] > 0.1:
        out.append({"code": "best_off", "text": f"il punto con le stelle migliori è spostato verso "
                    f"{way(math.degrees(math.atan2(f['best']['y'], f['best']['x'])))} ({f['best']['off']:.0%} della "
                    "semidiagonale): il centro ottico non è al centro del sensore"})
    if f["radial"] is not None and f["corner_stars"] >= 20 and abs(f["radial"]) > max(0.04, f["e_median"] * 0.4):
        out.append({"code": "spacing", "text": f"negli angoli le stelle sono allungate "
                    f"{'lungo il raggio (verso il centro)' if f['radial'] > 0 else 'di traverso al raggio'} "
                    f"(media {f['radial']:+.3f}): distanza correttore-sensore da rivedere"})
    coma = f["tail"] > max(0.03, 0.5 * f["tail_typical"])
    if coma:
        out.append({"code": "coma", "text": f"le stelle hanno la coda verso {way(f['tail_deg'])} in tutto il campo "
                    f"(spostamento del nucleo {f['tail']:.2f} FWHM): coma uniforme, il segno di un primario scollimato"})
    if f["one_direction"] > 0.6 * f["e_median"] and f["e_median"] > 0.08 and not coma:
        out.append({"code": "tracking", "text": f"le stelle sono allungate tutte nello stesso verso ({f['one_direction_deg']}° "
                    f"sul fotogramma, ellitticità mediana {f['e_median']:.2f}) senza coda: inseguimento o guida, non l'ottica"})
    if not out:
        out.append({"code": "ok", "text": f"campo uniforme: FWHM {f['fwhm_median']:.2f}″, angoli fra loro entro "
                    f"{f['corner_spread']:.2f}″ — oltre è il seeing"})
    return out


def frame(raw: np.ndarray, scale_arcsec_px: float, saturation: float = 65000, colour: bool = True) -> dict:
    """One frame as the camera wrote it → its field and verdict. `scale_arcsec_px` of the camera's own pixels."""
    img = cells(raw) if colour else raw.astype(np.float32)
    sat = saturation * (4 if colour else 1) * 0.9
    st = stars(img, sat)
    f = field(st, img.shape[1], img.shape[0], scale_arcsec_px * (2 if colour else 1))
    f["verdict"] = verdict(f)
    return f


def night(cfg, date: str = "", most: int = 8) -> dict:
    """The lights of one night (the latest, or `date` AAAA-MM-GG) from the frames folder: up to `most` of them spread
    over the night, each measured, and what they say together."""
    from collections import Counter
    from pathlib import Path
    from . import ast_frames as F, ast_inventory as A
    raw = str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip()
    root, why = F.local(raw) if raw else (None, "")
    if root is not None and not root.is_absolute():
        root = cfg.root / root
    if root is None or not root.is_dir():
        return {"error": why or "la cartella dei frame (AURORA_ASTRO_FRAMES_DIR) non è raggiungibile"}
    lights = [h for h in F.scan(root, cache=A.folder(cfg) / "frames.json") if h.get("kind") == "light"]
    dates = sorted({h.get("date") for h in lights if h.get("date")})
    if not dates:
        return {"error": "nessuna posa light nella cartella dei frame"}
    day = date if date in dates else dates[-1]
    pick = sorted((h for h in lights if h.get("date") == day), key=lambda h: Path(h["file"]).name)
    pick = pick[::max(1, len(pick) // most)][:most]
    scale = float(((A.profile(cfg) or {}).get("rig") or {}).get("scale_arcsec_px") or 0) or None
    rows = []
    for h in pick:
        try:
            f = frame(F.pixels(Path(h["file"]), h), scale or 1.0, colour=bool(h.get("bayer")))
        except (OSError, ValueError) as e:
            rows.append({"file": Path(h["file"]).name, "error": str(e)[:120]})
            continue
        rows.append({"file": Path(h["file"]).name, "filter": h.get("filter"), **f})
    good = [r for r in rows if "error" not in r]
    codes = Counter(v["code"] for r in good for v in r["verdict"])
    sides = Counter(way(r["worse_toward_deg"]) for r in good if any(v["code"] == "one_side" for v in r["verdict"]))
    # a side worse beyond twice its noise in most frames, always the same: small in each frame, real over the night
    steady = [r for r in good if r["gradient"] > 2 * r["gradient_err"]]
    sides_all = Counter(way(r["worse_toward_deg"]) for r in steady)
    side, k = sides_all.most_common(1)[0] if sides_all else (None, 0)
    near = {side, WAY[(WAY.index(side) + 1) % 8], WAY[(WAY.index(side) - 1) % 8]} if side else set()
    same = [r for r in steady if way(r["worse_toward_deg"]) in near]
    constant = None
    if good and len(same) >= max(3, 0.75 * len(good)):
        g = sorted(r["gradient"] for r in same)
        f = sorted(r["fwhm_median"] for r in same)
        constant = {"side": side, "frames": len(same), "of": len(good), "gradient": [g[0], g[-1]],
                    "pct": round(100 * g[len(g) // 2] / f[len(f) // 2], 1)}
    return {"date": day, "dates": dates[-10:], "frames": len(pick), "scale_known": scale is not None, "rows": rows,
            "codes": dict(codes), "worse_side": sides.most_common(1)[0][0] if sides else None, "constant": constant}


def night_text(n: dict) -> str:
    if "error" in n:
        return n["error"]
    good = [r for r in n["rows"] if "error" not in r]
    if not good:
        return f"Notte del {n['date']}: nessuna posa misurabile."
    unit = "″" if n["scale_known"] else " (unità di cella: scala non nota)"
    lines = [f"Notte del {n['date']}: {len(good)} pose misurate su {n['frames']} scelte lungo la notte."]
    for r in good:
        lines.append(f"- {r['file'][11:19] if len(r['file']) > 19 else r['file']}: {r['stars']} stelle, FWHM "
                     f"{r['fwhm_median']:.2f}{unit}, lato peggiore {way(r['worse_toward_deg'])} (+{r['gradient']:.2f}"
                     f"±{r['gradient_err']:.2f}), ellitticità {r['e_median']:.2f}, coda {r['tail']:.3f} → "
                     + "; ".join(v["code"] for v in r["verdict"]))
    half = len(good) // 2 + 1
    common = [c for c, k in n["codes"].items() if k >= half]
    words = {"one_side": f"un lato peggiore, quasi sempre {n['worse_side']}: tilt del treno (o collimazione, se c'è coda)",
             "best_off": "il punto migliore fuori dal centro", "spacing": "gli angoli allungati allo stesso modo: distanza "
             "correttore-sensore", "coma": "coda uniforme: primario scollimato", "tracking": "mosso nello stesso verso: "
             "inseguimento o guida", "ok": "campo uniforme: niente da correggere oltre il seeing"}
    c = n.get("constant")
    if c:
        lines.append(f"Lo stesso lato peggiore in {c['frames']} pose su {c['of']}: {c['side']} (+{c['gradient'][0]:.2f}…"
                     f"{c['gradient'][1]:.2f}{unit}, circa il {c['pct']:g}% della FWHM). Una direzione che non cambia con "
                     "l'oggetto, l'ora e il seeing è nel treno ottico: tilt (o collimazione, se ci fosse coda — qui "
                     + ("c'è" if "coma" in n["codes"] else "non c'è") + ").")
    lines.append("Nella maggior parte delle pose: " + ("; ".join(words.get(c, c) for c in common) if common else
                                                      "niente che si ripeta: le differenze sono quelle della notte") + ".")
    return "\n".join(lines)
