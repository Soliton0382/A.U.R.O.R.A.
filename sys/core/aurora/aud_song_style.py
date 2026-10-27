# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How a song is dressed (owner, 2026-10-27: «possiamo impostare anche diversi stili o modalità di stili… vengono cmq
tutte un po' uguali… non c'è modo di vestire le canzoni anche usando i medesimi stili?»).

Five axes the user may choose, each «auto» by default: the genre, the dress (the arrangement: the same genre acoustic,
orchestral, minimal, a club anthem… sounds another song), the voice, the tempo and the key, and how bold the music
model's own planner is. A choice becomes words the reasoner must build the caption on, tags added to the caption
whatever the reasoner wrote (so it is never lost), and the music model's own fields (bpm, key_scale, the planner's
temperature). «Sing it again» with another dress keeps the words and changes the clothes (redress).
"""
from __future__ import annotations

import random

# id: (it, en, tags for the music model)
GENRES = {
    "trance90": ("Trance anni '90", "90s trance", "90s eurotrance, uplifting trance, supersaw leads, rolling bassline"),
    "eurodance": ("Eurodance", "Eurodance", "90s eurodance, catchy synth riff, four-on-the-floor, energetic"),
    "synthwave": ("Synthwave", "Synthwave", "synthwave, retro 80s, analog synths, gated reverb drums, neon nostalgia"),
    "lofi": ("Lo-fi", "Lo-fi", "lo-fi hip hop, dusty vinyl crackle, mellow keys, laid-back swing beat"),
    "cinematic": ("Cinematografico", "Cinematic", "cinematic score, epic orchestra, big taiko drums, emotional build"),
    "rock": ("Rock", "Rock", "rock, driving electric guitars, live drums, bass guitar, anthemic chorus"),
    "pop_ballad": ("Ballata pop", "Pop ballad", "pop ballad, piano and strings, heartfelt, slow build to a big chorus"),
    "folk": ("Folk acustico", "Acoustic folk", "acoustic folk, fingerpicked guitar, warm, intimate, light percussion"),
    "jazz": ("Jazz", "Jazz", "jazz, brushed drums, upright bass, piano trio, smoky club"),
    "ambient": ("Ambient", "Ambient", "ambient, evolving pads, spacious reverb, slow, meditative"),
    "techno": ("Techno", "Techno", "techno, hypnotic, pounding kick, dark synth stabs, warehouse"),
    "house": ("House", "House", "deep house, groovy bassline, warm chords, soulful, four-on-the-floor"),
    "dnb": ("Drum & bass", "Drum & bass", "liquid drum and bass, fast breakbeats, deep sub bass, atmospheric"),
    "hiphop": ("Hip hop", "Hip hop", "hip hop, boom bap drums, deep bass, sampled soul chords"),
    "classical": ("Classica", "Classical", "classical, chamber orchestra, strings and woodwinds, romantic era"),
    "italo": ("Italo disco", "Italo disco", "italo disco, 80s, vocoder, arpeggiated bass, sparkling synths"),
}
DRESSES = {
    "acoustic": ("Acustico, unplugged", "Acoustic, unplugged", "unplugged, acoustic guitars, piano, no synths, natural room sound"),
    "orchestral": ("Orchestrale", "Orchestral", "full orchestral arrangement, strings, brass, timpani, choir pads"),
    "minimal": ("Elettronico minimale", "Minimal electronic", "minimal arrangement, few elements, sparse beat, lots of space"),
    "anthem": ("Inno da club", "Club anthem", "festival anthem, huge build-up, big drop, hands-in-the-air chorus"),
    "chill": ("Chill, lounge", "Chill, lounge", "chillout, lounge, soft beat, warm pads, relaxed"),
    "dark": ("Dark, cinematografico", "Dark, cinematic", "dark, brooding, minor key tension, cinematic textures"),
    "retro80": ("Retrò anni '80", "Retro 80s", "80s production, gated reverb, analog synths, chorus guitars"),
    "liveband": ("Band dal vivo", "Live band", "live band recording, drums bass guitars keys, energetic performance"),
    "dreamy": ("Sognante", "Dreamy", "dreamy, shimmering reverb, ethereal pads, soft focus"),
    "bigpop": ("Pop radiofonico", "Radio pop", "polished modern pop production, punchy drums, bright synths, radio-ready"),
}
VOICES = {
    "female": ("Voce femminile", "Female voice", "female vocalist"),
    "male": ("Voce maschile", "Male voice", "male vocalist"),
    "duet": ("Duetto", "Duet", "male and female duet"),
    "choir": ("Coro", "Choir", "choir vocals"),
    "instrumental": ("Strumentale", "Instrumental", "instrumental, no vocals"),
}
TEMPOS = {"slow": ("Lento", "Slow", 78), "mid": ("Medio", "Medium", 112), "fast": ("Veloce", "Fast", 138)}
KEYS = {"major": ("Maggiore (luminosa)", "Major (bright)", "major"), "minor": ("Minore (malinconica)", "Minor (moody)", "minor")}
CREATIVITY = {"safe": ("Sicura", "Safe", 0.7), "balanced": ("Equilibrata", "Balanced", 0.85), "bold": ("Audace", "Bold", 1.05)}
NOTES = ["C", "D", "E", "F", "G", "A", "B"]
AXES = {"genre": GENRES, "dress": DRESSES, "voice": VOICES, "tempo": TEMPOS, "key": KEYS, "creativity": CREATIVITY}


def options(lang: str = "it") -> dict:
    """Each axis with its choices, for the page: {axis: [{"id", "label"}]} («auto» is the page's own first choice)."""
    k = 0 if lang.startswith("it") else 1
    return {axis: [{"id": i, "label": v[k]} for i, v in table.items()] for axis, table in AXES.items()}


def check(style: dict | None) -> dict:
    """The choices kept, «auto» or unknown dropped (ValueError for an unknown axis)."""
    out = {}
    for axis, choice in (style or {}).items():
        if axis not in AXES:
            raise ValueError(f"style: unknown axis {axis!r}")
        if choice and choice != "auto":
            if choice not in AXES[axis]:
                raise ValueError(f"style {axis}: one of {', '.join(AXES[axis])}")
            out[axis] = choice
    return out


def resolve(style: dict | None, rng: random.Random | None = None) -> dict:
    """The choices made into what the writer and the music model take: {"brief", "tags", "bpm", "key_scale",
    "lm_temperature", "instrumental"} — only what was chosen."""
    s = check(style)
    rng = rng or random.Random()
    tags = [AXES[a][c][2] for a, c in s.items() if a in ("genre", "dress", "voice")]
    out: dict = {"tags": tags, "instrumental": s.get("voice") == "instrumental"}
    brief = []
    if "genre" in s:
        brief.append(f"genre: {GENRES[s['genre']][1]}")
    if "dress" in s:
        brief.append(f"arrangement: {DRESSES[s['dress']][1]} ({DRESSES[s['dress']][2]})")
    if "voice" in s:
        brief.append(f"voice: {VOICES[s['voice']][1]}")
    if "tempo" in s:
        out["bpm"] = TEMPOS[s["tempo"]][2] + rng.randint(-4, 4)          # a little apart each time
        brief.append(f"tempo about {out['bpm']} BPM")
    if "key" in s:                                                       # a tonic of chance in the mode chosen
        out["key_scale"] = f"{rng.choice(NOTES)} {KEYS[s['key']][2]}"
        brief.append(f"key: {out['key_scale']}")
    if "creativity" in s:
        out["lm_temperature"] = CREATIVITY[s["creativity"]][2]
    out["brief"] = "; ".join(brief)
    return out


def dress(caption: str, tags: list[str]) -> str:
    """The caption with the chosen tags in front (what the user chose is never left to the reasoner's wording)."""
    have = caption.lower()
    add = [t for t in tags if t.split(",")[0].strip().lower() not in have]
    return ", ".join(add + [caption]).strip(", ")[:600]


def redress(caption: str, style: dict | None) -> str:
    """«Sing it again» in other clothes: the genre's words kept, the arrangement and voice of before replaced."""
    r = resolve(style)
    old = [t.strip() for t in caption.split(",")]
    drop = {w.strip().lower() for table in (DRESSES, VOICES) for v in table.values() for w in v[2].split(",")}
    kept = [t for t in old if t.lower() not in drop]
    return dress(", ".join(kept), r["tags"])
