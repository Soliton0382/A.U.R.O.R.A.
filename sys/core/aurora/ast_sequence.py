# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The imaging program's sequences read back (ROADMAP N28): an advanced sequence of N.I.N.A. (its .json, added to the
astro folder) as what it will do — the targets with their coordinates, the exposures with gain and offset, the cooling,
whether it guides, focuses, dithers and flips — and checked against the darks' library and the camera's settings: a
sequence at an offset no dark has is found before the night, not after. Read only: a sequence is never written here."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = "SequenceRootContainer"


def _kind(n: dict) -> str:
    return str(n.get("$type", "")).split(",")[0].split(".")[-1]


def _walk(n, out: list) -> None:
    if isinstance(n, dict):
        if n.get("$type"):
            out.append(n)
        for k, v in n.items():
            if k != "Parent" and isinstance(v, (dict, list)):
                _walk(v, out)
    elif isinstance(n, list):
        for x in n:
            _walk(x, out)


def is_sequence(f: Path) -> bool:
    if f.suffix.lower() != ".json" or f.stat().st_size > 5_000_000:
        return False
    try:
        with f.open(encoding="utf-8-sig", errors="replace") as h:
            return ROOT in h.read(400)
    except OSError:
        return False


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse(text: str, name: str = "") -> dict:
    """One sequence: what it will do. Gain or offset -1 is the camera's own setting (N.I.N.A.'s profile)."""
    nodes: list[dict] = []
    _walk(json.loads(text), nodes)
    out = {"name": name, "targets": [], "exposures": [], "cool_c": None, "flip": False, "guiding": False,
           "autofocus": False, "dither_every": None}
    for n in nodes:
        k = _kind(n)
        if k == "DeepSkyObjectContainer":
            c = (n.get("Target") or {}).get("InputCoordinates") or {}
            ra = _num(c.get("RAHours"))
            if ra is not None:
                ra += (_num(c.get("RAMinutes")) or 0) / 60 + (_num(c.get("RASeconds")) or 0) / 3600
            dec = _num(c.get("DecDegrees"))
            if dec is not None:
                sign = -1 if c.get("NegativeDec") or dec < 0 else 1
                dec = sign * (abs(dec) + (_num(c.get("DecMinutes")) or 0) / 60 + (_num(c.get("DecSeconds")) or 0) / 3600)
            out["targets"].append({"name": (n.get("Target") or {}).get("TargetName") or n.get("Name") or "",
                                   "ra_h": round(ra, 4) if ra is not None else None,
                                   "dec_deg": round(dec, 3) if dec is not None else None})
        elif k == "TakeExposure" and str(n.get("ImageType", "LIGHT")).upper() == "LIGHT":
            e = {"s": _num(n.get("ExposureTime")), "gain": _num(n.get("Gain")), "offset": _num(n.get("Offset"))}
            if e not in out["exposures"]:
                out["exposures"].append(e)
        elif k == "CoolCamera":
            out["cool_c"] = _num(n.get("Temperature"))
        elif k == "MeridianFlipTrigger":
            out["flip"] = True
        elif k == "StartGuiding":
            out["guiding"] = True
        elif k.startswith("RunAutofocus") or k.startswith("AutofocusAfter"):
            out["autofocus"] = True
        elif k == "DitherAfterExposures":
            out["dither_every"] = int(_num(n.get("AfterExposures")) or 0) or None
    return out


def sequences(folder: Path) -> list[dict]:
    """The sequences of the folder, newest first; one that does not read is said, not raised."""
    out = []
    files = [f for f in folder.iterdir() if f.is_file() and is_sequence(f)] if folder.is_dir() else []
    for f in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            d = parse(f.read_text(encoding="utf-8-sig", errors="replace"), f.stem)
        except (ValueError, RecursionError) as e:
            d = {"name": f.stem, "error": str(e)[:120]}
        d["file"] = f.name
        out.append(d)
    return out


def check(seq: dict, rig: dict, darks: list[dict]) -> list[dict]:
    """A sequence against the camera's settings and the darks' library, as {level, code, numbers}."""
    out = []
    gain0, off0 = _num(rig.get("gain")), _num(rig.get("offset"))
    usable = [d for d in darks if not d.get("old")]
    for e in seq.get("exposures", []):
        g = gain0 if e["gain"] in (None, -1) else e["gain"]
        o = off0 if e["offset"] in (None, -1) else e["offset"]
        if usable and o is not None and not any(_num(d.get("offset")) == o for d in usable):
            near = sorted({_num(d.get("offset")) for d in usable if d.get("offset") is not None})
            out.append({"level": "high", "code": "seq_offset", "s": e["s"], "offset": o, "darks": near})
        elif usable and g is not None and not any(_num(d.get("gain")) == g for d in usable):
            out.append({"level": "high", "code": "seq_gain", "s": e["s"], "gain": g})
        elif usable and e["s"] and not any(_num(d.get("exposure_s")) == e["s"] and _num(d.get("gain")) == g
                                           and _num(d.get("offset")) == o for d in usable):
            out.append({"level": "mid", "code": "seq_no_dark", "s": e["s"], "gain": g, "offset": o})
    cool = rig.get("cooling_c")
    if seq.get("cool_c") is not None and cool is not None and seq["cool_c"] != cool:
        out.append({"level": "mid", "code": "seq_cool", "c": seq["cool_c"], "profile": cool})
    for k in ("flip", "guiding", "autofocus"):
        if seq.get("exposures") and not seq.get(k):
            out.append({"level": "mid" if k != "autofocus" else "low", "code": f"seq_no_{k}"})
    return out
