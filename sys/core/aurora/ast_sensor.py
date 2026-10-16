# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The camera and the sky measured, and the settings for each kind of object (ROADMAP N28; owner, 16–17 Oct: «per
l'oggetto selezionato i valori ottimali di ripresa sarebbero X, Y, Z; in base alla tua libreria dark ti consiglio F, G,
H… un paio di dark per tipologia di oggetto con gain diversi… per gli HDR mantenere 1600 g, 20 o»).

The sensor, at each gain the person has a pair of flats and a pair of dark-flats (or darks) for: the photon transfer —
gain in e-/ADU = flat signal ÷ (variance of the flats' difference ÷ 2 − the same for the darks), read noise = the darks'
difference's scatter ÷ √2 × gain, the bias level, the full well up to 16-bit saturation, and the share of pixels the
offset leaves at zero. No manual: the person's own camera, at their own settings.

The sky, for each filter: the lights' faint end (each colour's 8 × 8 blocks' medians, their 10th percentile, a 5 % border
off) less the darks' level, in electrons per second; the weakest colour decides.

The settings: an exposure is long enough when the sky gives 10 × read noise² electrons (read noise then adds under
5 %), and short enough to lose little when a frame is thrown away; its floor is what the frame costs besides the light
(the download, a dither and its settling every few frames) at 85 % of the night spent collecting. Of the gains measured,
the one that reaches it soonest. Then the person's darks: the shortest that is long enough, at a gain and offset they
have. Bright objects (HDR): the gain and offset of the profile, three exposures at least 2× apart from the darks."""
from __future__ import annotations

import json
import math
import re
import statistics
from pathlib import Path

import numpy as np

from aurora import ast_frames as F

LADDER = (15, 30, 45, 60, 90, 120, 150, 180, 200, 240, 280, 300, 360, 420, 480, 600)
NARROW = re.compile(r"(?i)extreme|duo|tri[- ]?band|quad|\bha\b|h-?alpha|oiii|o3|sii|s2|narrow|nbz|alp-?t|enhance|l-?ultimate|l-?enhance")
HDR_WORDS = re.compile(r"(?i)\bm ?42\b|orion|orione|pleiad|\bm ?45\b|trapez|\bm ?13\b|ercole|hercules|\bm ?8\b|laguna|lagoon")
BROAD_WORDS = re.compile(r"(?i)galass|galax|\bm ?(31|33|51|63|64|74|81|82|101|104|106)\b|ammass|cluster|riflession|reflection|"
                         r"cometa|comet|barnard|\bldn\b|\blbn\b|oscur|dark neb|vdb|sombrero|vortice|whirlpool|girandola")
CLASSES = ("narrowband", "broadband", "hdr")
SKY_E = 10.0                    # the sky's electrons per frame, in read noise²: read noise then adds < 5 %
MARGIN = 1.2
EFFICIENCY = 0.85


def _clip_var(x: np.ndarray) -> float:
    """The variance without the few pixels a cosmic ray or a hot pixel throws far (6 σ from the median, by the MAD)."""
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826 or 1.0
    return float(np.var(x[np.abs(x - med) < 6 * mad]))


def transfer(flats: list, darks: list) -> dict:
    """One gain's photon transfer from two flats and two darks (paths with their headers), per colour; the colour with
    the most signal below 70 % of saturation gives the numbers."""
    f1, f2 = (F.pixels(Path(h["file"]), h) for h in flats)
    d1, d2 = (F.pixels(Path(h["file"]), h) for h in darks)
    bayer = flats[0]["bayer"]
    a1, a2, b1, b2 = (F.channels(x, bayer) for x in (f1, f2, d1, d2))
    rows = {}
    for c in a1:
        sig = (a1[c].mean() + a2[c].mean() - b1[c].mean() - b2[c].mean()) / 2
        vf, vd = _clip_var(a1[c] - a2[c]) / 2, _clip_var(b1[c] - b2[c]) / 2
        if sig <= 0 or vf <= vd:
            continue
        g = sig / (vf - vd)
        rows[c] = {"signal_adu": round(float(sig)), "gain_e_adu": round(float(g), 4),
                   "read_noise_e": round(float(math.sqrt(vd) * g), 3), "read_noise_adu": round(float(math.sqrt(vd)), 2)}
    if not rows:
        raise ValueError("no usable signal in the flats")
    level = float(np.median(np.concatenate([x.ravel() for x in b1.values()])))
    use = max((c for c in rows if rows[c]["signal_adu"] + level < 0.7 * 65535), key=lambda c: rows[c]["signal_adu"],
              default=next(iter(rows)))
    g = rows[use]["gain_e_adu"]
    d_all = F.pixels(Path(darks[0]["file"]), darks[0])
    return {"gain": flats[0]["gain"], "offset": flats[0]["offset"], "gain_e_adu": g, "read_noise_e": rows[use]["read_noise_e"],
            "bias_adu": round(level), "full_well_e": round((65535 - level) * g), "zero_share": float(np.mean(d_all <= 0)),
            "channel": use, "channels": rows, "flats": [Path(h["file"]).name for h in flats],
            "darks": [Path(h["file"]).name for h in darks], "date": flats[0]["date"]}


def _pairs(frames: list[dict]) -> dict:
    """For each (gain, offset): the latest two flats of one exposure and two darks of the same exposure (±5 %)."""
    out = {}
    flats = [h for h in frames if h["kind"] == "flat" and h["gain"] is not None]
    darks = [h for h in frames if h["kind"] in ("darkflat", "dark", "bias") and h["gain"] is not None]
    for key in sorted({(h["gain"], h["offset"]) for h in flats}):
        fs = sorted((h for h in flats if (h["gain"], h["offset"]) == key), key=lambda h: h["mtime"], reverse=True)
        for f0 in fs:
            same = [h for h in fs if h["exposure_s"] == f0["exposure_s"] and h["filter"] == f0["filter"]][:2]
            ds = sorted((h for h in darks if (h["gain"], h["offset"]) == key and h["exposure_s"] and f0["exposure_s"]
                         and abs(h["exposure_s"] - f0["exposure_s"]) <= 0.05 * f0["exposure_s"] + 0.01),
                        key=lambda h: h["mtime"], reverse=True)[:2]
            if len(same) == 2 and len(ds) == 2:
                out[key] = (same, ds)
                break
    return out


def is_narrow(name: str) -> bool:
    return bool(NARROW.search(name or ""))


def sky(frames: list[dict], sensors: dict, darks_lib: list[dict], per_group: int = 3) -> list[dict]:
    """The sky of each filter and night from the lights: e-/s per pixel in each colour, the weakest named."""
    out = []
    lights = [h for h in frames if h["kind"] == "light" and h["exposure_s"] and h["exposure_s"] >= 10]
    groups: dict = {}
    for h in lights:
        groups.setdefault((h["filter"], h["gain"], h["offset"], h["exposure_s"], h["date"]), []).append(h)
    for (flt, gain, off, exp, date), hs in sorted(groups.items(), key=lambda kv: kv[0][4], reverse=True)[:12]:
        s = sensors.get((gain, off))
        if not s:
            continue
        integrated = next((d for d in darks_lib if not d.get("old") and d.get("gain") == gain and d.get("offset") == off
                       and d.get("exposure_s") == exp and d.get("level_adu") is not None), None)
        dark_level = integrated["level_adu"] if integrated else s["bias_adu"]
        vals: dict[str, list] = {}
        for h in sorted(hs, key=lambda h: h["mtime"])[:: max(1, len(hs) // per_group)][:per_group]:
            a = F.pixels(Path(h["file"]), h)
            by, bx = a.shape[0] // 40 * 2, a.shape[1] // 40 * 2
            for c, x in F.channels(a[by: a.shape[0] - by, bx: a.shape[1] - bx], h["bayer"], centre=False).items():
                vals.setdefault(c, []).append(background(x) - dark_level)
        rate = {c: round(statistics.median(v) * s["gain_e_adu"] / exp, 4) for c, v in vals.items()}
        weak = min(rate, key=rate.get)
        out.append({"filter": flt, "narrow": is_narrow(flt), "gain": gain, "offset": off, "exposure_s": exp, "date": date,
                    "frames": len(hs), "e_s": rate, "weakest": weak, "rate": rate[weak],
                    "dark": "integrated" if integrated else "bias"})
    return out


def background(x: np.ndarray, block: int = 8) -> float:
    """The sky's level in a colour: the median of each block of 8 × 8 pixels (the noise and the stars out), then the
    10th percentile of the blocks (the faint end, under any nebula). The percentile of single pixels would sit 1.3 σ
    of the noise below the sky."""
    if x.ndim != 2 or min(x.shape) < 4 * block:
        return float(np.median(x))
    h, w = x.shape[0] // block * block, x.shape[1] // block * block
    b = np.median(x[:h, :w].reshape(h // block, block, w // block, block).swapaxes(1, 2).reshape(h // block, w // block, -1), axis=2)
    return float(np.percentile(b, 10))


def floor_s(overhead_s: float) -> float:
    """The shortest exposure that keeps EFFICIENCY of the night collecting light, given what each frame costs besides."""
    return overhead_s * EFFICIENCY / (1 - EFFICIENCY)


def nice(t: float) -> int:
    return next((x for x in LADDER if x >= t), LADDER[-1])


def best(rate: float | None, sensors: dict, overhead_s: float) -> dict | None:
    """The best measured gain for a sky rate: the exposure it needs, and why."""
    if not rate or rate <= 0 or not sensors:
        return None
    opts = []
    for (gain, off), s in sensors.items():
        t_min = SKY_E * s["read_noise_e"] ** 2 / rate
        t = nice(max(MARGIN * t_min, floor_s(overhead_s)))
        opts.append({"gain": gain, "offset": off, "exposure_s": t, "t_min": round(t_min), "floor_s": round(floor_s(overhead_s)),
                     "read_noise_e": s["read_noise_e"], "full_well_e": s["full_well_e"],
                     "sky_e": round(rate * t, 1), "sky_share": round(rate * t / s["full_well_e"], 4)})
    return min(opts, key=lambda o: (o["exposure_s"], -o["full_well_e"]))


def with_darks(rate: float | None, sensors: dict, darks_lib: list[dict], overhead_s: float) -> dict | None:
    """The person's darks: the shortest that is long enough, at a gain they have measured."""
    usable = []
    for d in darks_lib:
        s = sensors.get((d.get("gain"), d.get("offset")))
        if d.get("old") or not s or not d.get("exposure_s") or not rate:
            continue
        t_min = SKY_E * s["read_noise_e"] ** 2 / rate
        if d["exposure_s"] >= max(t_min, floor_s(overhead_s)):
            usable.append({"gain": d["gain"], "offset": d["offset"], "exposure_s": d["exposure_s"], "t_min": round(t_min)})
    return min(usable, key=lambda u: u["exposure_s"]) if usable else None


def hdr(darks_lib: list[dict], gain, offset) -> list[float]:
    """Three exposures at least 2× apart (15, 60, 120 s with the usual darks), from the darks at the profile's gain and
    offset."""
    have = sorted({d["exposure_s"] for d in darks_lib if not d.get("old") and d.get("gain") == gain and d.get("offset") == offset
                   and d.get("exposure_s")})
    if not have:
        return []
    picks = [have[0]]
    for t in have[1:]:
        if t >= 2 * picks[-1] and len(picks) < 3:
            picks.append(t)
    return picks


def kind_of(name: str, saved: dict | None = None) -> str:
    """An object's kind from the person's choice, else from its name."""
    if (saved or {}).get(name) in CLASSES:
        return saved[name]
    if HDR_WORDS.search(name or ""):
        return "hdr"
    if BROAD_WORDS.search(name or ""):
        return "broadband"
    return "narrowband"


def overhead(profile: dict | None, every: int | None) -> float:
    """What a frame costs besides its light, in seconds: the download (2 s), and a dither with its settling every
    `every` frames (the profile's settle time + 5 s for the move)."""
    gs = ((profile or {}).get("nina") or [{}])[0].get("GuiderSettings", {})
    try:
        settle = float(gs.get("SettleTime") or 10)
    except ValueError:
        settle = 10.0
    return round(2 + (settle + 5) / max(1, every or 3), 1)


def measure(cfg, frames_dir: str) -> dict:
    """The sensor at each gain and the sky of each filter, cached in the astro folder (sensor.json) by the frames used."""
    from aurora import ast_inventory as A
    d = A.folder(cfg)
    snap = d / "sensor.json"
    root = Path(frames_dir) if Path(frames_dir).is_absolute() else cfg.root / frames_dir
    if not frames_dir or not root.is_dir():
        try:
            return {**json.loads(snap.read_text(encoding="utf-8")), "from": "snapshot"}
        except (OSError, ValueError):
            return {"sensors": [], "sky": [], "frames": 0, "error": "frames folder not found" if frames_dir else ""}
    frames = F.scan(root)
    lib = A.darks_library(cfg)["darks"]
    pairs = _pairs(frames)
    sig = json.dumps({str(k): [[h["file"], h["mtime"]] for h in v[0] + v[1]] for k, v in pairs.items()}, sort_keys=True)
    lights_sig = json.dumps(sorted((h["file"], h["mtime"]) for h in frames if h["kind"] == "light"))
    try:
        old = json.loads(snap.read_text(encoding="utf-8"))
        if old.get("sig") == sig and old.get("lights_sig") == lights_sig:
            return {**old, "from": "cache"}
    except (OSError, ValueError):
        pass
    sensors, errors = {}, []
    for key, (fs, ds) in pairs.items():
        try:
            sensors[key] = transfer(fs, ds)
        except (OSError, ValueError) as e:
            errors.append(f"gain {key[0]:g}: {e}"[:160])
    out = {"sensors": list(sensors.values()), "sky": sky(frames, sensors, lib), "frames": len(frames),
           "kinds": {k: sum(1 for h in frames if h["kind"] == k) for k in {h["kind"] for h in frames}},
           "errors": errors, "sig": sig, "lights_sig": lights_sig}
    try:
        snap.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


def plan(measured: dict, darks_lib: list[dict], profile: dict | None, every: int | None, name: str = "",
         saved_kinds: dict | None = None) -> dict:
    """The settings for each kind of object, and for the one named."""
    sensors = {(s["gain"], s["offset"]): s for s in measured.get("sensors", [])}
    ov = overhead(profile, every)
    rig = (profile or {}).get("rig") or {}
    g0, o0 = (float(rig["gain"]) if rig.get("gain") else None), (float(rig["offset"]) if rig.get("offset") else None)
    kinds = {}
    for k in ("narrowband", "broadband"):
        skies = [s for s in measured.get("sky", []) if s["narrow"] == (k == "narrowband")]
        rate = statistics.median(s["rate"] for s in skies) if skies else None
        kinds[k] = {"rate": rate, "skies": len(skies), "filters": sorted({s["filter"] for s in skies}),
                    "best": best(rate, sensors, ov), "with_darks": with_darks(rate, sensors, darks_lib, ov)}
    kinds["hdr"] = {"gain": g0, "offset": o0, "exposures": hdr(darks_lib, g0, o0), "lights_each": "30–40"}
    out = {"overhead_s": ov, "floor_s": round(floor_s(ov)), "kinds": kinds,
           "missing_gains": sorted({d["gain"] for d in darks_lib if not d.get("old") and d.get("gain") is not None
                                    and (d["gain"], d.get("offset")) not in sensors})}
    if name:
        k = kind_of(name, saved_kinds)
        out["object"] = {"name": name, "kind": k, "guessed": not (saved_kinds or {}).get(name)}
    return out
