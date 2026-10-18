# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The polar alignment a night really had, from its own guiding (owner, 19 Oct: «se quello che fa nina va bene…
teniamo aurora in monitoraggio per capire dove potrebbe stare il problema… l'ortogonalità della montatura»). Read only:
the guide log PHD2 already writes, nothing moved.

The mount turns about its own axis, the sky about the pole; a star then drifts in declination at
dδ/dt = ω·e·sin(H − A) — e the angle between the two axes, A the hour angle it points to, H the star's hour angle;
the declination does not enter. Guided, that drift is what the declination pulses undo: summed in windows of
WINDOW_S (settling after a dither and runaways left out), each window gives one drift at its hour angle; the night's
windows fitted to a·sin H + b·cos H give e and A with their error. Where the night spans too little of the sky for
both components, only the one it saw is said, as a lower bound. ω·1′ = 0.2625″ of declination a minute.

Assumed: a pulse «N» moves the scope north on either side of the pier (ASCOM's rule; a driver that breaks it would
need PHD2's «reverse Dec output after flip»). What is said is a size, not which knob: the signs are not trusted.
Also kept: the angle between the RA and Dec moves PHD2 measured at calibration — far from 90° says backlash or a
mount whose axes are not square — and the Guiding Assistant's own estimate, a few minutes long, beside the night's."""
from __future__ import annotations

import math

WINDOW_S = 900
PER_ARCMIN = 0.2625                   # ″/min of declination drift for 1′ of polar error, at the worst hour angle
MIN_SPAN_H = 1.5                      # the hour angles a night must span to tell both components apart


def windows(rows: list[dict], skip: set[int], dec_speed: float, ha0: float | None) -> list[dict]:
    """[{ha, rate ″/min, frames}] of one session: rows are PHD2's frames {t, dec_ms signed: + north}."""
    if ha0 is None or not rows or not dec_speed:
        return []
    t0, out = rows[0]["t"], []
    start = t0 + 60
    while start + WINDOW_S <= rows[-1]["t"]:
        inside = [i for i, r in enumerate(rows) if start <= r["t"] < start + WINDOW_S]
        pick = [rows[i] for i in inside if i not in skip]
        if len(pick) >= 50:
            north = sum(r["dec_ms"] for r in pick) / 1000 * dec_speed          # ″ the guiding moved north
            minutes = WINDOW_S / 60 * len(pick) / len(inside)                   # the time the frames kept cover
            out.append({"ha": round(ha0 + (start + WINDOW_S / 2 - t0) / 3600 * 1.0027, 3),
                        "rate": round(-north / minutes, 3), "frames": len(pick)})
        start += WINDOW_S
    return out


def fit(points: list[dict]) -> dict | None:
    """The night's windows → {"arcmin", "err_arcmin", "toward_h", "span_h", "both"} or a lower bound."""
    if len(points) < 3:
        return None
    hs = [p["ha"] * math.pi / 12 for p in points]
    y = [p["rate"] for p in points]
    span = max(p["ha"] for p in points) - min(p["ha"] for p in points)
    if span < MIN_SPAN_H:                             # one component only: the mean drift, a lower bound
        m = sum(y) / len(y)
        sd = math.sqrt(sum((v - m) ** 2 for v in y) / (len(y) - 1)) / math.sqrt(len(y))
        return {"both": False, "at_least_arcmin": round(abs(m) / PER_ARCMIN, 1), "err_arcmin": round(sd / PER_ARCMIN, 1),
                "span_h": round(span, 1), "windows": len(y)}
    s = [math.sin(h) for h in hs]
    c = [math.cos(h) for h in hs]
    ss, cc, sc = sum(v * v for v in s), sum(v * v for v in c), sum(a * b for a, b in zip(s, c))
    sy, cy = sum(a * b for a, b in zip(s, y)), sum(a * b for a, b in zip(c, y))
    det = ss * cc - sc * sc
    if abs(det) < 1e-9:
        return None
    a, b = (sy * cc - cy * sc) / det, (cy * ss - sy * sc) / det        # y = a·sin H + b·cos H
    res = [v - a * si - b * ci for v, si, ci in zip(y, s, c)]
    var = sum(r * r for r in res) / max(1, len(y) - 2)
    va, vb = var * cc / det, var * ss / det
    amp = math.hypot(a, b)
    err = math.sqrt((a * a * va + b * b * vb) / amp ** 2) if amp > 0 else math.sqrt(va + vb)
    # a·sin H + b·cos H = amp·sin(H − A): A = −atan2(b, a)
    return {"both": True, "arcmin": round(amp / PER_ARCMIN, 1), "err_arcmin": round(err / PER_ARCMIN, 1),
            "toward_h": round((-math.atan2(b, a) * 12 / math.pi) % 24, 1), "span_h": round(span, 1),
            "scatter": round(math.sqrt(var), 3), "windows": len(y)}


def square(calibrations: list[dict]) -> float | None:
    """How far from 90° the RA and Dec moves were at the last calibration (degrees)."""
    ra = next((c["angle"] for c in reversed(calibrations) if c["axis"] == "RA"), None)
    dec = next((c["angle"] for c in reversed(calibrations) if c["axis"] == "DEC"), None)
    if ra is None or dec is None:
        return None
    d = abs((dec - ra + 180) % 360 - 180)
    return round(abs(90 - d), 1)


def night(log: dict) -> dict:
    """One guide log (ast_guidelog.parse) → what its night says about the polar alignment."""
    pts = [p for s in log.get("sessions", []) if not s.get("assistant") for p in s.get("drift", [])]
    return {"night": log.get("night"), "fit": fit(pts), "points": pts, "assistant_arcmin": (log.get("advice") or {}).get("pa_arcmin"),
            "square_deg": square(log.get("calibrations", []))}


def text(n: dict) -> str:
    f = n["fit"]
    head = f"Notte del {n['night']}: "
    if not f:
        out = head + "troppo poca guida lunga per misurare l'allineamento polare (servono almeno 45 minuti)."
    elif f["both"]:
        out = (head + f"errore polare effettivo {f['arcmin']}′ ± {f['err_arcmin']}′, misurato sulla deriva in DEC di "
               f"{f['windows']} finestre da 15 minuti su {f['span_h']} h di angolo orario.")
    else:
        out = (head + f"almeno {f['at_least_arcmin']}′ ± {f['err_arcmin']}′ (la notte ha coperto solo {f['span_h']} h di "
               "angolo orario: si vede una componente sola).")
    if n["assistant_arcmin"] is not None:
        out += f" Il Guiding Assistant, in pochi minuti, aveva stimato {n['assistant_arcmin']}′."
    if n["square_deg"] is not None:
        out += (f" Calibrazione: RA e DEC fuori squadra di {n['square_deg']:.1f}°"
                + (" ✅." if n["square_deg"] <= 5 else " ⚠️ (oltre 5°: gioco in DEC o assi non a squadra)."))
    return out
