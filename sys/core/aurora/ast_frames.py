# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The single frames of a night (ROADMAP N28): lights, flats, darks and dark-flats as the imaging program saved them
(XISF uncompressed, or FITS), found in the person's frames folder (AURORA_ASTRO_FRAMES_DIR, read only) by their
header — kind, exposure, gain, offset, filter, temperature, Bayer pattern, date — and their pixels read when a
measure needs them (ast_sensor). A camera writes whole numbers: an image in floating point is an integration (the
darks' library's, a stack), not a frame, and is left out."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

SUFFIX = (".xisf", ".fits", ".fit", ".fts")
KEYS = ("IMAGETYP", "EXPTIME", "EXPOSURE", "GAIN", "OFFSET", "FILTER", "CCD-TEMP", "BAYERPAT", "DATE-OBS", "XBINNING")
KIND = {"light": "light", "flat": "flat", "dark": "dark", "darkflat": "darkflat", "flatdark": "darkflat", "bias": "bias"}


def _num(x):
    try:
        return float(str(x).strip("' "))
    except (TypeError, ValueError):
        return None


def header(f: Path) -> dict | None:
    """The keywords that matter and where the pixels are; None when the file is not a single uncompressed 2-D frame."""
    with f.open("rb") as fh:
        head = fh.read(262144)
    kw: dict = {}
    if head.startswith(b"XISF0100"):
        xml = head[16:].decode("utf-8", "replace")
        tag = re.search(r"<Image [^>]*>", xml)
        if not tag or "compression=" in tag.group(0):
            return None
        g = re.search(r'geometry="(\d+):(\d+):(\d+)"', tag.group(0))
        fmt = re.search(r'sampleFormat="(\w+)"', tag.group(0))
        loc = re.search(r'location="attachment:(\d+):(\d+)"', tag.group(0))
        if not (g and fmt and loc) or g.group(3) != "1":
            return None
        for k, v in re.findall(r'<FITSKeyword name="([A-Z0-9_-]+)" value="([^"]*)"', xml):
            kw.setdefault(k, v.strip("' "))
        it = re.search(r'imageType="(\w+)"', tag.group(0))
        if it:
            kw.setdefault("IMAGETYP", it.group(1))
        px = {"w": int(g.group(1)), "h": int(g.group(2)), "dtype": {"UInt16": "<u2", "Float32": "<f4"}.get(fmt.group(1)),
              "offset": int(loc.group(1)), "scale": 65535.0 if fmt.group(1) == "Float32" else 1.0, "bzero": 0.0}
    else:
        cards, end = {}, None
        for i in range(0, len(head) - 80, 80):
            card = head[i:i + 80].decode("ascii", "replace")
            k = card[:8].strip()
            if k == "END":
                end = i + 80
                break
            if card[8:10] == "= ":
                cards[k] = card[10:].split("/")[0].strip().strip("' ")
        if end is None or cards.get("NAXIS") != "2" or cards.get("BITPIX") not in ("16", "-32"):
            return None
        kw = cards
        px = {"w": int(cards["NAXIS1"]), "h": int(cards["NAXIS2"]), "dtype": ">i2" if cards["BITPIX"] == "16" else ">f4",
              "offset": -(-end // 2880) * 2880, "scale": 1.0, "bzero": _num(cards.get("BZERO")) or 0.0}
    if not px["dtype"]:
        return None
    kind = re.sub(r"[^a-z]", "", str(kw.get("IMAGETYP", "")).lower().replace("frame", ""))
    return {"kind": KIND.get(kind, kind or "unknown"), "exposure_s": _num(kw.get("EXPTIME") or kw.get("EXPOSURE")),
            "gain": _num(kw.get("GAIN")), "offset": _num(kw.get("OFFSET")), "filter": str(kw.get("FILTER", "")).strip(),
            "temp_c": _num(kw.get("CCD-TEMP")), "bayer": str(kw.get("BAYERPAT", "")).strip().upper(),
            "date": str(kw.get("DATE-OBS", ""))[:10], "binning": _num(kw.get("XBINNING")) or 1.0, "pixels": px}


def pixels(f: Path, h: dict) -> np.ndarray:
    """The frame in 16-bit ADU (float), as the camera wrote it."""
    p = h["pixels"]
    a = np.fromfile(f, dtype=p["dtype"], count=p["w"] * p["h"], offset=p["offset"]).reshape(p["h"], p["w"])
    return a.astype(np.float64) * p["scale"] + p["bzero"]


def scan(folder: Path, limit: int = 5000) -> list[dict]:
    """The single frames under the folder (three levels down), each with its header; integrations left out."""
    out = []
    if not folder.is_dir():
        return out
    for f in sorted(folder.rglob("*")):
        if len(out) >= limit:
            break
        if not f.is_file() or f.suffix.lower() not in SUFFIX or len(f.relative_to(folder).parts) > 4:
            continue
        try:
            h = header(f)
        except (OSError, ValueError, KeyError):
            continue
        if h and h["pixels"]["dtype"] in ("<u2", ">i2"):           # whole numbers: a frame, not an integration
            h["file"] = str(f)
            h["mtime"] = f.stat().st_mtime
            out.append(h)
    return out


def channels(a: np.ndarray, bayer: str, centre: bool = True) -> dict[str, np.ndarray]:
    """The colour channels of a raw frame (or the whole frame, «L», when it has no Bayer pattern); the centre half,
    from an even row and column so the pattern keeps its phase."""
    if centre:
        y0, x0 = a.shape[0] // 8 * 2, a.shape[1] // 8 * 2
        a = a[y0: y0 + a.shape[0] // 4 * 2, x0: x0 + a.shape[1] // 4 * 2]
    if len(bayer) != 4 or set(bayer) - set("RGB"):
        return {"L": a}
    pos = {(0, 0): bayer[0], (0, 1): bayer[1], (1, 0): bayer[2], (1, 1): bayer[3]}
    out: dict[str, list] = {}
    for (dy, dx), c in pos.items():
        out.setdefault(c, []).append(a[dy::2, dx::2])
    return {c: (v[0] if len(v) == 1 else np.vstack(v)) for c, v in out.items()}      # the two greens one above the other
