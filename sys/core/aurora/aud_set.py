# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A DJ set made by Aurora (owner, 2026-10-27: «qualcosa di grafico accattivante che permetta davvero un mix autonomo
fine brani»): several of the user's tracks, in the order a DJ would play them, each one coming in on the beat of the
one before as that one ends.

Each track is analysed once (aud_analysis). The order, unless the user keeps theirs: from the first chosen track, the
next is the one nearest on the Camelot wheel (the same key, a fifth away, or its relative major/minor mix without a
clash) and in tempo. Every track is brought to one common tempo (the median of the set, half or double time taken at
the nearer one) without changing its key — a voice moved by semitones sounds wrong, the order keeps the keys apart
instead. The transition starts where the outgoing track has BARS (by default 16) bars plus its last 8 left — those last 8,
often a fade, are not played — on one of its own followed beats; the incoming track's first downbeat lands on it (aud_deck's transitions: a bass swap between
keys that agree, a filter sweep between keys that do not). The timeline (each track's place, the transitions, the
waveform's peaks) is kept beside the MP3 for the DJ page's console.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np

from . import aud_analysis as A
from . import aud_deck as D
from .aud_analysis import SR

PEAKS = 1600                     # the console's waveform: points for the whole set
OUTRO_BARS = 8                   # a track's last bars, left out after its transition: they are often a fade


def camelot(key: int, minor: bool) -> tuple[int, str]:
    """The Camelot wheel's place of a key: (1-12, "A" minor / "B" major)."""
    num = ((7 * key + (4 if minor else 7)) % 12) + 1          # C major = 8B, A minor = 8A
    return num, "A" if minor else "B"


def label(key: int, minor: bool) -> str:
    n, letter = camelot(key, minor)
    return f"{n}{letter}"


def distance(a: tuple[int, str], b: tuple[int, str]) -> int:
    """Steps on the wheel: 0 the same key, 1 a neighbour (a fifth away, or the relative major/minor), more: a clash."""
    d = min((a[0] - b[0]) % 12, (b[0] - a[0]) % 12)
    return d + (0 if a[1] == b[1] else 1)


def order(infos: list[A.Info], first: int = 0) -> list[int]:
    """From the first chosen track, each next the nearest in key and tempo (greedy, as a DJ reads the crate)."""
    left = [i for i in range(len(infos)) if i != first]
    out = [first]
    while left:
        cur = infos[out[-1]]
        cw = camelot(cur.key, cur.minor)
        nxt = min(left, key=lambda i: 3 * distance(cw, camelot(infos[i].key, infos[i].minor))
                  + abs(D._near(infos[i].bpm, cur.bpm) - 1.0) * 40)
        out.append(nxt)
        left.remove(nxt)
    return out


def _beats(info: A.Info, ratio: float, n: int, beat: float) -> np.ndarray:
    if info.steady and len(info.beats) >= 8:
        return info.beats / ratio
    return info.first_beat / ratio + np.arange(int(n / SR / beat)) * beat


def peaks(x: np.ndarray, points: int = PEAKS) -> list[float]:
    mono = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    edges = np.linspace(0, len(mono), points + 1).astype(int)
    return [round(float(mono[a:z].max()) if z > a else 0.0, 3) for a, z in zip(edges[:-1], edges[1:])]


def build(tracks: list[np.ndarray], names: list[str], keep_order: bool = False, bars: int = 16,
          emit=None) -> tuple[np.ndarray, dict]:
    """The set: its audio and its timeline."""
    if len(tracks) < 2:
        raise ValueError("a set takes at least two tracks")
    if bars not in (8, 16, 32):
        raise ValueError("bars: 8, 16 or 32")
    say = emit or (lambda e, p: None)
    infos = []
    for i, x in enumerate(tracks):
        say("dj.track", {"n": i + 1, "of": len(tracks), "step": "analysis"})
        infos.append(A.analyze(x))
    seq = list(range(len(tracks))) if keep_order else order(infos)
    common = round(statistics.median(D._near(infos[i].bpm, infos[seq[0]].bpm) * infos[i].bpm for i in seq), 1)
    beat = 60.0 / common
    say("dj.plan", {"order": [names[i] for i in seq], "bpm": common})
    out = np.zeros((0, 2), np.float32)
    timeline, prev_off, prev_beats, prev_len = [], 0, None, 0
    for pos, i in enumerate(seq):
        say("dj.track", {"n": pos + 1, "of": len(seq), "step": "mix"})
        info = infos[i]
        ratio = D._near(info.bpm, common)
        y = D.shift(tracks[i], ratio, 0)
        yb = _beats(info, ratio, len(y), beat)
        entry = {"name": names[i], "bpm": round(info.bpm, 1), "key": info.as_dict()["key"],
                 "camelot": label(info.key, info.minor), "tempo": round(ratio, 4)}
        if prev_beats is None:
            out, off = y, 0
        else:
            over = int(bars * 4 * beat * SR)
            want = (prev_len - over) / SR - OUTRO_BARS * 4 * beat            # where the transition should start
            ks = [k for k in range(0, len(prev_beats), 4) if prev_beats[k] <= want]
            k = ks[-1] if ks else max(0, len(prev_beats) // 2 // 4 * 4)
            start = int(prev_beats[k] * SR)
            b0 = int((yb[0] if len(yb) else 0.0) * SR)
            over = max(1, min(over, prev_len - start, len(y) - b0))
            prev = timeline[-1]
            kind = "bass_swap" if distance(camelot(infos[seq[pos - 1]].key, infos[seq[pos - 1]].minor),
                                           camelot(info.key, info.minor)) <= 1 else "filter"
            a0 = prev_off + start
            mixed = D._transition(out[a0: a0 + over], y[b0: b0 + over], kind, beat)
            out = np.concatenate([out[:a0], mixed, y[b0 + over:]])
            off = a0 - b0
            prev["end"] = round((a0 + over) / SR, 2)
            entry["transition"] = {"from": round(a0 / SR, 2), "to": round((a0 + over) / SR, 2), "kind": kind,
                                   "bars": round(over / SR / (4 * beat))}
        entry["start"] = round(max(0, off) / SR, 2)
        entry["end"] = round((off + len(y)) / SR, 2)
        timeline.append(entry)
        prev_off, prev_beats, prev_len = off, yb, len(y)
    peak = float(np.max(np.abs(out))) or 1.0
    out = (out / peak * 0.95).astype(np.float32)
    return out, {"bpm": common, "seconds": round(len(out) / SR, 1), "tracks": timeline, "peaks": peaks(out),
                 "order": "given" if keep_order else "camelot"}


def make(paths: list[Path], out: Path, keep_order: bool = False, bars: int = 16, seconds: float | None = None,
         emit=None) -> dict:
    """Files in; the set's MP3 and its timeline (<name>.json beside it) out."""
    tracks = [A.load(p, seconds) for p in paths]
    y, plan = build(tracks, [p.stem for p in paths], keep_order, bars, emit)
    A.save(y, out, title=f"{out.stem} (Aurora's set)")
    out.with_suffix(".json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return {"file": out.name, **{k: v for k, v in plan.items() if k != "peaks"}}
