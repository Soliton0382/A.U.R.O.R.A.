# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How a song is dressed (owner, 2026-10-27: «possiamo impostare anche diversi stili o modalità di stili… vengono cmq
tutte un po' uguali… non c'è modo di vestire le canzoni anche usando i medesimi stili?»).

Five axes the user may choose, each «auto» by default: the genre, the dress (the arrangement: the same genre acoustic,
orchestral, minimal, a club anthem… sounds another song), the voice, the tempo and the key, and how bold the music
model's own planner is. A choice becomes words the reasoner must build the caption on, tags added to the caption
whatever the reasoner wrote (so it is never lost), and the music model's own fields (bpm, key_scale, the planner's
temperature). «Sing it again» with another dress keeps the words and changes the clothes (redress).

Then (owner, 28 Oct: «vocal trance bella strumentale… che ti fa toccare con mano l'infinito dell'universo… techno di
quella giusta anni 2000… manca anche il metal… quali set si possono specificare per pompare più o meno determinati
arrangiamenti… prendere ispirazione allo stile di determinati brani»): more genres, each with its own tempo when the
tempo is «auto»; the mix — each element of the arrangement from 0 (left out: the model's negative prompt) to 3 (up
front); and an inspiration — a track named in words, whose style (never its melody or its words) the reasoner turns
into musical terms. Only words: no reference audio (owner, 28 Oct: «no file di riferimento, tutto gestito tramite il
prompt»).
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
    "vocal_trance": ("Vocal trance", "Vocal trance", "vocal trance, uplifting, euphoric, soaring ethereal female vocal, long "
                     "instrumental passages, supersaw lead, emotional breakdown with piano and strings, big drop"),
    "cosmic_trance": ("Trance cosmica strumentale", "Cosmic instrumental trance", "uplifting instrumental trance, epic and "
                      "cosmic, vast space atmosphere, huge supersaw chords, lush evolving pads, long breakdown, "
                      "euphoric melody, early 2000s"),
    "techno2000": ("Techno anni 2000", "2000s techno", "early 2000s peak-time techno, driving and hypnotic, rolling "
                   "percussive loops, punchy kick, filtered stabs, warehouse energy"),
    "hard_trance": ("Hard trance anni 2000", "2000s hard trance", "2000s hard trance, pounding kick, acid 303 lines, "
                    "fast energetic leads, hoover synths"),
    "metal": ("Metal", "Metal", "heavy metal, distorted down-tuned guitars, double kick drums, galloping riffs, "
              "powerful vocals, guitar solo"),
    "symphonic_metal": ("Metal sinfonico", "Symphonic metal", "symphonic metal, heavy guitars with full orchestra and "
                        "choir, operatic vocals, epic and dramatic"),
}
GENRE_BPM = {"trance90": 138, "vocal_trance": 138, "cosmic_trance": 136, "techno2000": 132, "hard_trance": 145,
             "techno": 130, "house": 124, "dnb": 174, "eurodance": 135, "metal": 160, "symphonic_metal": 140}
# the mix: the elements of an arrangement, each 0 (left out) to 3 (up front); 1 subtle, 2 as the genre has it
MIX = {
    "lead": ("Lead synth (supersaw)", "Lead synth (supersaw)", "supersaw lead"),
    "pads": ("Pad e atmosfere", "Pads and atmosphere", "atmospheric pads"),
    "arp": ("Arpeggi", "Arpeggios", "arpeggiated synths"),
    "acid": ("Acid 303", "Acid 303", "acid 303 bassline"),
    "piano": ("Pianoforte", "Piano", "piano"),
    "strings": ("Archi e orchestra", "Strings and orchestra", "orchestral strings"),
    "guitars": ("Chitarre distorte", "Distorted guitars", "distorted electric guitars"),
    "bass": ("Basso", "Bass", "bassline"),
    "kick": ("Cassa e batteria", "Kick and drums", "kick drum"),
    "choir": ("Coro", "Choir", "choir"),
    "vocals": ("Voce", "Vocals", "vocals"),
    "breakdown": ("Breakdown", "Breakdown", "breakdown"),
}
LEVELS = {0: "no {x}", 1: "subtle {x}", 2: "{x}", 3: "prominent {x} up front, {x}-driven"}
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
INSPIRATION_MAX = 160


def options(lang: str = "it") -> dict:
    """Each axis with its choices, for the page: {axis: [{"id", "label"}]} («auto» is the page's own first choice)."""
    k = 0 if lang.startswith("it") else 1
    out = {axis: [{"id": i, "label": v[k]} for i, v in table.items()] for axis, table in AXES.items()}
    return {**out, "mix": [{"id": i, "label": v[k]} for i, v in MIX.items()]}


def check(style: dict | None) -> dict:
    """The choices kept, «auto» or unknown dropped (ValueError for an unknown axis)."""
    out = {}
    for axis, choice in (style or {}).items():
        if axis == "mix":                                # {element: 0..3}; 2 (as the genre has it) is not kept
            if not isinstance(choice, dict):
                raise ValueError("style mix: {element: 0-3}")
            mix = {}
            for e, v in choice.items():
                if e not in MIX or str(v) not in ("0", "1", "2", "3"):
                    raise ValueError(f"style mix: elements {', '.join(MIX)}, levels 0-3")
                if int(v) != 2:
                    mix[e] = int(v)
            if mix:
                out["mix"] = mix
            continue
        if axis == "inspiration":
            words = " ".join(str(choice or "").split())[:INSPIRATION_MAX]
            if words:
                out["inspiration"] = words
            continue
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
    mix = s.get("mix", {})
    tags += [LEVELS[v].format(x=MIX[e][2]) for e, v in mix.items() if v > 0]
    out: dict = {"tags": tags, "instrumental": s.get("voice") == "instrumental" or mix.get("vocals") == 0}
    if any(v == 0 for v in mix.values()):              # what is left out: the planner's negative prompt
        out["negative"] = ", ".join(MIX[e][2] for e, v in mix.items() if v == 0)
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
    elif s.get("genre") in GENRE_BPM:                                    # the genre's own tempo when «auto»
        out["bpm"] = GENRE_BPM[s["genre"]] + rng.randint(-2, 2)
        brief.append(f"tempo about {out['bpm']} BPM")
    if mix:
        brief.append("mix: " + "; ".join(f"{MIX[e][1]} {('left out', 'subtle', 'normal', 'up front')[v]}" for e, v in mix.items()))
    if "inspiration" in s:                             # the style of a track in words: never its melody, never its name
        brief.append(f"inspired by the STYLE of «{s['inspiration']}»: describe that style in musical terms only "
                     "(era, tempo, instruments, structure, mood); never name the track or the artist in the caption, "
                     "never reuse its melody or its words")
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
