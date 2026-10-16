# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The single frames of a night (ROADMAP N28): lights, flats, darks and dark-flats as the imaging program saved them
(XISF uncompressed, or FITS), found in the person's frames folder (AURORA_ASTRO_FRAMES_DIR, read only) by their
header — kind, exposure, gain, offset, filter, temperature, Bayer pattern, date — and their pixels read when a
measure needs them (ast_sensor). A camera writes whole numbers: an image in floating point is an integration (the
darks' library's, a stack), not a frame, and is left out."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

MOUNT = Path("/mnt/aurora-astro")                  # where aurora-mount puts a NAS frames folder, read only (N29)
SUFFIX = (".xisf", ".fits", ".fit", ".fts")
HEAD, MAX_HEAD = 16384, 262144                   # a header read in pieces, never past 256 KB
KEYS = ("IMAGETYP", "EXPTIME", "EXPOSURE", "GAIN", "OFFSET", "FILTER", "CCD-TEMP", "BAYERPAT", "DATE-OBS", "XBINNING")
KIND = {"light": "light", "flat": "flat", "dark": "dark", "darkflat": "darkflat", "flatdark": "darkflat", "bias": "bias"}


def _num(x):
    try:
        return float(str(x).strip("' "))
    except (TypeError, ValueError):
        return None


def local(raw: str, mount: Path = MOUNT) -> tuple[Path | None, str]:
    """The frames folder on this machine and, when there is none, why: a NAS folder (smb://host/share/sub) is its
    share mounted by aurora-mount; a NAS asleep is said at once, never a wait on a hanging mount (C125)."""
    raw = raw.strip()
    if not raw.startswith("smb://"):
        return Path(raw), ""
    from aurora import sys_backup as B
    if not B.nas_reachable(raw):
        return None, f"the NAS ({raw[6:].split('/')[0]}) does not answer: off or asleep"
    if not B.mounted(mount):
        return None, f"the NAS frames folder is not mounted on {mount}: save the folder again (it mounts it)"
    sub = "/".join(raw[6:].strip("/").split("/")[2:])
    return (mount / sub if sub else mount), ""


def header(f: Path) -> dict | None:
    """The keywords that matter and where the pixels are; None when the file is not a single uncompressed 2-D frame."""
    with f.open("rb") as fh:                       # only the header: a frame over the network is megabytes
        head = fh.read(HEAD)
        if head.startswith(b"XISF0100"):
            size = 16 + int.from_bytes(head[8:12], "little")
            if size > len(head):
                head += fh.read(min(size, MAX_HEAD) - len(head))
        else:
            while b"END     " not in head and len(head) < MAX_HEAD and len(more := fh.read(HEAD)):
                head += more
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


def _files(folder: Path, depth: int):
    """The frame files under the folder, `depth` levels at most, in name order: the folders deeper are never walked
    (a NAS share of years of nights), nor hidden ones and a NAS's own (#recycle, @eaDir)."""
    import os
    for top, dirs, names in os.walk(folder):
        level = len(Path(top).relative_to(folder).parts)
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "#", "@"))) if level < depth - 1 else []   # NAS bins
        for n in sorted(names):
            if n.lower().endswith(SUFFIX):
                yield Path(top) / n


def scan(folder: Path, limit: int = 5000, cache: Path | None = None) -> list[dict]:
    """The single frames under the folder (three levels down), each with its header; integrations left out. With a
    cache file a header is read again only when its file changed (size, time): on a NAS a header is a round trip."""
    out = []
    if not folder.is_dir():
        return out
    try:
        known = json.loads(cache.read_text(encoding="utf-8")) if cache else {}
    except (OSError, ValueError):
        known = {}
    seen = {}
    for f in _files(folder, 4):
        if len(out) >= limit:
            break
        try:
            st = f.stat()
            k = known.get(str(f))
            if k and k["size"] == st.st_size and k["mtime"] == st.st_mtime:
                h = k["h"]
            else:
                h = header(f)
                h = h and {**h, "file": str(f), "mtime": st.st_mtime}
        except (OSError, ValueError, KeyError):
            continue
        seen[str(f)] = {"size": st.st_size, "mtime": st.st_mtime, "h": h}
        if h and h["pixels"]["dtype"] in ("<u2", ">i2"):           # whole numbers: a frame, not an integration
            out.append(h)
    if cache and seen != known:
        try:
            cache.write_text(json.dumps(seen), encoding="utf-8")
        except OSError:
            pass
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
