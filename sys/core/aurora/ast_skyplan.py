# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌌 Tonight's plan for any person's equipment (ROADMAP N30): the night (astronomical dark, the Moon), the sky's
forecast, and the whole catalogue (ast_catalog) ranked by the hours each object can be taken.

An hour counts for an object when it is dark (the Sun below 18°), the object is above `min_alt`, the forecast cloud is
at most CLOUD_MAX (when known), and the Moon allows it: for narrowband the Moon down or MOON_SEP_NARROW° away; for
broadband the Moon down, or under MOON_DIM lit, or MOON_SEP_BROAD° away and under half lit. The rank is those hours ×
how the object fits the field (the sensor × the scale: a tiny one or a mosaic counts less) × how bright it is.

The site is the inventory's, rounded to a tenth of a degree (else the weather's place, rounded here, never kept); the
forecast (Open-Meteo's cloud layers, 7Timer!'s seeing and transparency) is asked with that rounded place only."""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from . import ast_catalog, ast_sky

MIN_ALT = 30.0
CLOUD_MAX = 50
MOON_SEP_NARROW, MOON_SEP_BROAD, MOON_DIM = 30.0, 90.0, 0.25
SMALL, TINY, WELL = 0.15, 0.05, 0.3   # how much of the field the object fills (its long side along the field's)
# what a night is spent on: clusters and dark clouds count less than a nebula or a bright galaxy
APPEAL = {"OCl": 0.5, "GCl": 0.8, "DrkN": 0.6}
OVERLAP = 0.85                    # a mosaic's panel overlaps its neighbour by 15 %
FORECAST_TTL = 3600
SEEING = {1: "<0.5″", 2: "0.5–0.75″", 3: "0.75–1″", 4: "1–1.25″", 5: "1.25–1.5″", 6: "1.5–2″", 7: "2–2.5″", 8: ">2.5″"}
_forecast: dict = {}


def site(cfg, profile: dict | None) -> dict | None:
    """{"lat", "lon", "from"} rounded to 0.1°: the inventory's, else the weather's place rounded here."""
    s = ((profile or {}).get("rig") or {}).get("site")
    if s and s.get("lat") is not None:
        return {"lat": round(float(s["lat"]), 1), "lon": round(float(s["lon"]), 1), "from": "inventario"}
    try:
        lat, lon = float(cfg["AURORA_WEATHER_LAT"]), float(cfg["AURORA_WEATHER_LON"])
    except (TypeError, ValueError, KeyError):
        return None
    return {"lat": round(lat, 1), "lon": round(lon, 1), "from": "luogo del meteo (arrotondato)"}


def field(folder, profile: dict | None) -> dict | None:
    """The field in degrees: the lights' size in pixels (frames.json, else an integrated dark's name) × the scale."""
    scale = ((profile or {}).get("rig") or {}).get("scale_arcsec_px")
    if not scale:
        return None
    w = h = None
    try:
        fr = json.loads((folder / "frames.json").read_text(encoding="utf-8"))
        sizes = [(v["h"]["pixels"]["w"], v["h"]["pixels"]["h"]) for v in fr.values()
                 if v.get("h", {}).get("kind") == "light" and v["h"].get("pixels")]
        if sizes:
            w, h = max(set(sizes), key=sizes.count)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if not w:
        try:
            m = re.search(r"(\d{3,5})x(\d{3,5})", (folder / "darks.json").read_text(encoding="utf-8"))
            w, h = (int(m.group(1)), int(m.group(2))) if m else (None, None)
        except OSError:
            pass
    if not w:
        return None
    w, h = max(w, h), min(w, h)
    return {"w_deg": round(w * scale / 3600, 3), "h_deg": round(h * scale / 3600, 3), "px": [w, h], "scale": scale}


def fit(o: dict, fov: dict | None) -> dict:
    """How the object fills the field: its share of the short side, and the mosaic's panels when it does not fit."""
    if not fov or not o.get("maj"):
        return {"share": None, "panels": 1, "weight": 0.8, "words": "dimensione non nota" if fov else "campo non noto"}
    maj, mn = o["maj"] / 60, (o.get("min") or o["maj"]) / 60
    share = max(maj / fov["w_deg"], mn / fov["h_deg"])
    nx = max(1, math.ceil(maj / (fov["w_deg"] * OVERLAP))) if maj > fov["w_deg"] * 0.95 else 1
    ny = max(1, math.ceil(mn / (fov["h_deg"] * OVERLAP))) if mn > fov["h_deg"] * 0.95 else 1
    panels = nx * ny
    if panels > 1:
        return {"share": round(share, 2), "panels": panels, "weight": round(1 / math.sqrt(panels), 2),
                "words": f"non entra: mosaico {nx}×{ny}"}
    if share < TINY:
        return {"share": round(share, 2), "panels": 1, "weight": 0.2, "words": f"molto piccolo (riempie il {share:.0%} del campo)"}
    if share < SMALL:
        return {"share": round(share, 2), "panels": 1, "weight": 0.5, "words": f"piccolo (riempie il {share:.0%} del campo)"}
    return {"share": round(share, 2), "panels": 1, "weight": 1.0 if share >= WELL else 0.75,
            "words": f"entra (riempie il {share:.0%} del campo)"}


def brightness(o: dict) -> float:
    if o["type"] in ast_catalog.GALAXY:
        mag = o.get("mag") or ast_catalog.GALAXY_MAG
        return round(float(np.clip(1 - (mag - 9) / (ast_catalog.GALAXY_MAG - 9) * 0.7, 0.3, 1)), 2)
    if o.get("bright") is not None:                              # Sharpless: 1 faint … 3 bright
        return {1: 0.4, 2: 0.7}.get(int(o["bright"]), 1.0)
    if o["name"].startswith("LDN"):
        return 0.5
    return APPEAL.get(o["type"], 1.0)


def kind(o: dict, saved: dict | None = None) -> str:
    """narrowband / broadband / hdr: the person's choice for one of its names (the 🎯 tab), a bright core by its names
    (ast_sensor), else the catalogue's type."""
    from . import ast_sensor
    every = [o["name"]] + o.get("aliases", []) + o.get("common", []) + ast_catalog.named(o)
    mine = next((saved[n] for n in every if (saved or {}).get(n) in ast_sensor.CLASSES), None)
    if mine:
        return mine
    names = " ".join(every)
    if ast_sensor.HDR_WORDS.search(names):
        return "hdr"
    return ast_catalog.CLASS.get(o["type"], "broadband")


def start_of(date: str, tz: ZoneInfo, now: float | None = None) -> datetime:
    """The local noon a night starts from: the date given, else tonight (before 6:00 the night still going on)."""
    if date:
        d = datetime.strptime(date[:10], "%Y-%m-%d")
    else:
        n = datetime.fromtimestamp(now or time.time(), tz)
        d = n - timedelta(days=1) if n.hour < 6 else n
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=tz)


def forecast(lat: float, lon: float, tz: str) -> dict:
    """{"hours": {epoch_hour: cloud%}, "seeing": {epoch: (seeing 1–8, transparency 1–8)}, "errors"}: cached an hour."""
    key = (lat, lon)
    hit = _forecast.get(key)
    if hit and time.time() - hit["at"] < FORECAST_TTL:
        return hit
    import httpx
    out = {"at": time.time(), "hours": {}, "layers": {}, "seeing": {}, "errors": []}
    try:
        j = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
            "latitude": lat, "longitude": lon, "timezone": "UTC", "forecast_days": 3, "timeformat": "unixtime",
            "hourly": "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high"}).raise_for_status().json()
        h = j["hourly"]
        for i, t in enumerate(h["time"]):
            out["hours"][int(t)] = h["cloud_cover"][i]
            out["layers"][int(t)] = (h["cloud_cover_low"][i], h["cloud_cover_mid"][i], h["cloud_cover_high"][i])
    except Exception as e:                           # noqa: BLE001 — without a forecast the plan is the sky's alone
        out["errors"].append(f"Open-Meteo: {type(e).__name__}")
    try:
        j = httpx.get("https://www.7timer.info/bin/astro.php", timeout=20, params={
            "lon": lon, "lat": lat, "ac": 0, "unit": "metric", "output": "json", "tzshift": 0}).raise_for_status().json()
        init = datetime.strptime(j["init"], "%Y%m%d%H").replace(tzinfo=ZoneInfo("UTC")).timestamp()
        for p in j["dataseries"]:
            out["seeing"][int(init + p["timepoint"] * 3600)] = (p["seeing"], p["transparency"])
    except Exception as e:                           # noqa: BLE001
        out["errors"].append(f"7Timer!: {type(e).__name__}")
    _forecast[key] = out
    return out


def _cloud_at(fc: dict, t: np.ndarray) -> np.ndarray:
    """The forecast cloud % at each time (its hour), NaN where unknown."""
    hrs = fc.get("hours") or {}
    return np.array([hrs.get(int(x // 3600 * 3600), np.nan) for x in t], dtype=float)


def plan(cfg, profile: dict | None, folder, date: str = "", min_alt: float = MIN_ALT, only: str = "", limit: int = 10,
         objects: list[dict] | None = None, fc: dict | None = None, now: float | None = None, name: str = "",
         saved: dict | None = None) -> dict:
    """The night and the targets ranked; `name`: that one object's whole night instead of a ranking."""
    st = site(cfg, profile)
    if not st:
        return {"error": "nessun sito: carica l'inventario del PC del telescopio (pagina 🔭 Astro) o indica il luogo del meteo"}
    tzname = str(cfg["AURORA_TIMEZONE"] or "UTC")
    tz = ZoneInfo(tzname)
    start = start_of(date, tz, now)
    n = ast_sky.night(st["lat"], st["lon"], start.timestamp())
    if objects is None:
        objects = ast_catalog.load(folder)["objects"]
    fc = forecast(st["lat"], st["lon"], tzname) if fc is None else fc
    cloud = _cloud_at(fc, n["t"])
    fov = field(folder, profile)
    hm = lambda s: datetime.fromtimestamp(s, tz).strftime("%H:%M")              # noqa: E731
    dark = n["dark"]
    moon_up = n["moon_alt"] > 0
    lit = float(np.mean(n["moon_lit"][dark])) if dark.any() else float(n["moon_lit"][len(n["t"]) // 2])
    known = ~np.isnan(cloud)
    clear = np.where(known, cloud <= CLOUD_MAX, True)
    seeing = sorted((t, v) for t, v in fc.get("seeing", {}).items() if n["dusk"] and n["dusk"] - 3 * 3600 <= t <= n["dawn"] + 3600)
    out = {"site": st, "date": start.strftime("%Y-%m-%d"), "timezone": tzname, "field": fov, "min_alt": min_alt,
           "night": {"dusk": hm(n["dusk"]) if n["dusk"] else None, "dawn": hm(n["dawn"]) if n["dawn"] else None,
                     "dark_h": round(float(dark.sum()) * n["step_h"], 1),
                     "moon_lit": round(lit, 2),
                     "moon_up_dark_h": round(float((dark & moon_up).sum()) * n["step_h"], 1),
                     "clear_dark_h": round(float((dark & clear & known).sum()) * n["step_h"], 1) if known[dark].any() else None,
                     "cloud_mean": round(float(np.nanmean(cloud[dark])), 0) if known[dark].any() else None,
                     "seeing": [{"at": hm(t), "seeing": SEEING.get(v[0], "?"), "transparency": v[1]} for t, v in seeing][:6],
                     "forecast_errors": fc.get("errors", [])},
           "catalogue": len(objects)}
    if not dark.any():
        out["targets"] = []
        return out
    pick = [o for o in objects if (not only or kind(o, saved) == only or (only == "galaxy" and o["type"] in ast_catalog.GALAXY))]
    if name:
        o = ast_catalog.find(objects, name)
        if not o:
            out["error"] = f"«{name}» non è nel catalogo ({len(objects)} oggetti): prova il nome NGC/IC/M/Sh2"
            return out
        pick = [o]
    j = n["jd"]
    ra0, dec0 = np.array([o["ra"] for o in pick]), np.array([o["dec"] for o in pick])
    mid = j[len(j) // 2]
    ra, dec = ast_sky.precess(ra0, dec0, mid)
    alt = ast_sky.altitude(ra, dec, st["lat"], st["lon"], j)                       # (objects, times)
    sep = ast_sky.separation(ra[:, None], dec[:, None], n["moon_ra"][None, :], n["moon_dec"][None, :])
    kinds = [kind(o, saved) for o in pick]
    narrow = np.array([k == "narrowband" for k in kinds])[:, None]
    moon_ok_n = ~moon_up[None, :] | (sep >= MOON_SEP_NARROW)
    moon_ok_b = ~moon_up[None, :] | (n["moon_lit"][None, :] < MOON_DIM) | ((sep >= MOON_SEP_BROAD) & (n["moon_lit"][None, :] < 0.5))
    sky_ok = dark[None, :] & (alt >= min_alt) & np.where(narrow, moon_ok_n, moon_ok_b)
    usable = sky_ok & clear[None, :]
    if not usable.any() and sky_ok.any() and known[dark].any():
        usable = sky_ok                                  # all clouded: the ranking if the sky opens, said as such
        out["clouds_ignored"] = True
    hours = usable.sum(axis=1) * n["step_h"]
    rows = []
    for i, o in enumerate(pick):
        if hours[i] <= 0 and not name:
            continue
        f = fit(o, fov)
        a = np.where(dark, alt[i], -90)
        top = int(np.argmax(a))
        idx = np.flatnonzero(usable[i])
        rows.append({"name": o["name"], "aliases": o["aliases"][:3], "common": (ast_catalog.named(o) + o["common"])[:2],
                     "type": ast_catalog.WORDS.get(o["type"], o["type"]), "kind": kinds[i],
                     "size_arcmin": [o.get("maj"), o.get("min")], "mag": o.get("mag"),
                     "hours": round(float(hours[i]), 1), "from": hm(n["t"][idx[0]]) if idx.size else None,
                     "to": hm(n["t"][idx[-1]] + n["step_h"] * 3600) if idx.size else None,
                     "max_alt": round(float(a[top]), 0), "max_at": hm(n["t"][top]),
                     "moon_sep": round(float(np.min(np.where(dark & moon_up, sep[i], 180))), 0),
                     "fit": f, "score": round(float(hours[i]) * f["weight"] * brightness(o), 2)})
    rows.sort(key=lambda r: (-r["score"], -r["max_alt"]))
    out["targets"] = rows[:max(1, min(int(limit), 50))]
    out["candidates"] = len(rows)
    if name:
        out["hourly"] = [{"at": hm(t), "alt": round(float(alt[0][k]), 0), "dark": bool(dark[k]), "moon_alt": round(float(n["moon_alt"][k]), 0),
                          "cloud": None if np.isnan(cloud[k]) else int(cloud[k]), "usable": bool(usable[0][k])}
                         for k, t in enumerate(n["t"]) if k % 6 == 0 and (dark[k] or n["sun_alt"][k] < 0)]
    return out


def tonight(cfg, date: str = "", min_alt: float = MIN_ALT, only: str = "", limit: int = 10, name: str = "") -> dict:
    """The plan of the person whose configuration this is: their inventory, folder, frames and own kinds."""
    from . import ast_advice, ast_inventory
    folder = ast_inventory.folder(cfg)
    profile = ast_inventory.profile(cfg)
    saved = ast_advice.setup(folder).get("kinds") or {}
    return with_set(cfg, plan(cfg, profile, folder, date, min_alt, only, limit, name=name, saved=saved), profile)


def with_set(cfg, p: dict, profile: dict | None) -> dict:
    """The camera's set for each target's kind (ast_sensor: measured on the person's frames, with their darks)."""
    from . import ast_inventory, ast_sensor
    try:
        m = ast_sensor.measure(cfg, str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip())
        sp = ast_sensor.plan(m, ast_inventory.darks_library(cfg)["darks"], profile, 3)
    except Exception:                                # noqa: BLE001 — the plan stands without the set
        return p
    for r in p.get("targets", []):
        k = sp["kinds"].get(r["kind"]) or {}
        if r["kind"] == "hdr":
            r["set"] = f"HDR: gain {k.get('gain')}, pose {', '.join(f'{x:g} s' for x in k.get('exposures', []))}"
        elif k.get("with_darks"):
            r["set"] = f"gain {k['with_darks']['gain']:g}, offset {k['with_darks']['offset']:g}, posa {k['with_darks']['exposure_s']:g} s (con i tuoi dark)"
        elif k.get("best"):
            r["set"] = f"gain {k['best']['gain']:g}, offset {k['best']['offset']:g}, posa {k['best']['exposure_s']} s (nessun dark adatto)"
    return p


def text(p: dict) -> str:
    """The plan in words, for the chat."""
    if p.get("error") and not p.get("night"):
        return p["error"]
    nt, s = p["night"], p["site"]
    lines = [f"Notte del {p['date']} a lat {s['lat']}, lon {s['lon']} ({s['from']}); altezza minima {p['min_alt']:g}°."]
    if not nt["dusk"]:
        return lines[0] + " Non diventa mai buio astronomico (Sole sempre sopra −18°)."
    lines.append(f"Buio astronomico {nt['dusk']}–{nt['dawn']} ({nt['dark_h']} h); Luna illuminata al {nt['moon_lit']:.0%}, "
                 f"sopra l'orizzonte {nt['moon_up_dark_h']} h di buio.")
    if nt["cloud_mean"] is not None:
        lines.append(f"Nuvole previste (Open-Meteo): {nt['cloud_mean']:.0f}% in media nel buio; ore serene (≤ {CLOUD_MAX}%): {nt['clear_dark_h']} h.")
    if nt["seeing"]:
        lines.append("Seeing e trasparenza (7Timer!, 1 = ottima … 8): " + "; ".join(
            f"{x['at']} seeing {x['seeing']} trasp. {x['transparency']}" for x in nt["seeing"]))
    if nt["forecast_errors"]:
        lines.append("Previsioni non lette: " + ", ".join(nt["forecast_errors"]) + " — piano fatto sul solo cielo.")
    f = p.get("field")
    if f:
        lines.append(f"Campo: {f['w_deg']}° × {f['h_deg']}° ({f['px'][0]}×{f['px'][1]} px a {f['scale']}″/px).")
    if p.get("error"):
        lines.append(p["error"])
    if p.get("clouds_ignored"):
        lines.append(f"⚠️ Nessuna ora serena prevista: la classifica qui sotto vale solo se il cielo si apre.")
    for i, r in enumerate(p.get("targets", []), 1):
        alias = ", ".join(r["common"] + r["aliases"])
        size = f"{r['size_arcmin'][0]:g}′" if r["size_arcmin"][0] else "dimensione ?"
        lines.append(f"{i}. {r['name']}{f' ({alias})' if alias else ''} — {r['type']}, {r['kind']}, {size}: "
                     f"{r['hours']} h utili" + (f" {r['from']}–{r['to']}" if r["from"] else "")
                     + f", massimo {r['max_alt']:.0f}° alle {r['max_at']}, Luna a {r['moon_sep']:.0f}°; {r['fit']['words']}"
                     + (f"; {r['set']}" if r.get("set") else ""))
    if p.get("hourly"):
        def hour(h):
            cloud = "" if h["cloud"] is None else f" nuvole {h['cloud']}%"
            return f"{h['at']} {h['alt']:.0f}°{cloud}" + (" ✓" if h["usable"] else "")
        lines.append("Ora per ora: " + "; ".join(hour(h) for h in p["hourly"]))
    if p.get("error"):
        pass
    elif not p.get("targets"):
        lines.append("Nessun oggetto riprendibile stanotte con questi vincoli.")
    else:
        lines.append(f"({p.get('candidates', 0)} oggetti riprendibili su {p['catalogue']} del catalogo.)")
    return "\n".join(lines)
