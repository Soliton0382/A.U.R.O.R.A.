# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Audio in and out, and what a track is: its tempo, where its beats fall, its key (the DJ, owner 2026-10-05).

Decoding and encoding through ffmpeg (any format in; MP3 out); the analysis with numpy only: an onset envelope from
the spectral flux, the tempo from its autocorrelation (60-200 BPM, weighted towards 120), the beat phase that fits the
onsets best, the key from the average chroma against the Krumhansl-Kessler profiles. A pulse comes with the tempo:
how much more onset energy falls on the beat grid than on average. A church choir or a piano played freely has no
steady beat (synthetic choirs 1.3-3.4 — a vibrato sung in phase is the highest —, beats even soft 11-15:
STEADY = 6, their geometric middle), and then the remix keeps
its own time. The key of a song that dwells on its fifth as much as on its tonic can come out as the fifth.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 44100
HOP, WIN = 512, 2048
STEADY = 6.0              # pulse at or above: a beat to follow (measured on synthetic signals only, see the doc)
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass
class Info:
    seconds: float
    bpm: float
    confidence: float          # the pulse: onset energy on the beat grid over the average (>= STEADY: a beat)
    first_beat: float          # seconds
    key: int                   # pitch class of the tonic, 0 = C
    minor: bool

    @property
    def steady(self) -> bool:
        return self.confidence >= STEADY

    def as_dict(self) -> dict:
        return {"seconds": round(float(self.seconds), 1), "bpm": round(float(self.bpm), 1),
                "pulse": round(float(self.confidence), 2), "steady": self.steady, "first_beat": round(float(self.first_beat), 3), "key": NOTES[self.key] + (" minor" if self.minor else " major")}


def load(path: Path, seconds: float | None = None) -> np.ndarray:
    """Any audio file as float32 stereo at 44.1 kHz, shape (n, 2)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(SR)]
    if seconds:
        cmd += ["-t", str(seconds)]
    r = subprocess.run(cmd + ["-f", "f32le", "-"], capture_output=True, timeout=600)
    if not r.stdout:
        raise ValueError(f"audio not readable: {r.stderr.decode(errors='replace')[-200:]}")
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


def save(x: np.ndarray, path: Path, title: str = "") -> Path:
    """Stereo float to an MP3 (192 kb/s), loudness levelled to -14 LUFS, marked as made by an AI in its tags."""
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1.0, 1.0).astype(np.float32)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
           "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-ar", str(SR), "-b:a", "192k",
           "-metadata", f"title={title or path.stem}", "-metadata", "comment=Made with Aurora (AI-generated remix)",
           str(path)]
    r = subprocess.run(cmd, input=x.tobytes(), capture_output=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"encoding failed: {r.stderr.decode(errors='replace')[-300:]}")
    return path


def stretch(x: np.ndarray, ratio: float) -> np.ndarray:
    """Faster (ratio > 1) or slower, the pitch kept (ffmpeg's rubberband)."""
    if abs(ratio - 1.0) < 0.005:
        return x
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-af", f"rubberband=tempo={ratio:.5f}", "-f", "f32le", "-"],
                       input=np.ascontiguousarray(x, np.float32).tobytes(), capture_output=True, timeout=900)
    if not r.stdout:
        raise RuntimeError(f"time stretch failed: {r.stderr.decode(errors='replace')[-200:]}")
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


def _spectrogram(mono: np.ndarray) -> np.ndarray:
    n = 1 + max(0, (len(mono) - WIN) // HOP)
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    frames = mono[idx] * np.hanning(WIN)[None, :]
    return np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)


def onsets(spec: np.ndarray) -> np.ndarray:
    flux = np.maximum(0.0, np.diff(np.log1p(spec), axis=0)).sum(axis=1)
    flux = np.convolve(flux, np.ones(3) / 3, mode="same")
    flux -= np.convolve(flux, np.ones(31) / 31, mode="same")      # the local mean away: the beats stand out
    return np.maximum(flux, 0.0)


def tempo(env: np.ndarray) -> tuple[float, float]:
    """(BPM, confidence) from the onset envelope's autocorrelation, 60-200 BPM, a mild preference around 120."""
    fps = SR / HOP
    env = env - env.mean()
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    if ac[0] <= 0:
        return 120.0, 0.0
    ac /= ac[0]
    lags = np.arange(int(fps * 60 / 200), int(fps * 60 / 60) + 1)
    bpms = 60 * fps / lags
    weight = np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)
    score = ac[lags] * weight
    i = int(np.argmax(score))
    lo, hi = max(i - 1, 0), min(i + 1, len(lags) - 1)              # a parabola through the peak: a finer lag
    a, b, c = score[lo], score[i], score[hi]
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    lag = lags[i] + float(np.clip(shift, -0.5, 0.5))
    return 60 * fps / lag, float(max(0.0, min(1.0, ac[lags[i]] * 2)))


def beat_phase(env: np.ndarray, bpm: float) -> float:
    fps = SR / HOP
    period = fps * 60 / bpm
    best, phase = -1.0, 0.0
    for p in np.arange(0, period, 0.5):
        pos = np.arange(p, len(env), period).astype(int)
        s = env[pos].sum()
        if s > best:
            best, phase = s, p
    return phase / fps + (HOP + WIN / 2) / SR       # a flux value belongs to the next frame's centre


def pulse(env: np.ndarray, bpm: float, first_beat: float) -> float:
    fps = SR / HOP
    start = (first_beat - (HOP + WIN / 2) / SR) * fps
    pos = np.arange(max(start, 0.0), len(env) - 1, fps * 60 / bpm).astype(int)
    if not len(pos):
        return 0.0
    grid = np.concatenate([env[np.clip(pos + d, 0, len(env) - 1)] for d in (-1, 0, 1)]).mean()
    return float(grid / max(float(env.mean()), 1e-9))


def key(spec: np.ndarray) -> tuple[int, bool]:
    freqs = np.fft.rfftfreq(WIN, 1 / SR)
    ok = (freqs > 55) & (freqs < 2000)
    pcs = (np.round(12 * np.log2(freqs[ok] / 440.0)).astype(int) + 9) % 12
    energy = spec[:, ok].mean(axis=0)
    chroma = np.bincount(pcs, weights=energy, minlength=12)
    best = (-2.0, 0, False)
    for root in range(12):
        for minor, prof in ((False, MAJOR), (True, MINOR)):
            r = float(np.corrcoef(chroma, np.roll(prof, root))[0, 1])
            if r > best[0]:
                best = (r, root, minor)
    return best[1], best[2]


def analyze(x: np.ndarray) -> Info:
    mono = x.mean(axis=1)
    spec = _spectrogram(mono[: SR * 240])                            # four minutes are enough to know it
    env = onsets(spec)
    bpm, _ = tempo(env)
    first = beat_phase(env, bpm)
    k, minor = key(spec)
    return Info(len(x) / SR, bpm, pulse(env, bpm, first), first, k, minor)
