# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 Collimation from a defocused star, and which screw to turn (owner, 19 Oct: «messa a fuoco automatica, stella
luminosa, la sfuoco e lei controlla come è collimato il telescopio e poi mi dice cosa aggiustare o se va bene così»;
«primario decentrato, agisci sulla vite in basso a destra»).

A bright star defocused at the centre of the field is a ring (the primary's light) with a dark hole (the secondary's
shadow). Collimated, the hole sits in the ring's middle; a primary off its axis moves it. One frame is measured: the
ring's outer edge and the hole's edge each fitted with a circle (least squares on their boundary pixels), the hole's
centre against the ring's in fractions of the ring's radius. Off the field's centre a ring is uneven by itself (the
corrector's field): the star must be within CENTRE of the middle, or it is said.

Which screw: the screws' positions on the cell and how the image is turned are the person's own, so they are learned,
not assumed. The person turns one screw by a known amount (e.g. ⅛ of a turn clockwise) between two measures; the hole's
move per ⅛ turn is that screw's vector (astro_setup.json "collimation"). With two or three screws learned, the turns
that bring the hole to the middle are the least ones that do it (minimum norm), said for the one or two screws that
matter, rounded to a sixteenth of a turn. Within TOL the primary is left alone: «collimato — oltre è il seeing».
The frame comes from N.I.N.A. (Advanced API capture, the PNG it renders; no stretch), or from a file."""
from __future__ import annotations

import io
import json
import math
import time
import urllib.parse
import urllib.request

import numpy as np
from scipy import ndimage

PORT = 1888
TOL = 0.03                 # the hole off the middle by less than this (× the ring's radius): collimated
CENTRE = 0.12              # the ring farther than this from the frame's middle (× the half diagonal): uneven by itself
EIGHTHS = {"1/16": 0.5, "1/8": 1, "1/4": 2, "3/8": 3, "1/2": 4, "1": 8}


def parse_turn(text: str) -> float | None:
    """«1/8 orario», «1/4 di giro antiorario» → eighths of a turn, + clockwise; None when it does not read."""
    t = str(text).lower().replace("di giro", "").strip()
    amount = next((v for k, v in sorted(EIGHTHS.items(), key=lambda kv: -len(kv[0])) if t.startswith(k)), None)
    if amount is None:
        return None
    return -amount if "anti" in t else amount


def _circle(ys: np.ndarray, xs: np.ndarray) -> tuple[float, float, float] | None:
    """The least-squares circle through boundary points (Kåsa): (cx, cy, r)."""
    if len(xs) < 12:
        return None
    A = np.stack([xs, ys, np.ones_like(xs)], axis=1).astype(np.float64)
    b = (xs.astype(np.float64) ** 2 + ys.astype(np.float64) ** 2)
    (p, q, c), *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = p / 2, q / 2
    r2 = c + cx * cx + cy * cy
    return (float(cx), float(cy), float(math.sqrt(r2))) if r2 > 0 else None


def _edge(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.nonzero(mask & ~ndimage.binary_erosion(mask))


def measure(img: np.ndarray) -> dict:
    """One frame with one defocused star → {"ring", "hole", "offset", "off_x", "off_y", "centre_off"} or {"error"}."""
    a = img.astype(np.float64)
    if a.ndim == 3:
        a = a.mean(axis=2)
    s = ndimage.gaussian_filter(a, 2)
    bg = float(np.median(np.concatenate([s[:10].ravel(), s[-10:].ravel(), s[:, :10].ravel(), s[:, -10:].ravel()])))
    top = float(np.percentile(s, 99.7))
    if top - bg <= 0:
        return {"error": "nessuna stella: l'immagine è uniforme"}
    lit = s > bg + 0.3 * (top - bg)
    lab, n = ndimage.label(lit)
    if n == 0:
        return {"error": "nessuna stella sopra il fondo"}
    sizes = ndimage.sum(lit, lab, range(1, n + 1))
    ring = lab == (int(np.argmax(sizes)) + 1)
    disk = ndimage.binary_fill_holes(ring)
    h, w = a.shape
    ys, xs = np.nonzero(disk)
    if ys.min() == 0 or xs.min() == 0 or ys.max() == h - 1 or xs.max() == w - 1:
        return {"error": "la stella sfocata tocca il bordo dell'immagine: centrala o sfoca meno"}
    outer = _circle(*_edge(disk))
    hole = disk & ~ring
    if not outer or outer[2] < 12:
        return {"error": "la stella è troppo piccola: sfoca di più (un anello di almeno 25 pixel)"}
    hl, hn = ndimage.label(hole)
    if hn == 0:
        return {"error": "non vedo l'ombra del secondario: sfoca di più finché al centro compare il buco scuro"}
    hs = ndimage.sum(hole, hl, range(1, hn + 1))
    inner_mask = hl == (int(np.argmax(hs)) + 1)
    inner = _circle(*_edge(inner_mask))
    if not inner or not 0.15 <= inner[2] / outer[2] <= 0.7:
        return {"error": "l'ombra del secondario non si misura bene: sfoca un po' di più o un po' di meno"}
    dx, dy = (inner[0] - outer[0]) / outer[2], (inner[1] - outer[1]) / outer[2]
    half = math.hypot(w, h) / 2
    return {"ring": [round(v, 2) for v in outer], "hole": [round(v, 2) for v in inner],
            "off_x": round(dx, 4), "off_y": round(dy, 4), "offset": round(math.hypot(dx, dy), 4),
            "centre_off": round(math.hypot(outer[0] - w / 2, outer[1] - h / 2) / half, 3), "size": [w, h]}


def turns(off: tuple[float, float], screws: dict) -> list[dict]:
    """The least turns (in eighths, + clockwise) of the learned screws that move the hole by −off, largest first."""
    names = [k for k, v in screws.items() if v and math.hypot(*v) > 1e-4]
    if len(names) < 2:
        return []
    V = np.array([screws[k] for k in names], dtype=np.float64).T          # 2 × n: the hole's move per eighth
    want = -np.array(off, dtype=np.float64)
    a = V.T @ np.linalg.pinv(V @ V.T) @ want                              # minimum norm
    out = [{"screw": k, "eighths": float(x)} for k, x in zip(names, a)]
    out.sort(key=lambda t: -abs(t["eighths"]))
    return out


def say_turn(t: dict) -> str:
    sixteenths = round(abs(t["eighths"]) * 2)
    if sixteenths == 0:
        return ""
    frac = {1: "1/16", 2: "1/8", 3: "3/16", 4: "1/4", 6: "3/8", 8: "1/2", 12: "3/4", 16: "1 giro"}
    amount = frac.get(sixteenths, f"{sixteenths}/16")
    return f"la vite {t['screw']} di {amount}{'' if amount.endswith('giro') else ' di giro'} in senso " \
           f"{'orario' if t['eighths'] > 0 else 'antiorario'}"


def step(m: dict, state: dict, learn: tuple[str, float] | None = None) -> tuple[dict, dict]:
    """(what to say, the state to keep). learn: (screw, eighths turned, + clockwise) since the last measure."""
    if "error" in m:
        return {"done": False, "say": m["error"]}, state
    screws = dict(state.get("screws") or {})
    last = state.get("last")
    out = {"offset": m["offset"], "off_x": m["off_x"], "off_y": m["off_y"], "ring_px": m["ring"][2]}
    if learn:
        name, eighths = learn
        if not last or not eighths:
            return {"done": False, "say": "prima misura la stella, poi gira la vite e chiedimi di imparare"}, state
        mv = ((m["off_x"] - last["off_x"]) / eighths, (m["off_y"] - last["off_y"]) / eighths)
        if math.hypot(*mv) < 0.002:
            out["say"] = (f"girando la vite {name} l'ombra non si è mossa in modo misurabile: gira un po' di più "
                          "(per esempio 1/4) e riprova")
            return out, {**state, "last": {"off_x": m["off_x"], "off_y": m["off_y"], "at": time.time()}}
        screws[name] = [round(mv[0], 5), round(mv[1], 5)]
        out["learned"] = f"vite {name}: ⅛ di giro in senso orario sposta l'ombra di {math.hypot(*mv):.3f} raggi"
    new = {**state, "screws": screws, "last": {"off_x": m["off_x"], "off_y": m["off_y"], "at": time.time()}}
    if m["centre_off"] > CENTRE:
        out.update(done=False, say=f"la stella è lontana dal centro del campo ({m['centre_off']:.0%} della semidiagonale): "
                                   "lì l'anello è irregolare da sé — centrala e rimisura")
        return out, new
    if m["offset"] <= TOL:
        out.update(done=True, say=f"✅ Primario collimato: l'ombra è a {m['offset']:.1%} del raggio dal centro "
                                  f"dell'anello (soglia {TOL:.0%}). Lascia le viti come sono.")
        return out, new
    where = ("destra", "in basso", "sinistra", "in alto")[int(((math.degrees(math.atan2(m["off_y"], m["off_x"])) % 360)
                                                               + 45) // 90) % 4]
    plan = turns((m["off_x"], m["off_y"]), screws)
    words = [x for x in (say_turn(t) for t in plan[:2]) if x]
    if words:
        out.update(done=False, turns=plan, say=f"Ombra spostata verso {where} di {m['offset']:.1%} del raggio. Gira "
                   + " e poi ".join(words) + ", poi rimisura.")
    else:
        learned = ", ".join(screws) or "nessuna"
        out.update(done=False, say=f"Ombra spostata verso {where} di {m['offset']:.1%} del raggio. Per dirti quale vite "
                   f"girare devo imparare cosa fa ciascuna (imparate: {learned}): gira una vite di 1/8 in senso orario "
                   "e chiedimi di imparare quella vite, con il suo nome (per esempio «in basso a destra»).")
    return out, new


def capture_png(host: str, seconds: float, port: int = PORT, timeout: float = 120.0) -> np.ndarray:
    """One frame from N.I.N.A. as the PNG it renders, without its stretch: a 2-D array."""
    from PIL import Image
    q = urllib.parse.urlencode({"duration": seconds, "waitForResult": "true", "stream": "true", "quality": -1,
                                "skipAutoStretch": "true", "save": "false"})
    with urllib.request.urlopen(f"http://{host}:{port}/v2/api/equipment/camera/capture?{q}", timeout=timeout) as r:  # noqa: S310
        data = r.read()
    if data[:1] == b"{":
        d = json.loads(data.decode("utf-8", "replace"))
        raise RuntimeError(str(d.get("Error") or d.get("Response") or "N.I.N.A. non ha restituito un'immagine")[:200])
    return np.asarray(Image.open(io.BytesIO(data)), dtype=np.float64)     # 8 or 16 bits, grey or colour (measure averages)


def run(cfg, seconds: float = 3.0, learn: tuple[str, float] | None = None) -> dict:
    from . import ast_advice, ast_inventory
    folder = ast_inventory.folder(cfg)
    host, _ = ast_advice.telescope_host(cfg)
    if not host:
        return {"say": "nessun indirizzo del PC del telescopio (AURORA_ASTRO_PC o l'inventario)"}
    try:
        img = capture_png(host, seconds)
    except (OSError, RuntimeError, ValueError) as e:
        return {"say": f"N.I.N.A. non ha scattato: {e}"}
    out, state = step(measure(img), ast_advice.setup(folder).get("collimation") or {}, learn)
    ast_advice.save_part(folder, "collimation", state)
    return out
