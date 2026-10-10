# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Two decks (owner, 10 Oct: «un classico remix su due brani… facendoti decidere un po' tutto, come farebbero i modelli
più blasonati online»): two tracks brought to one tempo and, if asked, one key, then either MIXED — A, and B coming in
on A's beat at the bar chosen, over 4-32 bars, by a crossfade, a bass swap, a filter sweep or an echo out — or
MASHED UP — A over B for the whole length. Optionally the DJ's beat of a style over the result (aud_dj.remix).

Every choice is the user's (opts); «auto» picks what a DJ would: A's tempo, B in A's key, the transition where A's last
quarter starts, 16 bars, a bass swap. The beats are followed one by one on both decks (aud_analysis.track, M180), so
B's first downbeat lands on one of A's.
The mashup is an EQ mashup: A without its lows (its kick and bass), B with room cut in the middle for A's voice. A
true mashup separates each track's voice from its music (stems: a separation model such as Demucs), which Aurora
does not have yet — said in the result.
"""
from __future__ import annotations

import subprocess

import numpy as np

from . import aud_analysis as A
from . import aud_synth as S
from .aud_analysis import SR

TRANSITIONS = ("crossfade", "bass_swap", "filter", "echo")
DEFAULTS = {"mode": "mix", "bpm": "a", "key": "match", "at": "auto", "bars": 16, "transition": "bass_swap",
            "drums": "none", "style": "house", "gain_a": 0.0, "gain_b": 0.0}


def options(opts: dict | None) -> dict:
    """The user's choices checked, «auto» where they left them."""
    o = {**DEFAULTS, **{k: v for k, v in (opts or {}).items() if v not in (None, "")}}
    if o["mode"] not in ("mix", "mashup"):
        raise ValueError("mode: mix or mashup")
    if o["key"] not in ("match", "keep"):
        raise ValueError("key: match or keep")
    if o["transition"] not in TRANSITIONS:
        raise ValueError(f"transition: one of {', '.join(TRANSITIONS)}")
    if o["drums"] not in ("none", "light", "full"):
        raise ValueError("drums: none, light or full")
    if int(o["bars"]) not in (4, 8, 16, 32):
        raise ValueError("bars: 4, 8, 16 or 32")
    if str(o["bpm"]) not in ("a", "b", "style"):
        bpm = float(o["bpm"])
        if not 60 <= bpm <= 200:
            raise ValueError("bpm: a, b, style, or 60-200")
    for g in ("gain_a", "gain_b"):
        if not -24 <= float(o[g]) <= 12:
            raise ValueError(f"{g}: -24 to +12 dB")
    return o


def semitones(a: A.Info, b: A.Info) -> int:
    """The smallest shift that puts B in A's key (a minor key compared through its relative major): -6..+5."""
    ra = (a.key + 3) % 12 if a.minor else a.key
    rb = (b.key + 3) % 12 if b.minor else b.key
    d = (ra - rb) % 12
    return d - 12 if d > 5 else d


def _near(bpm: float, target: float) -> float:
    """The tempo ratio, a track at half or double time taken at the nearer one."""
    r = target / bpm
    for k in (1.0, 2.0, 0.5):
        if 0.7 <= target / (bpm * k) <= 1.45:
            return target / (bpm * k)
    return r


def shift(x: np.ndarray, tempo: float, steps: int) -> np.ndarray:
    """Tempo and pitch at once (ffmpeg's rubberband): the key moved by whole semitones, the length by the tempo."""
    if abs(tempo - 1.0) < 0.005 and not steps:
        return x
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-af", f"rubberband=tempo={tempo:.5f}:pitch={2 ** (steps / 12):.6f}", "-f", "f32le", "-"],
                       input=np.ascontiguousarray(x, np.float32).tobytes(), capture_output=True, timeout=900)
    if not r.stdout:
        raise RuntimeError(f"tempo/pitch change failed: {r.stderr.decode(errors='replace')[-200:]}")
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


def _swept(x: np.ndarray, kind: str, start_hz: float, end_hz: float, pieces: int = 32) -> np.ndarray:
    """A filter whose cutoff moves (exponentially) over the whole of x: pieces filtered and joined with short fades."""
    n = len(x)
    out = np.zeros_like(x)
    edges = np.linspace(0, n, pieces + 1).astype(int)
    fade = min(512, max(1, n // pieces // 4))
    for i in range(pieces):
        hz = start_hz * (end_hz / start_hz) ** (i / max(1, pieces - 1))
        a, z = max(0, edges[i] - fade), min(n, edges[i + 1] + fade)
        y = (S.highpass if kind == "high" else S.lowpass)(x[a:z], min(hz, SR / 2 - 100))
        w = np.ones(z - a, np.float32)
        if a > 0:
            w[: 2 * fade] = np.linspace(0, 1, 2 * fade)
        if z < n:
            w[-2 * fade:] = np.linspace(1, 0, 2 * fade)
        out[a:z] += y * w[:, None]
    return out


def _transition(a: np.ndarray, b: np.ndarray, kind: str, beat: float) -> np.ndarray:
    """The overlap: A's end and B's start, the same length, into one."""
    n = len(a)
    t = np.linspace(0, 1, n, dtype=np.float32)[:, None]
    if kind == "crossfade":                                    # equal power
        return a * np.cos(t * np.pi / 2) + b * np.sin(t * np.pi / 2)
    if kind == "bass_swap":                                    # highs crossfade; the lows swap at the half, on a beat
        la, lb = S.lowpass(a, 150), S.lowpass(b, 150)
        half = int(round(n / 2 / (beat * SR)) * beat * SR) if beat else n // 2
        lows = np.concatenate([la[:half], lb[half:]])
        return (a - la) * (1 - t) + (b - lb) * t + lows
    if kind == "filter":                                       # A thinned away from below, B opened from above
        return _swept(a, "high", 30, 4000) * (1 - t ** 3) + _swept(b, "low", 250, 18000) * np.minimum(1, t * 1.5)
    # echo out: A's last beat repeated with feedback, fading, while B comes in
    d, out = int(beat * SR), a * np.clip(1 - t * 4, 0, 1)
    tail = np.zeros_like(a)
    seed = a[: min(n, d)]
    for k, g in enumerate((0.6, 0.4, 0.25, 0.15)):
        at = (k + 1) * d
        if at < n:
            tail[at: at + len(seed)] += seed[: n - at] * g
    return out + S.highpass(tail, 300) + b * np.minimum(1, t * 2)


def blend(xa: np.ndarray, xb: np.ndarray, opts: dict | None = None, emit=None) -> tuple[np.ndarray, dict]:
    """Two tracks into one, as the user chose (options()); the audio and what was done."""
    from . import aud_dj
    o = options(opts)
    say = emit or (lambda e, p: None)
    ia, ib = A.analyze(xa), A.analyze(xb)
    say("dj.analysis", {"a": ia.as_dict(), "b": ib.as_dict()})
    target = {"a": ia.bpm, "b": ib.bpm, "style": aud_dj.STYLES[o["style"]]["bpm"] or ia.bpm}.get(str(o["bpm"]))
    target = float(target or o["bpm"])
    ra, rb = _near(ia.bpm, target), _near(ib.bpm, target)
    steps = semitones(ia, ib) if o["key"] == "match" else 0
    xa = shift(xa, ra, 0) * 10 ** (float(o["gain_a"]) / 20)
    xb = shift(xb, rb, steps) * 10 ** (float(o["gain_b"]) / 20)
    beat = 60.0 / target
    ba = ia.beats / ra if ia.steady and len(ia.beats) >= 8 else ia.first_beat / ra + np.arange(int(len(xa) / SR / beat)) * beat
    bb = ib.beats / rb if ib.steady and len(ib.beats) >= 8 else ib.first_beat / rb + np.arange(int(len(xb) / SR / beat)) * beat
    note = {"bpm": round(target, 1), "key_a": ia.as_dict()["key"], "key_b": ib.as_dict()["key"], "b_semitones": steps,
            "a_steady": ia.steady, "b_steady": ib.steady, "mode": o["mode"]}
    if o["mode"] == "mashup":
        # A over B from B's first downbeat: A without its lows, B with its middle lowered to make room for A's voice
        lead = max(0, int((bb[0] - ba[0]) * SR)) if len(ba) and len(bb) else 0
        n = min(len(xa) + lead, len(xb))
        a = np.zeros((n, 2), np.float32)
        a[lead:] = S.highpass(xa, 220)[: n - lead]
        b = xb[:n] - 0.45 * S.lowpass(S.highpass(xb[:n], 300), 3000)
        out = a + b
        note["mashup"] = "EQ (no stems: A's lows away, room in B's middle)"
    else:
        bars = int(o["bars"])
        if o["at"] == "auto":                                  # A's last quarter, on a bar
            k = max(0, int(len(ba) * 0.75) // 4 * 4)
        else:
            k = max(0, int(float(o["at"]) / beat) // 4 * 4)
        k = min(k, max(0, len(ba) - 1))
        start = int((ba[k] if len(ba) else k * beat) * SR)
        b0 = int((bb[0] if len(bb) else 0.0) * SR)             # B's first downbeat lands on A's beat k
        over = int(bars * 4 * beat * SR)
        over = max(1, min(over, len(xa) - start, len(xb) - b0))
        mixed = _transition(xa[start: start + over], xb[b0: b0 + over], o["transition"], beat)
        out = np.concatenate([xa[:start], mixed, xb[b0 + over:]])
        note.update(transition=o["transition"], at_seconds=round(start / SR, 1), bars=bars)
    if o["drums"] != "none":
        out, r = aud_dj.remix(out, o["style"], bpm=target, drums_level=0.5 if o["drums"] == "light" else 1.0, emit=emit)
        note["drums"] = f"{o['drums']} ({o['style']})"
    peak = float(np.max(np.abs(out))) or 1.0
    out = S.saturate(out / peak * 1.05, 1.1) * 0.95
    return out.astype(np.float32), {**note, "seconds": round(len(out) / SR, 1)}
