# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The DJ's instruments, drawn with numpy (owner, 2026-10-05): a kick, a clap, hats, a snare, a bass and a pad in the
track's key, and the effects a remix needs — a sidechain pump, a filter, a saturation, a noise riser.

Nothing is sampled from anyone: every sound is made here, so a remix carries no one else's samples.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

from .aud_analysis import SR

RNG = np.random.default_rng(7)


def _env(n: int, decay_s: float) -> np.ndarray:
    return np.exp(-np.arange(n) / (decay_s * SR))


def kick(level: float = 1.0, punch: float = 1.0) -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    freq = 45 + 110 * punch * np.exp(-t * 28)                      # a falling pitch: the thump
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * _env(n, 0.16)
    click = RNG.normal(0, 0.3, n) * _env(n, 0.003)
    return (level * np.tanh(1.6 * (body + click))).astype(np.float32)


def _band(noise: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return sosfilt(butter(4, [lo, hi], btype="band", fs=SR, output="sos"), noise)


def clap(level: float = 0.55) -> np.ndarray:
    n = int(0.25 * SR)
    burst = np.zeros(n)
    for d in (0, 0.011, 0.022):                                    # three hands, a clap
        i = int(d * SR)
        burst[i:] += RNG.normal(0, 1, n - i) * _env(n - i, 0.012 if d < 0.02 else 0.09)
    return (level * _band(burst, 900, 6000)).astype(np.float32)


def snare(level: float = 0.6) -> np.ndarray:
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 185 * t) * _env(n, 0.05)
    noise = _band(RNG.normal(0, 1, n), 1500, 8000) * _env(n, 0.11)
    return (level * (0.5 * tone + noise)).astype(np.float32)


def hat(open_: bool = False, level: float = 0.25) -> np.ndarray:
    n = int((0.22 if open_ else 0.05) * SR)
    noise = sosfilt(butter(4, 7000, btype="high", fs=SR, output="sos"), RNG.normal(0, 1, n))
    return (level * noise * _env(n, 0.08 if open_ else 0.012)).astype(np.float32)


def note_hz(pc: int, octave: int) -> float:
    return 440.0 * 2 ** ((pc - 9) / 12 + (octave - 4))


def saw(freq: float, n: int, detune: float = 0.0, voices: int = 1) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros(n)
    for v in range(voices):
        f = freq * (1 + detune * (v - (voices - 1) / 2) / max(1, voices - 1))
        out += 2 * ((t * f + RNG.random()) % 1.0) - 1
    return out / voices


def lowpass(x: np.ndarray, hz: float, order: int = 2) -> np.ndarray:
    sos = butter(order, min(hz, SR / 2 - 100), btype="low", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0)


def highpass(x: np.ndarray, hz: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, hz, btype="high", fs=SR, output="sos"), x, axis=0)


def bass_note(freq: float, seconds: float, level: float = 0.5, cutoff: float = 900) -> np.ndarray:
    n = int(seconds * SR)
    env = np.minimum(1, np.arange(n) / (0.004 * SR)) * _env(n, max(0.06, seconds * 0.6))
    tone = lowpass(saw(freq, n) + 0.6 * np.sin(2 * np.pi * freq * np.arange(n) / SR), cutoff)
    return (level * tone * env).astype(np.float32)


def pad(freqs: list[float], seconds: float, level: float = 0.18, cutoff: float = 2500) -> np.ndarray:
    """A supersaw chord: seven detuned voices per note, a slow attack and release."""
    n = int(seconds * SR)
    x = sum(saw(f, n, detune=0.012, voices=7) for f in freqs) / max(1, len(freqs))
    env = np.minimum(1, np.arange(n) / (0.3 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.4 * SR))
    return (level * lowpass(x, cutoff) * env).astype(np.float32)


def riser(seconds: float, level: float = 0.25) -> np.ndarray:
    """White noise opening up: the build before a drop."""
    n = int(seconds * SR)
    noise = RNG.normal(0, 1, n)
    out = np.zeros(n)
    parts = 16
    for k in range(parts):                                         # the filter opens step by step
        a, b = k * n // parts, (k + 1) * n // parts
        out[a:b] = highpass(noise[a:b], 200 + 6000 * (k / parts) ** 2)
    return (level * out * np.linspace(0.1, 1, n)).astype(np.float32)


def pump(n: int, beat_s: float, first: float, depth: float = 0.6) -> np.ndarray:
    """The sidechain: the music ducks under every kick and swells back before the next one."""
    t = (np.arange(n) / SR - first) % beat_s / beat_s
    return (1 - depth * np.exp(-t * 7)).astype(np.float32)


def place(track: np.ndarray, sound: np.ndarray, at_s: float, gain: float = 1.0) -> None:
    """Add a mono sound into a stereo track at a time (in place)."""
    i = int(at_s * SR)
    if i >= len(track) or i + len(sound) <= 0:
        return
    s = sound[max(0, -i):]
    i = max(0, i)
    end = min(len(track), i + len(s))
    track[i:end] += gain * s[: end - i, None] if s.ndim == 1 else gain * s[: end - i]


def saturate(x: np.ndarray, drive: float) -> np.ndarray:
    return (np.tanh(drive * x) / np.tanh(drive)).astype(np.float32)
