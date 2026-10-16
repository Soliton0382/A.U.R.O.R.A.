# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The nights already guided (ROADMAP N28; owner, 16 Oct: «lei monitora… e modifica i parametri di inseguimento in
base a quello che legge nei log»): PHD2's guide logs (PHD2_GuideLog_*.txt, added to the astro folder) read back — each
guiding session with its settings, the RMS PHD2's way over the frames that count (no settling after a dither, no lost
star), the pulses at their limit, the runaways (an axis whose error grows while the pulses stay at their maximum: the
mount stopped following), the Guiding Assistant's measures and advice, and what Aurora reads in them, as codes and
numbers (the page says them in words). Read only; the debug logs are not read (tens of MB of internals).

Where the sky was is not kept: altitude and azimuth with RA, Dec and the time give the site back, so they are dropped;
the hour angle is kept rounded to 0.1 h (about the meridian flip, not the longitude)."""
from __future__ import annotations

import csv
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

FIRST = "PHD2 version"
RUN_MIN = 5                        # pulses at the limit in a row, the error growing, to call it a runaway
RUN_PX = 3.0                       # … and beyond this many pixels
GREMLIN = 6.0                      # a jump between two frames, in RMS of the axis (seeing alone: the difference of two
                                   # frames scatters by √2 RMS, so 6 RMS is over 4σ — once in tens of thousands)
_cache: dict[str, tuple[float, dict]] = {}


def logs(folder: Path) -> list[Path]:
    """The guide logs of the folder, newest first (the name or the first line says it)."""
    out = []
    for f in folder.iterdir() if folder.is_dir() else []:
        if f.is_file() and f.suffix.lower() in (".txt", ".log") and "debuglog" not in f.name.lower():
            try:
                with f.open(encoding="utf-8", errors="replace") as h:
                    if h.readline().startswith(FIRST):
                        out.append(f)
            except OSError:
                continue
    return sorted(out, key=lambda f: f.stat().st_mtime, reverse=True)


def _n(s, cast=float):
    try:
        return cast(s)
    except (TypeError, ValueError):
        return None


def _settings(lines: list[str]) -> dict:
    """A session's header: the settings that matter for the advice, no place in the sky beyond RA, Dec, hour angle."""
    s: dict = {}
    for ln in lines:
        if m := re.match(r"Equipment Profile = (.+)", ln):
            s["profile"] = m.group(1).strip()
        elif m := re.match(r"Pixel scale = ([\d.]+) arc-sec/px.*Focal length = ([\d.]+)", ln):
            s["scale"], s["focal_mm"] = float(m.group(1)), float(m.group(2))
        elif m := re.match(r"Exposure = (\d+) ms", ln):
            s["exposure_ms"] = int(m.group(1))
        elif m := re.match(r"Mount = ([^,]+)", ln):
            s.setdefault("mount", m.group(1).strip())
        elif m := re.match(r"X guide algorithm = ([^,]+)(?:, Control gain = ([\d.]+))?", ln):
            s["x_algo"], s["x_gain"] = m.group(1).strip(), _n(m.group(2))
        elif m := re.match(r"Minimum move = ([\d.]+)", ln):
            s.setdefault("x_min_move", float(m.group(1)))
        elif m := re.match(r"Y guide algorithm = ([^,]+), Minimum move = ([\d.]+)(?: Aggression = (\d+)%)?", ln):
            s["y_algo"], s["y_min_move"], s["y_aggr"] = m.group(1).strip(), float(m.group(2)), _n(m.group(3), int)
        elif m := re.match(r"Backlash comp = (enabled|disabled), pulse = (\d+) ms", ln):
            s["backlash_on"], s["backlash_ms"] = m.group(1) == "enabled", int(m.group(2))
        elif m := re.match(r"Max RA duration = (\d+), Max DEC duration = (\d+), DEC guide mode = (\w+)", ln):
            s["max_ra_ms"], s["max_dec_ms"], s["dec_mode"] = int(m.group(1)), int(m.group(2)), m.group(3)
        elif m := re.match(r"RA = ([\d.-]+) hr, Dec = ([\d.-]+) deg, Hour angle = ([\d.-]+) hr, Pier side = (\w+)", ln):
            s["ra_h"], s["dec_deg"] = round(float(m.group(1)), 2), round(float(m.group(2)), 1)
            s["ha_h"], s["_ha"], s["pier"] = round(float(m.group(3)), 1), float(m.group(3)), m.group(4)
    return s


def _rms(v: list[float]) -> float | None:
    if not v:
        return None
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / len(v))


def _runaways(rows: list[dict], axis: str, limit: int | None, scale: float) -> list[dict]:
    """Stretches where the axis's pulses sit at their limit and the error keeps growing: the mount is not following."""
    out, run = [], []
    for r in rows + [None]:
        hit = (r is not None and limit and r[f"{axis}_ms"] >= limit and abs(r[axis]) >= RUN_PX
               and (not run or abs(r[axis]) >= abs(run[-1][axis]) * 0.9))
        if hit:
            run.append(r)
            continue
        if len(run) >= RUN_MIN:
            a, b = run[0], run[-1]
            dt = max(1e-6, b["t"] - a["t"])
            out.append({"axis": axis, "t0": a["t"], "t1": b["t"], "frames": len(run),
                        "rate": round(abs(b[axis] - a[axis]) * scale / dt, 2), "peak": round(abs(b[axis]) * scale, 1)})
        run = []
    return out


def _session(start: str, head: list[str], body: list[str], info: list[tuple[int, str]]) -> dict:
    s = _settings(head)
    scale = s.get("scale") or 1.0
    cols, rows, lost, settling, skip = None, [], 0, False, set()
    for i, ln in enumerate(body):
        if ln.startswith("Frame,"):
            cols = ln.split(",")
            continue
        if ln.startswith("INFO:"):
            if "Settling started" in ln:
                settling = True
            elif "Settling complete" in ln or "Settling failed" in ln:
                settling = False
            continue
        if not cols or not ln[:1].isdigit():
            continue
        p = next(csv.reader([ln]))
        d = dict(zip(cols, p))
        if d.get("mount") == "DROP":
            lost += 1
            continue
        if d.get("mount") != "Mount" or d.get("ErrorCode", "0") not in ("0", "1", ""):
            continue                                      # a frame guided on a star that was not there
        r = {"t": _n(d.get("Time")) or 0.0, "ra": _n(d.get("RARawDistance")) or 0.0, "dec": _n(d.get("DECRawDistance")) or 0.0,
             "ra_ms": _n(d.get("RADuration"), int) or 0, "dec_ms": _n(d.get("DECDuration"), int) or 0, "snr": _n(d.get("SNR"))}
        if settling:
            skip.add(len(rows))
        rows.append(r)
    runs = _runaways(rows, "ra", s.get("max_ra_ms"), scale) + _runaways(rows, "dec", s.get("max_dec_ms"), scale)
    away = {i for i, r in enumerate(rows) for w in runs if w["t0"] <= r["t"]}   # the frames from a runaway on
    good = [r for i, r in enumerate(rows) if i not in skip and i not in away]
    ra, dec = _rms([r["ra"] * scale for r in good]), _rms([r["dec"] * scale for r in good])
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") if re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", start) else None
    when = lambda x: (t0 + timedelta(seconds=x)).strftime("%H:%M") if t0 else None
    ha = s.pop("_ha", None)
    for w in runs:
        w["at"] = when(w["t0"])
        if ha is not None:                               # minutes from the meridian then: the header's hour angle and
            w["meridian_min"] = round((ha + w["t0"] / 3600 * 1.0027) * 60)               # the sidereal time gone by
    snr = [r["snr"] for r in good if r["snr"] is not None]
    sat = lambda k, lim: sum(1 for r in good if lim and r[k] >= lim)
    jumps = _gremlins(good, scale, ra, dec, s.get("max_ra_ms"), s.get("max_dec_ms"))
    return {"start": start, "minutes": round((rows[-1]["t"] - rows[0]["t"]) / 60, 1) if len(rows) > 1 else 0.0,
            "frames": len(rows), "counted": len(good), "lost": lost, "settings": s,
            "rms": {"ra": _r(ra), "dec": _r(dec), "total": _r(math.hypot(ra, dec)) if ra is not None else None},
            "snr": round(sum(snr) / len(snr), 1) if snr else None,
            "at_limit": {"ra": sat("ra_ms", s.get("max_ra_ms")), "dec": sat("dec_ms", s.get("max_dec_ms"))},
            "dithers": sum(1 for _, x in info if x.startswith("DITHER")), "runaways": runs,
            "gremlins": {"n": len(jumps), "at": [when(t) for t in jumps[:5]]},
            "changes": [x.split("Guiding parameter change, ", 1)[1] for _, x in info if "Guiding parameter change" in x]}


def _gremlins(rows: list[dict], scale: float, ra: float | None, dec: float | None, max_ra, max_dec) -> list[float]:
    """Sudden jumps of the star (PHD2's «gremlins», B. Waddington's guide to the logs): from one frame to the next the
    error moves by more than GREMLIN× the axis's RMS and 3″, and the pulse just sent was not a large one — something moved
    (a cable, the wind, a loose joint), not PHD2. The times (seconds into the session) of each; only frames one
    after the other count, and the star must stay moved for two more (a single frame off and back is not one)."""
    out = []
    gaps = sorted(b["t"] - a["t"] for a, b in zip(rows, rows[1:]))
    step = gaps[len(gaps) // 2] if gaps else 1.0
    for i in range(1, len(rows) - 3):
        a, b = rows[i], rows[i + 1]
        if b["t"] - a["t"] > 1.8 * step or (out and b["t"] - out[-1] < 30):   # a gap; or the same disturbance going
            continue                                                            # back, within 30 s: one event
        for axis, rms, lim in (("ra", ra, max_ra), ("dec", dec, max_dec)):
            d = (b[axis] - a[axis]) * scale
            if not rms or abs(d) <= max(GREMLIN * rms, 3.0) or abs(a[f"{axis}_ms"]) >= 0.5 * (lim or 1000):
                continue
            # it stays: the next two frames still off the same way by half the jump (one frame and back is a glitch),
            # and it starts from where the star was (the way back from a glitch is not a jump)
            if abs(a[axis] - rows[i - 1][axis]) * scale < abs(d) / 2 and all((rows[i + k][axis] - a[axis]) * scale * (1 if d > 0 else -1) > abs(d) / 2 for k in (2, 3)):
                out.append(b["t"])
                break
    return out


def _r(x):
    return round(x, 2) if x is not None else None


def parse(text: str) -> dict:
    """One guide log: its version, the guiding sessions (with ≥ 30 frames: a few seconds of a try are not a night),
    the calibrations and the Guiding Assistant's results."""
    lines = text.splitlines()
    out = {"version": "", "sessions": [], "calibrations": [], "assistant": [], "night": ""}
    if lines and (m := re.match(r"PHD2 version ([^,]+).*Log enabled at (\d{4}-\d\d-\d\d)", lines[0])):
        out["version"], out["night"] = m.group(1).strip(), m.group(2)
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("Guiding Begins at "):
            start, j, head = ln[18:].strip(), i + 1, []
            while j < len(lines) and not lines[j].startswith("Frame,"):
                head.append(lines[j])
                j += 1
            k = j
            while k < len(lines) and not lines[k].startswith("Guiding Ends"):
                k += 1
            body = lines[j:k]
            info = [(n, b[6:]) for n, b in enumerate(body) if b.startswith("INFO: ")]
            s = _session(start, head, body, info)
            s["assistant"] = any("MountGuidingEnabled = false" in x for _, x in info)   # the GA's unguided minutes
            if s["frames"] >= 30:
                out["sessions"].append(s)
            i = k + 1
            continue
        if m := re.match(r"(West|North) calibration complete\. Angle = ([\d.-]+) deg, Rate = ([\d.]+) px/sec", ln):
            out["calibrations"].append({"axis": "RA" if m.group(1) == "West" else "DEC", "angle": float(m.group(2)),
                                        "rate": float(m.group(3))})
        i += 1
    out["assistant"] = [ln[18:].strip() for ln in lines if ln.startswith("INFO: GA Result - ")]   # inside a session too
    out["advice"] = _assistant(out["assistant"])
    return out


def _assistant(lines: list[str]) -> dict:
    """The Guiding Assistant's numbers: polar alignment error, backlash, the minimum moves it advises."""
    a: dict = {}
    for ln in lines:
        if m := re.search(r"PA Error=\s*([\d.]+) arc-min", ln):
            a["pa_arcmin"] = float(m.group(1))
        if m := re.search(r"Backlash=\s*(\d+)", ln):
            a["backlash_ms"] = int(m.group(1))
        if m := re.search(r"backlash compensation of (\d+) ms", ln):
            a["backlash_advised_ms"] = int(m.group(1))
        if "Recommendation" in ln and (m := re.search(r"\b(Dec|DEC|AR|RA)\b[^\d]*?\b(?:a|to) ([\d.]+)\s*$", ln)):
            a["dec_min_move" if m.group(1).lower() == "dec" else "ra_min_move"] = float(m.group(2))
        if m := re.search(r"Total HPF-RMS=.*?\(\s*([\d.]+) arc-sec", ln):
            a["hpf_rms_arcsec"] = float(m.group(1))         # the star's own jitter: the floor of what guiding can do
    return a


def findings(log: dict, imaging_scale: float | None = None, flip: dict | None = None, advice: dict | None = None) -> list[dict]:
    """What Aurora reads in a night, as {level, code, numbers}: observations and proposals, never a change. flip: N.I.N.A.'s
    meridian flip settings (the inventory's); advice: the latest Guiding Assistant's, when this night ran none."""
    out, ss = [], log["sessions"]
    adv = log["advice"] or advice or {}
    after = _n((flip or {}).get("MinutesAfterMeridian"))
    for s in (x for x in ss if not x["assistant"]):
        for w in s["runaways"]:
            near = w.get("meridian_min") is not None and abs(w["meridian_min"]) <= 20
            out.append({"level": "high", "code": "runaway_meridian" if near else "runaway", "at": w.get("at"),
                        "axis": w["axis"].upper(), "rate": w["rate"], "min": w.get("meridian_min"),
                        "pier": s["settings"].get("pier"), "flip_after": after,
                        "flip_max": _n((flip or {}).get("MaxMinutesAfterMeridian"))})
        lim = s["settings"].get("max_ra_ms")
        if lim and s["counted"] and s["at_limit"]["ra"] / s["counted"] > 0.05 and not s["runaways"]:
            out.append({"level": "mid", "code": "ra_at_limit", "at": s["start"][11:16], "n": s["at_limit"]["ra"], "ms": lim})
        if s["counted"] and s["lost"] / (s["lost"] + s["counted"]) > 0.05:
            out.append({"level": "mid", "code": "star_lost", "at": s["start"][11:16], "n": s["lost"], "snr": s["snr"]})
        r = s["rms"]
        if imaging_scale and r["total"] and s["minutes"] >= 10 and r["total"] > imaging_scale:
            out.append({"level": "mid", "code": "rms_over_scale", "at": s["start"][11:16], "rms": r["total"], "scale": imaging_scale})
        if r["ra"] and r["dec"] and s["minutes"] >= 10 and max(r["ra"], r["dec"]) >= 2 * min(r["ra"], r["dec"]):
            # one axis 2–3× the other: stars elongate (B. Waddington, «Analyzing PHD2 guide logs»)
            out.append({"level": "mid", "code": "elongated", "at": s["start"][11:16], "ra": r["ra"], "dec": r["dec"],
                        "axis": "DEC" if r["dec"] > r["ra"] else "RA"})
        g = s.get("gremlins") or {}
        rate = g.get("n", 0) / (s["minutes"] / 60) if s["minutes"] >= 10 else 0
        if rate >= 3:                                     # a few an hour happen to anyone outdoors; ten is a cause
            out.append({"level": "mid" if rate >= 10 else "low", "code": "gremlins", "at": s["start"][11:16], "n": g["n"],
                        "per_h": round(rate, 1), "times": ", ".join(x for x in g["at"] if x)})
    if log["advice"].get("pa_arcmin", 0) > 5:             # this night's only: the alignment is redone each night
        out.append({"level": "mid", "code": "polar", "arcmin": adv["pa_arcmin"]})
    last = ss[-1]["settings"] if ss else {}
    if adv.get("backlash_advised_ms") and last and not last.get("backlash_on"):
        # low: on a strain-wave mount the assistant's backlash reads scatter (seen: 91 to 375 ms, ± 110, in three runs on one mount)
        out.append({"level": "low", "code": "backlash_off", "ms": adv["backlash_advised_ms"]})
    for k, axis in (("ra_min_move", "x_min_move"), ("dec_min_move", "y_min_move")):
        if adv.get(k) and last.get(axis) is not None and abs(last[axis] - adv[k]) > 0.02:
            out.append({"level": "low", "code": "min_move", "axis": "RA" if k[0] == "r" else "DEC", "now": last[axis], "advised": adv[k]})
    return out


def read(f: Path) -> dict:
    """One guide log read, by its modification time."""
    m = f.stat().st_mtime
    hit = _cache.get(str(f))
    if hit and hit[0] == m:
        return hit[1]
    d = parse(f.read_text(encoding="utf-8", errors="replace"))
    d["file"] = f.name
    _cache[str(f)] = (m, d)
    return d


def nights(folder: Path, imaging_scale: float | None = None, flip: dict | None = None, last: int = 12) -> list[dict]:
    """The latest guide logs of the folder, each with what Aurora reads in it (empty logs, a session under 30 frames, left
    out)."""
    out = []
    got = [dict(read(f)) for f in logs(folder)[:last]]
    for i, d in enumerate(got):                            # the latest assistant run before this night, when it ran none
        older = next((x["advice"] for x in got[i:] if x["advice"]), None)
        d["findings"] = findings(d, imaging_scale, flip, older)
        d["advice_from"] = d["night"] if d["advice"] else next((x["night"] for x in got[i:] if x["advice"]), None)
        if d["sessions"]:
            out.append(d)
    return out
