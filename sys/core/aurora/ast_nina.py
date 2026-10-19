# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 Where the mount points and what the imaging program is doing, live (ROADMAP N28; owner, 16 Oct: «rappresentazione
del telescopio e montatura che mostra dove sta puntando»): N.I.N.A.'s Advanced API plugin on the telescope's PC (HTTP,
port 1888 by default; read only here — GETs, nothing that moves anything).

The site never leaves this module: the mount's answer carries the exact latitude and longitude and the sidereal time
(which, with the clock, gives the longitude back); they are dropped, and what is kept is rounded — altitude and azimuth
to 0.1°, the hour angle to 0.01 h. Asked at most every ASK_S; an unreachable PC is said, not raised."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request

PORT = 1888
ASK_S = 2.0
_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()


def _get(base: str, path: str, timeout: float = 3.0):
    with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as r:      # noqa: S310 — the person's own PC
        d = json.loads(r.read().decode("utf-8", "replace"))
    if not d.get("Success", True):
        raise RuntimeError(str(d.get("Error") or "error")[:160])
    return d.get("Response")


def _num(x, nd=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:                                                                 # NaN
        return None
    return round(v, nd) if nd is not None else v


def ha_of(lst_h, ra_h):
    """The hour angle in (-12, 12] h."""
    if lst_h is None or ra_h is None:
        return None
    h = (lst_h - ra_h) % 24
    return h - 24 if h > 12 else h


def mount(m: dict) -> dict:
    """The mount's answer without the site: pointing, side of pier, tracking, park, the time to the flip."""
    pier = {"pierEast": "east", "pierWest": "west"}.get(str(m.get("SideOfPier")), "unknown")
    ra, dec = _num(m.get("RightAscension")), _num(m.get("Declination"))
    flip = _num(m.get("TimeToMeridianFlip"))
    return {"connected": bool(m.get("Connected")), "name": m.get("DisplayName") or m.get("Name") or "",
            "ra_h": _num(ra, 4), "dec_deg": _num(dec, 3), "ha_h": _num(ha_of(_num(m.get("SiderealTime")), ra), 2),
            "alt_deg": _num(m.get("Altitude"), 1), "az_deg": _num(m.get("Azimuth"), 1), "pier": pier,
            "tracking": bool(m.get("TrackingEnabled")), "slewing": bool(m.get("Slewing")), "parked": bool(m.get("AtPark")),
            "home": bool(m.get("AtHome")), "guiding": bool(m.get("IsPulseGuiding")),
            "flip_h": flip if flip is not None and flip < 23.99 else None,
            "guide_rate": _num(m.get("GuideRateRightAscensionArcsecPerSec"), 2)}


def _ends_in(iso, now: float | None = None):
    """Seconds to N.I.N.A.'s «ExposureEndTime» (an ISO time with its offset), None when past or unreadable."""
    from datetime import datetime
    try:
        end = datetime.fromisoformat(str(iso)[:26] + str(iso)[-6:] if len(str(iso)) > 32 else str(iso)).timestamp()
    except ValueError:
        return None
    left = end - (now if now is not None else time.time())
    return round(left, 1) if left > 0 else None


def camera(c: dict) -> dict:
    exposing = bool(c.get("IsExposing"))
    return {"connected": bool(c.get("Connected")), "name": c.get("DisplayName") or c.get("Name") or "",
            "state": c.get("CameraState") or "", "temp_c": _num(c.get("Temperature"), 1), "target_c": _num(c.get("TargetTemp"), 1),
            "cooler": bool(c.get("CoolerOn")), "power": _num(c.get("CoolerPower"), 0), "gain": c.get("Gain"),
            "offset": c.get("Offset"), "size": [c.get("XSize"), c.get("YSize")], "exposing": exposing,
            "ends_in_s": _ends_in(c.get("ExposureEndTime")) if exposing else None}


def focuser(f: dict) -> dict:
    return {"connected": bool(f.get("Connected")), "name": f.get("DisplayName") or "", "position": f.get("Position"),
            "temp_c": _num(f.get("Temperature"), 1), "moving": bool(f.get("IsMoving"))}


def guider(g: dict) -> dict:
    r = g.get("RMSError") or {}
    return {"connected": bool(g.get("Connected")), "state": g.get("State") or "",
            "rms": {k: _num((r.get(src) or {}).get("Arcseconds"), 2) for k, src in (("ra", "RA"), ("dec", "Dec"), ("total", "Total"))}}


def sequence(s) -> dict:
    """What the sequence is doing: the containers and items RUNNING, by name (the tree as N.I.N.A. sends it)."""
    running: list[str] = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("Status") == "RUNNING" and n.get("Name"):
                running.append(str(n["Name"]))
            for v in n.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(n, list):
            for x in n:
                walk(x)
    walk(s)
    return {"running": running[-4:], "active": bool(running), **progress(s)}


def progress(s) -> dict:
    """The sequence's shooting (owner, 20 Oct: «il numero di ore totali… una sezione dedicata allo scatto e al progresso
    totale»): each series — a container holding a light «Take Exposure» and its loop of N iterations — with its target,
    exposure, gain, offset, done and planned; the totals in seconds. From the tree N.I.N.A. sends, nothing asked twice."""
    series: list[dict] = []

    def walk(n, target, above=""):
        if isinstance(n, list):
            for x in n:
                walk(x, target, above)
            return
        if not isinstance(n, dict):
            return
        if "Target" in n and n.get("Name"):
            target = str(n["Name"]).removesuffix("_Container")
        kids = n.get("Items") if isinstance(n.get("Items"), list) else []
        kids = kids + (n.get("Conditions") if isinstance(n.get("Conditions"), list) else [])
        shot = next((k for k in kids if isinstance(k, dict) and "ExposureTime" in k
                     and str(k.get("ImageType", "LIGHT")).upper() == "LIGHT"), None)
        loop = next((k for k in kids if isinstance(k, dict) and "CompletedIterations" in k), None)
        if shot and loop:
            exp = _num(shot.get("ExposureTime")) or 0.0
            total, done = int(loop.get("Iterations") or 0), int(loop.get("CompletedIterations") or 0)
            name = str(n.get("Name") or "").removesuffix("_Container")
            if re.match(r"(Take Many Exposures|Smart Exposure)", name) and above:     # the series' own name, «50x180s»
                name = above
            series.append({"target": target, "name": name,
                           "exposure_s": exp, "gain": shot.get("Gain"), "offset": shot.get("Offset"),
                           "done": min(done, total), "total": total, "status": str(n.get("Status") or shot.get("Status") or ""),
                           "running": "RUNNING" in (n.get("Status"), shot.get("Status"))})
            return
        here = str(n.get("Name") or "").removesuffix("_Container") or above
        for v in n.values():
            if isinstance(v, (dict, list)):
                walk(v, target, here)
    walk(s, "")
    planned = sum(x["total"] * x["exposure_s"] for x in series)
    done = sum(x["done"] * x["exposure_s"] for x in series)
    return {"series": series, "planned_s": round(planned), "done_s": round(done), "left_s": round(planned - done)}


def last_image(base: str) -> dict | None:
    """The last picture N.I.N.A. took this session (its image history): kind, exposure, filter, HFR, stars."""
    n = _get(base, "/image-history?count=true")
    if not isinstance(n, int) or n <= 0:
        return None
    h = _get(base, f"/image-history?index={n - 1}")
    h = h[0] if isinstance(h, list) and h else h
    if not isinstance(h, dict):
        return None
    return {"n": n, "type": h.get("ImageType") or "", "exposure_s": _num(h.get("ExposureTime"), 1),
            "filter": h.get("Filter") or "", "hfr": _num(h.get("HFR"), 2), "stars": h.get("Stars"),
            "date": str(h.get("Date") or "")[:19], "temp_c": _num(h.get("Temperature"), 1)}


WHERE_S = 0.4                                     # the mount alone, asked every second by the drawing (one call, ~0.1 s)


def where(host: str, port: int = PORT) -> dict:
    """Only where the mount points (the drawing follows it every second; the rest every few): the site dropped."""
    key = ("where", host, port)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < WHERE_S:
            return hit[1]
    try:
        out = {"reachable": True, "mount": mount(_get(f"http://{host}:{port}/v2/api", "/equipment/mount/info", 2.0))}
    except (OSError, ValueError, RuntimeError, AttributeError, urllib.error.URLError) as e:
        out = {"reachable": False, "error": str(getattr(e, "reason", e))[:160]}
    with _lock:
        _cache[key] = (time.time(), out)
    return out


def status(host: str, port: int = PORT) -> dict:
    """The picture: mount, camera, focuser, guider, sequence; each part on its own (one that fails says why)."""
    key = (host, port)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ASK_S:
            return hit[1]
    base = f"http://{host}:{port}/v2/api"
    out: dict = {"host": host, "port": port, "reachable": False, "error": ""}
    try:
        out["version"] = _get(base, "/version")
        out["reachable"] = True
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as e:
        out["error"] = str(getattr(e, "reason", e))[:160]
    if out["reachable"]:
        for part, path, fn in (("mount", "/equipment/mount/info", mount), ("camera", "/equipment/camera/info", camera),
                               ("focuser", "/equipment/focuser/info", focuser), ("guider", "/equipment/guider/info", guider),
                               ("sequence", "/sequence/state", sequence)):
            try:
                out[part] = fn(_get(base, path))
            except (OSError, ValueError, RuntimeError, AttributeError, urllib.error.URLError) as e:
                out[part] = {"error": str(getattr(e, "reason", e))[:160]}
        try:
            out["image"] = last_image(base)
        except (OSError, ValueError, RuntimeError, AttributeError, urllib.error.URLError):
            out["image"] = None
    with _lock:
        _cache[key] = (time.time(), out)
    return out


# the active profile's settings the advice compares (ast_advice); AstrometrySettings (the site) is never read
PROFILE_KEYS = {"GuiderSettings": ("DitherPixels", "SettlePixels", "SettleTime", "SettleTimeout", "GuiderName"),
                "MeridianFlipSettings": ("MinutesAfterMeridian", "MaxMinutesAfterMeridian", "PauseTimeBeforeMeridian", "SettleTime",
                                         "UseSideOfPier"),
                "FocuserSettings": ("AutoFocusStepSize", "BacklashIn", "BacklashOut"),
                "CameraSettings": ("Gain", "Offset", "Temperature", "PixelSize"),
                "TelescopeSettings": ("FocalLength", "FocalRatio")}


def profile(host: str, port: int = PORT, timeout: float = 3.0) -> dict | None:
    """N.I.N.A.'s active profile, only the sections and keys the advice uses (strings, as the inventory has them)."""
    try:
        r = _get(f"http://{host}:{port}/v2/api", "/profile/show?active=true", timeout)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError):
        return None
    if not isinstance(r, dict):
        return None
    return {sec: {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in (r.get(sec) or {}).items() if k in keys}
            for sec, keys in PROFILE_KEYS.items()}
