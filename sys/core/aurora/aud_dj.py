# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's DJ (owner, 2026-10-05): a track remixed in a style, or several tracks mixed into one set.

A style says the tempo, the drums on a 16-step bar, the bass line, whether a pad plays, how much the music pumps
under the kick, how the original is coloured. A remix: the track analysed (aud_analysis), brought to the style's
tempo when its beat is steady (else it keeps its own time and the new beat runs under it), cleared below 120 Hz for
the kick and the bass, then built in sections — intro, main, breakdown with a riser, drop, outro. Bass and pad stay
on the track's key (a progression of chords invented here could clash with the song's harmony). A mix: every track
remixed at one tempo, joined with crossfades of 8 bars on the beat grid.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import aud_analysis as A
from . import aud_synth as S
from .aud_analysis import SR

# steps of a 4/4 bar in sixteenths: 0 = the first beat, 4 = the second...
STYLES = {
    "techno": {"it": "Techno", "en": "Techno", "bpm": 130, "kick": range(0, 16, 4), "clap": (4, 12), "hat": range(2, 16, 4),
               "closed": range(0, 16, 1), "bass": [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15], "bass_len": 0.25,
               "pad": False, "pump": 0.55, "orig": 0.75, "drive": 1.4},
    "trance": {"it": "Trance", "en": "Trance", "bpm": 138, "kick": range(0, 16, 4), "clap": (4, 12), "hat": range(2, 16, 4),
               "closed": range(0, 16, 2), "bass": [2, 6, 10, 14], "bass_len": 0.5, "pad": True, "pad_level": 0.16,
               "pump": 0.65, "orig": 0.8, "drive": 1.0},
    "vocal_trance": {"it": "Trance vocale", "en": "Vocal trance", "bpm": 136, "kick": range(0, 16, 4), "clap": (4, 12),
                     "hat": range(2, 16, 4), "closed": range(0, 16, 2), "bass": [2, 6, 10, 14], "bass_len": 0.5,
                     "pad": True, "pad_level": 0.10, "pump": 0.45, "orig": 1.0, "drive": 1.0, "long_break": True},
    "techno_trance": {"it": "Techno-trance", "en": "Techno-trance", "bpm": 136, "kick": range(0, 16, 4), "clap": (4, 12),
                      "hat": range(2, 16, 4), "closed": range(0, 16, 1), "bass": [2, 3, 6, 7, 10, 11, 14, 15],
                      "bass_len": 0.25, "pad": True, "pad_level": 0.13, "pump": 0.6, "orig": 0.85, "drive": 1.2},
    "house": {"it": "House", "en": "House", "bpm": 124, "kick": range(0, 16, 4), "clap": (4, 12), "hat": range(2, 16, 4),
              "closed": (), "bass": [3, 6, 10, 13], "bass_len": 0.35, "pad": False, "pump": 0.4, "orig": 0.9, "drive": 1.0},
    "rock": {"it": "Rock", "en": "Rock", "bpm": None, "kick": (0, 8, 10), "snare": (4, 12), "hat": (),
             "closed": range(0, 16, 2), "bass": range(0, 16, 2), "bass_len": 0.5, "pad": False, "pump": 0.0, "orig": 0.9,
             "drive": 2.4},
    "chill": {"it": "Chill", "en": "Chill", "bpm": 88, "kick": (0, 10), "snare": (4, 12), "snare_level": 0.3, "hat": (),
              "closed": range(0, 16, 2), "bass": (0, 10), "bass_len": 0.9, "pad": True, "pad_level": 0.08, "pump": 0.15,
              "orig": 0.95, "drive": 1.0, "lowpass": 4000},
    "smooth": {"it": "Mix morbido (solo dissolvenze)", "en": "Smooth mix (crossfades only)", "bpm": None, "kick": (),
               "hat": (), "closed": (), "bass": (), "pad": False, "pump": 0.0, "orig": 1.0, "drive": 1.0},
}


def styles(lang: str = "it") -> list[dict]:
    return [{"id": k, "label": v["it" if lang.startswith("it") else "en"], "bpm": v["bpm"]} for k, v in STYLES.items()]


def _sections(bars: int, long_break: bool) -> dict[str, tuple[int, int]]:
    """Bar ranges of each part; a short track gets only an intro and an outro around its body."""
    if bars < 32:
        return {"intro": (0, min(4, bars)), "main": (min(4, bars), max(min(4, bars), bars - 4)), "outro": (max(0, bars - 4), bars)}
    mid = bars // 2 - (bars // 2) % 4
    brk = 16 if long_break and bars >= 64 else 8
    return {"intro": (0, 8), "main": (8, mid - brk), "break": (mid - brk, mid), "drop": (mid, bars - 8), "outro": (bars - 8, bars)}


def _clock(beats: np.ndarray, first_bar: int, beat: float):
    """Where step s (0-15) of bar b falls: on the song's own beats, followed one by one (aud_analysis.track), the
    sixteenths between two of them; before the first and after the last one, the mean beat. Owner, 10 Oct: «ogni
    tanto esce fuori ritmo» — a fixed grid drifted away from a song that moves (M180: 131-216 ms off, now 3 ms)."""
    def at(b: int, s: int) -> float:
        k, frac = 4 * (b - first_bar) + s // 4, (s % 4) / 4
        if len(beats) < 2 or k < 0:
            return (beats[0] if len(beats) else first_bar * 4 * beat) + (k + frac) * beat
        if k >= len(beats) - 1:
            return beats[-1] + (k - len(beats) + 1 + frac) * beat
        return beats[k] + frac * (beats[k + 1] - beats[k])
    return at


def _pump(n: int, kicks: list[float], beat: float, depth: float) -> np.ndarray:
    """The sidechain on the kicks really placed: the music ducks under each one and swells back before the next."""
    if not kicks:
        return np.ones(n, np.float32)
    at = np.sort(np.array([int(k * SR) for k in kicks]))
    idx = np.searchsorted(at, np.arange(n), side="right") - 1
    since = np.where(idx >= 0, (np.arange(n) - at[np.clip(idx, 0, None)]) / SR, 10 * beat)
    return (1 - depth * np.exp(-since / beat * 7)).astype(np.float32)


def remix(x: np.ndarray, style: str, seconds: float | None = None, emit=None, bpm: float | None = None,
          drums_level: float = 1.0) -> tuple[np.ndarray, dict]:
    """One track in a style; returns the audio and what was done (tempo, key, sections). `bpm`: a tempo of the
    user's instead of the style's (the two-deck mixer, aud_deck); `drums_level`: how loud the added beat is."""
    st = {**STYLES[style], **({"bpm": float(bpm)} if bpm else {})}
    say = emit or (lambda e, p: None)
    info = A.analyze(x)
    say("dj.analysis", info.as_dict())
    steady = info.steady
    bpm = st["bpm"] or (info.bpm if steady else 120.0)
    ratio = 1.0
    if st["bpm"] and steady:
        ratio = bpm / info.bpm
        if ratio > 1.45 or ratio < 0.7:                            # half or double time: the nearer one
            for k in (2.0, 0.5):
                if 0.7 <= bpm / (info.bpm * k) <= 1.45:
                    ratio = bpm / (info.bpm * k)
        x = A.stretch(x, ratio)
        first = info.first_beat / ratio
    else:
        first = info.first_beat if steady else 0.0
        bpm = bpm if st["bpm"] else (info.bpm if steady else 120.0)
    if seconds:
        x = x[: int(seconds * SR)]
    beat = 60.0 / bpm
    bar = 4 * beat
    shift = (bar - first % bar) % bar if steady else 0.0            # the song's first beat on a bar line
    lead = int(shift * SR)
    total = len(x) + lead
    bars = max(1, int(np.ceil(total / SR / bar)))
    n = int(bars * bar * SR)
    song = np.zeros((n, 2), np.float32)
    song[lead: lead + len(x)] = x[: n - lead]
    followed = info.beats / ratio + shift if steady and len(info.beats) >= 8 else np.zeros(0)
    if seconds is not None:
        followed = followed[followed < seconds + shift]
    first_bar = int(round(((first + shift) if steady else 0.0) / bar))
    at = _clock(followed, first_bar, beat) if len(followed) else (lambda b_, s_: b_ * bar + s_ * beat / 4)
    kicks: list[float] = []
    if st["kick"] or st["bass"]:
        song = S.highpass(song, 120).astype(np.float32)             # room for the kick and the bass
    if st.get("lowpass"):
        song = S.lowpass(song, st["lowpass"]).astype(np.float32)
    song = S.saturate(song * st["orig"], st["drive"]) if st["drive"] > 1.0 else song * st["orig"]
    secs = _sections(bars, st.get("long_break", False))
    say("dj.plan", {"bpm": round(bpm, 1), "steady": steady, "bars": bars, "sections": secs, "style": style})
    drums = np.zeros((n, 2), np.float32)
    music = np.zeros((n, 2), np.float32)
    kick, clap, snr = S.kick(0.95), S.clap(), S.snare(st.get("snare_level", 0.6))
    hat_o, hat_c = S.hat(True), S.hat(False, 0.12)
    root = info.key
    bass_hz = S.note_hz(root, 1 if root >= 5 else 2)
    third = 3 if info.minor else 4
    chord = [S.note_hz(root, 3), S.note_hz((root + third) % 12, 3 if root + third < 12 else 4), S.note_hz((root + 7) % 12, 3 if root + 7 < 12 else 4)]

    def part(b: int) -> str:
        return next((k for k, (a, z) in secs.items() if a <= b < z), "main")
    for b in range(bars):
        p = part(b)
        full = p in ("main", "drop")
        intro_or_out = p in ("intro", "outro")
        if p != "break":
            for s in st["kick"]:
                S.place(drums, kick, at(b, s), 0.8 if intro_or_out else 1.0)
                kicks.append(at(b, s))
            for s in st.get("clap", ()):
                if full:
                    S.place(drums, clap, at(b, s))
            for s in st.get("snare", ()):
                if full or p == "outro":
                    S.place(drums, snr, at(b, s))
            for s in st["hat"]:
                S.place(drums, hat_o, at(b, s), 1.0 if full else 0.5)
            for s in st["closed"]:
                S.place(drums, hat_c, at(b, s), 0.9 if s % 4 == 2 else 0.6)
            if full or p == "outro":
                for s in st["bass"]:
                    S.place(music, S.bass_note(bass_hz, st["bass_len"] * beat, 0.45), at(b, s))   # bass_len: in beats
        if st["pad"] and (b % 4 == 0) and p in ("break", "drop", "main"):
            S.place(music, S.pad(chord, 4 * bar, st.get("pad_level", 0.15) * (1.4 if p == "break" else 1.0)), at(b, 0))
    if "break" in secs:                                            # the build: noise rising into the drop
        a, z = secs["break"]
        S.place(music, S.riser(min(4, z - a) * bar), (z - min(4, z - a)) * bar)
    if st["pump"]:
        g = _pump(n, kicks, beat, st["pump"])[:, None]
        mask = np.ones((n, 1), np.float32)
        a, z = secs.get("break", (0, 0))
        mask[int(a * bar * SR): int(z * bar * SR)] = 0.0             # no kick in the break: no pump
        g = 1 - (1 - g) * mask
        song, music = song * g, music * g
    fade = int(min(8, bars) * bar * SR * 0.5)
    out = song + (music + drums) * drums_level
    if fade:
        out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    peak = float(np.max(np.abs(out))) or 1.0
    out = S.saturate(out / peak * 1.1, 1.2) * 0.95
    return out.astype(np.float32), {"bpm": round(bpm, 1), "key": info.as_dict()["key"], "steady": steady,
                                    "bars": bars, "seconds": round(n / SR, 1), "style": style}


def mix(tracks: list[np.ndarray], style: str, emit=None) -> tuple[np.ndarray, list[dict]]:
    """Several tracks, one style, one tempo: each remixed, joined with 8-bar crossfades (8 s for the smooth mix)."""
    parts, notes = [], []
    for i, x in enumerate(tracks):
        (emit or (lambda e, p: None))("dj.track", {"n": i + 1, "of": len(tracks)})
        y, note = remix(x, style, emit=emit)
        parts.append(y)
        notes.append(note)
    if not parts:
        raise ValueError("no track")
    bpm = notes[0]["bpm"]
    over = int((8 * 4 * 60 / bpm if STYLES[style]["bpm"] else 8.0) * SR)
    out = parts[0]
    for y in parts[1:]:
        o = min(over, len(out) // 2, len(y) // 2)
        ramp = np.linspace(0, 1, o, dtype=np.float32)[:, None]
        out = np.concatenate([out[:-o], out[-o:] * (1 - ramp) + y[:o] * ramp, y[o:]])
    return out, notes


def make(paths: list[Path], style: str, out: Path, seconds: float | None = None, emit=None,
         deck: dict | None = None) -> dict:
    """The DJ's one call: files in, an MP3 out (loudness levelled, tagged as an AI remix). `deck`: two tracks on the
    two-deck mixer with the user's choices (aud_deck)."""
    if style not in STYLES:
        raise ValueError(f"style: one of {', '.join(STYLES)}")
    if not paths:
        raise ValueError("no track")
    tracks = [A.load(p, seconds) for p in paths]
    if deck is not None:
        from . import aud_deck
        if len(tracks) != 2:
            raise ValueError("the two decks take two tracks")
        y, note = aud_deck.blend(tracks[0], tracks[1], {**deck, "style": deck.get("style") or style}, emit=emit)
        A.save(y, out, title=f"{out.stem} (two decks)")
        return {"file": out.name, "seconds": round(len(y) / SR, 1), "style": style, "deck": note,
                "tracks": [{"bpm": note["bpm"], "key": note["key_a"]}]}
    y, notes = (remix(tracks[0], style, emit=emit) if len(tracks) == 1 else mix(tracks, style, emit=emit))
    notes = notes if isinstance(notes, list) else [notes]
    A.save(y, out, title=f"{out.stem} ({STYLES[style]['en']})")
    return {"file": out.name, "seconds": round(len(y) / SR, 1), "style": style, "tracks": notes}
