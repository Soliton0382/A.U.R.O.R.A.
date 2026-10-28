# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎓 The DJ learns a style from a radio (owner, 29 Oct 2026: «sfruttare il recording temporaneo per dire al dj aurora
lo stile da usare… recording usa e getta per delineare i pattern da poter riutilizzare… un tasto tipo impara stile»).

A few minutes of the station the user listens to are taken through Aurora (aud_radio, net_public: a public address
only), decoded in memory and never written: what is kept is a style of the DJ's own kind (aud_dj.STYLES) — numbers,
no sound. From the beats followed (aud_analysis), each bar of four beats is cut into the 16 steps the DJ plays on, and
the onsets of four bands are averaged on them: the kick (< 150 Hz), the bass (60-250 Hz, off the kick's steps), the
clap or snare (1-4 kHz), the hats (> 7 kHz; dense = closed). The bar's first beat is the one that puts the claps on
the second and fourth. A held middle band says a pad; the dip of the middle after each kick says how much the music
pumps; the crest of the signal how hard it is driven; a dark spectrum a low-pass. The audio is let go once read.

The styles learnt are the user's (dj_styles.json in their music folder): «learned-<name>», offered beside the DJ's
own, deleted when they want. Nothing of the tracks heard goes into a mix: the DJ plays its own drums and bass.

record(sid, seconds)   the station's audio, in memory
learn(x)               the style read from it
save / load / delete   the user's styles learnt
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from . import aud_analysis as A
from .aud_analysis import HOP, SR, WIN

SECONDS = (45, 900)                                      # how long a listen may be: a whole track and more
SHORTEST = 30                                            # «Fine» pressed early: at least this much heard
MAX_BYTES = 40 * 2**20                                   # a 320 kb/s station for 900 s is 36 MB
FILE = "dj_styles.json"
PREFIX = "learned-"
NAME = re.compile(r"[^\w-]+")


def record(sid: str, seconds: float, stop=None) -> tuple[np.ndarray, str]:
    """(stereo float32 at 44.1 kHz, the station's name): `seconds` of the stream, decoded in memory; `stop` (an
    Event) set by the user's «Fine» ends the listen there (ValueError if less than SHORTEST was heard)."""
    from . import aud_radio, net_public
    seconds = max(SECONDS[0], min(SECONDS[1], float(seconds)))
    url, name = aud_radio.stream_url(sid)
    client, r = net_public.open_stream(url, False, 20, aud_radio.UA)
    buf = bytearray()
    try:
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith(("audio/", "application/ogg")):
            raise ValueError(f"the station answered {r.status_code} {r.headers.get('content-type', '')}")
        t0 = time.monotonic()
        for chunk in r.iter_raw(16384):
            buf += chunk
            if time.monotonic() - t0 >= seconds or len(buf) >= MAX_BYTES or (stop is not None and stop.is_set()):
                break
        if stop is not None and stop.is_set() and time.monotonic() - t0 < SHORTEST:
            raise ValueError(f"stopped after less than {SHORTEST} s: too little to learn from")
    finally:
        r.close()
        client.close()
    out = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn", "-ac", "2", "-ar",
                          str(SR), "-f", "f32le", "-"], input=bytes(buf), capture_output=True, timeout=120)
    buf[:] = b""                                         # the compressed stream let go at once
    if not out.stdout:
        raise ValueError("the station's audio could not be read")
    return np.frombuffer(out.stdout, np.float32).reshape(-1, 2).copy(), name


def _steps(beats: np.ndarray, first: int) -> np.ndarray:
    """The frame of each of the 16 steps of every whole bar from beat `first`: shape (bars, 16)."""
    fps, offset = SR / HOP, (HOP + WIN / 2) / SR
    rows = []
    for b in range(first, len(beats) - 4, 4):
        times = [beats[b + j] + k * (beats[b + j + 1] - beats[b + j]) / 4 for j in range(4) for k in range(4)]
        rows.append(np.round((np.array(times) - offset) * fps).astype(int))
    return np.array(rows)


def _grid(env: np.ndarray, frames: np.ndarray) -> np.ndarray:
    """The band's onsets on the 16 steps, averaged over the bars (the strongest of ±1 frame), scaled to its top."""
    near = np.max([env[np.clip(frames + d, 0, len(env) - 1)] for d in (-1, 0, 1)], axis=0)
    g = near.mean(axis=0)
    return g / g.max() if g.max() > 0 else g


def _pattern(g: np.ndarray, share: float) -> list[int]:
    """The steps that stand out: at least `share` of the strongest, and above the bar's average."""
    return [i for i, v in enumerate(g) if v >= share and v > g.mean()]


def steady_part(x: np.ndarray, window: float = 30.0) -> np.ndarray | None:
    """The longest stretch of the listen whose beat is steady, in windows of `window` seconds half overlapping (the
    station's first listen, 29 Oct: steady in the middle, 0.005-0.02, not across a change of track at the ends, and
    the whole at 0.05 — just over the line); None when no window is."""
    w, hop = int(window * SR), int(window * SR / 2)
    flags = [A.analyze(x[i:i + w]).steady for i in range(0, max(1, len(x) - w + 1), hop)]
    best, run = (0, -1), 0
    for k, ok in enumerate(flags):
        run = run + 1 if ok else 0
        if run and run > best[1] - best[0] + 1:
            best = (k - run + 1, k)
    if best[1] < 0:
        return None
    return x[best[0] * hop: best[1] * hop + w]


def learn(x: np.ndarray) -> dict:
    """The style of a listen (ValueError when there is no steady beat to learn from): of the whole when it is steady,
    else of its longest steady stretch."""
    info = A.analyze(x)
    if not info.steady or len(info.beats) < 33:
        part = steady_part(x)
        if part is not None:
            x, info = part, A.analyze(part)
    if not info.steady or len(info.beats) < 33:
        raise ValueError("no steady beat to learn from: try a station with a clear rhythm, or a longer listen")
    mono = x.mean(axis=1)
    spec = A._spectrogram(mono)
    f = np.fft.rfftfreq(WIN, 1 / SR)
    env = {name: A.onsets(spec[:, mask]) for name, mask in (
        ("kick", f < 150), ("bass", (f >= 60) & (f < 250)), ("clap", (f >= 1000) & (f < 4000)), ("hat", f >= 7000))}
    beats = np.asarray(info.beats)
    best = None                                          # the bar's first beat: claps on the 2nd and the 4th
    for first in range(4):
        frames = _steps(beats, first)
        c = _grid(env["clap"], frames)
        score = c[[4, 12]].sum() - c[[0, 8]].sum()
        if best is None or score > best[0]:
            best = (score, frames)
    frames = best[1]
    g = {name: _grid(e, frames) for name, e in env.items()}
    kick = _pattern(g["kick"], 0.8)                     # the bass shares the band: the kick is the strongest there
    clap = _pattern(g["clap"], 0.55)
    hats = [i for i, v in enumerate(g["hat"]) if v >= 0.25]
    closed = hats if len(hats) >= 8 else []             # a dense hat line: the closed hats
    hat = [s for s in _pattern(g["hat"], 0.7) if s not in kick]
    bass = [s for s in _pattern(np.where(np.isin(np.arange(16), kick), 0, g["bass"]), 0.5)]
    mids = spec[:, (f >= 300) & (f < 3000)].sum(axis=1)
    held = float(np.percentile(mids, 10) / (np.median(mids) + 1e-9))      # a pad keeps the middle from falling
    beat = float(np.median(np.diff(beats))) * SR / HOP   # frames in a beat
    at = frames[:, kick].ravel() if kick else np.zeros(0, int)
    at = at[(at >= 0) & (at + int(0.5 * beat) < len(mids))]
    early, late = mids[at + int(0.1 * beat)], mids[at + int(0.45 * beat)]   # just after each kick, and before the next
    pump = float(np.clip(1 - early.mean() / (late.mean() + 1e-9), 0, 0.7)) if len(at) else 0.0
    rms = float(np.sqrt(np.mean(mono ** 2)) + 1e-9)
    crest = float(np.max(np.abs(mono)) / rms)
    power = spec.mean(axis=0) ** 2
    centroid = float((f * power).sum() / (power.sum() + 1e-9))
    st = {"bpm": round(float(np.clip(info.bpm, 60, 200)), 1), "kick": kick, "clap": clap, "hat": hat,
          "closed": closed, "bass": bass, "bass_len": 0.25 if len(bass) >= 8 else 0.5 if len(bass) >= 4 else 0.9,
          "pad": held > 0.45, "pump": round(pump, 2), "orig": 0.85,
          "drive": round(float(np.clip(1 + (8 - crest) / 8, 1.0, 1.6)), 2),
          "key": [info.key, info.minor], "learned": {"pulse": round(float(info.confidence), 1), "held": round(held, 2),
                                                     "crest": round(crest, 1), "centroid_hz": round(centroid)}}
    if st["pad"]:
        st["pad_level"] = round(float(np.clip(0.06 + 0.12 * (held - 0.45) / 0.55, 0.06, 0.16)), 2)
    if centroid < 1200:
        st["lowpass"] = 4000
    return st


def describe(st: dict) -> str:
    """A style learnt, in musical words (for a song: the music model takes words, not step grids)."""
    k, c, h, b = (list(st.get(x) or []) for x in ("kick", "clap", "hat", "bass"))
    parts = [f"{st.get('bpm')} BPM"]
    parts.append("four-on-the-floor kick" if k == [0, 4, 8, 12] else f"kick on steps {k} of 16" if k else "no kick")
    if c == [4, 12]:
        parts.append("claps on two and four")
    elif c:
        parts.append(f"claps on steps {c} of 16")
    if h and all(s % 4 == 2 for s in h):
        parts.append("open hi-hats on the off-beats")
    if len(st.get("closed") or []) >= 8:
        parts.append("busy closed hi-hats")
    if b:
        parts.append("rolling sixteenth bass" if len(b) >= 8 else "off-beat bass" if all(s % 4 == 2 for s in b) else "syncopated bass")
    if st.get("pad"):
        parts.append("lush sustained pads")
    if (st.get("pump") or 0) >= 0.4:
        parts.append("strong sidechain pumping")
    elif (st.get("pump") or 0) >= 0.15:
        parts.append("light sidechain pumping")
    if (st.get("drive") or 1) >= 1.3:
        parts.append("driven, saturated sound")
    if st.get("lowpass"):
        parts.append("dark, filtered top end")
    return ", ".join(parts)


def _file(folder: Path) -> Path:
    return Path(folder) / FILE


def load(folder: Path) -> dict[str, dict]:
    try:
        data = json.loads(_file(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k.startswith(PREFIX) and isinstance(v, dict)}


def save(folder: Path, name: str, style: dict, station: str) -> str:
    """The style kept under the user's name for it; returns its id."""
    label = " ".join(str(name or station or "").split())[:60] or "radio"
    sid = PREFIX + (NAME.sub("-", label.lower()).strip("-")[:40] or "radio")
    mine = load(folder)
    mine[sid] = {**style, "it": f"🎓 {label}", "en": f"🎓 {label}", "station": station[:120], "at": time.time()}
    f = _file(folder)
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(mine, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(f)
    return sid


def delete(folder: Path, sid: str) -> bool:
    mine = load(folder)
    if mine.pop(sid, None) is None:
        return False
    _file(folder).write_text(json.dumps(mine, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
