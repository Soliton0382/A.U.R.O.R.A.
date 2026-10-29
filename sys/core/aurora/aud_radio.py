# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📻 Internet radio in the player (owner, 28 Oct: «io però non ho premium… nel caso c'è qualche radio internet che
possiamo sfruttare?»).

The stations come from Radio Browser (radio-browser.info: a free, open directory kept by its community, tens of
thousands of stations, SomaFM's among them), asked by name or by genre; a station is played through Aurora (the page
asks /v1/aurora/radio/<id>/stream): the WebUI's own policy keeps media from this site only, the stream's address is
looked up here by the station's id — never a link the page sends — and reached as a public address only (net_public:
never this machine, never the LAN). The stations a user keeps are theirs (radio.json in their music folder). Only
listening: nothing is recorded or kept.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from . import net_public

SERVERS = ("https://de1.api.radio-browser.info", "https://fi1.api.radio-browser.info", "https://at1.api.radio-browser.info")
UA = {"User-Agent": "Aurora/1 (self-hosted assistant; radio player)"}
KEEP_S = 600
ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# the owner's genres first (28 Oct: vocal trance, «trance cosmica», 2000s techno, metal)
PRESETS = [("vocal trance", "🎤 Vocal trance"), ("uplifting trance", "🌌 Uplifting trance"), ("trance", "✨ Trance"),
           ("space", "🛰️ Spazio e ambient"), ("techno", "⚙️ Techno"), ("hard trance", "🔥 Hard trance"),
           ("metal", "🤘 Metal"), ("chillout", "🌙 Chillout")]
# every genre, in families (owner, 29 Oct: «mettiamo tutti i generi altrimenti resta un po' poverina»): the directory's
# own tags, each shown with how many stations carry it (a tag with fewer than MIN_STATIONS left out); any other tag of
# the directory by its name (genres(): «more»)
GENRES = [
    ("🎛️ Elettronica", [("electronic", "Electronic"), ("dance", "Dance"), ("house", "House"), ("deep house", "Deep house"),
                       ("tech house", "Tech house"), ("progressive house", "Progressive house"), ("techno", "Techno"),
                       ("minimal", "Minimal"), ("trance", "Trance"), ("vocal trance", "Vocal trance"),
                       ("uplifting trance", "Uplifting trance"), ("progressive trance", "Progressive trance"),
                       ("psytrance", "Psytrance"), ("goa", "Goa"), ("hard trance", "Hard trance"), ("hardstyle", "Hardstyle"),
                       ("hardcore", "Hardcore"), ("drum and bass", "Drum and bass"), ("jungle", "Jungle"),
                       ("dubstep", "Dubstep"), ("breakbeat", "Breakbeat"), ("electro", "Electro"), ("edm", "EDM"),
                       ("eurodance", "Eurodance"), ("italo disco", "Italo disco"), ("synthwave", "Synthwave"),
                       ("idm", "IDM"), ("industrial", "Industrial"), ("ebm", "EBM")]),
    ("🌙 Ambient e chill", [("ambient", "Ambient"), ("space", "Spazio"), ("chillout", "Chillout"), ("lounge", "Lounge"),
                           ("downtempo", "Downtempo"), ("trip hop", "Trip hop"), ("lofi", "Lo-fi"), ("new age", "New age"),
                           ("meditation", "Meditazione"), ("relax", "Relax"), ("sleep", "Per dormire")]),
    ("🎸 Rock e Metal", [("rock", "Rock"), ("classic rock", "Classic rock"), ("hard rock", "Hard rock"),
                        ("alternative", "Alternative"), ("indie", "Indie"), ("indie rock", "Indie rock"), ("punk", "Punk"),
                        ("grunge", "Grunge"), ("progressive rock", "Progressive rock"), ("psychedelic", "Psichedelica"),
                        ("post-rock", "Post-rock"), ("metal", "Metal"), ("heavy metal", "Heavy metal"),
                        ("thrash metal", "Thrash metal"), ("death metal", "Death metal"), ("black metal", "Black metal"),
                        ("power metal", "Power metal"), ("symphonic metal", "Symphonic metal"), ("doom metal", "Doom metal"),
                        ("gothic", "Gothic"), ("rockabilly", "Rockabilly")]),
    ("🎤 Pop", [("pop", "Pop"), ("top 40", "Top 40"), ("hits", "Hit"), ("dance pop", "Dance pop"), ("synthpop", "Synthpop"),
               ("indie pop", "Indie pop"), ("k-pop", "K-pop"), ("j-pop", "J-pop"), ("italian", "Italiana"),
               ("cantautori", "Cantautori"), ("schlager", "Schlager"), ("chanson", "Chanson")]),
    ("🎷 Jazz, Blues e Soul", [("jazz", "Jazz"), ("smooth jazz", "Smooth jazz"), ("swing", "Swing"), ("bebop", "Bebop"),
                              ("big band", "Big band"), ("blues", "Blues"), ("soul", "Soul"), ("funk", "Funk"),
                              ("motown", "Motown"), ("gospel", "Gospel"), ("r&b", "R&B"), ("disco", "Disco")]),
    ("🎻 Classica", [("classical", "Classica"), ("baroque", "Barocco"), ("opera", "Opera"), ("piano", "Pianoforte"),
                    ("orchestral", "Orchestrale"), ("soundtrack", "Colonne sonore"), ("film", "Cinema"),
                    ("contemporary classical", "Contemporanea"), ("choral", "Corale")]),
    ("🎧 Hip hop e Urban", [("hip hop", "Hip hop"), ("rap", "Rap"), ("trap", "Trap"), ("rnb", "RnB"),
                           ("reggae", "Reggae"), ("dancehall", "Dancehall"), ("dub", "Dub"), ("afrobeat", "Afrobeat")]),
    ("🌍 Dal mondo", [("latin", "Latina"), ("salsa", "Salsa"), ("reggaeton", "Reggaeton"), ("bossa nova", "Bossa nova"),
                     ("samba", "Samba"), ("tango", "Tango"), ("flamenco", "Flamenco"), ("folk", "Folk"),
                     ("celtic", "Celtica"), ("country", "Country"), ("bluegrass", "Bluegrass"), ("world", "World"),
                     ("african", "Africana"), ("arabic", "Araba"), ("indian", "Indiana"), ("balkan", "Balcanica"),
                     ("greek", "Greca"), ("turkish", "Turca"), ("napoletana", "Napoletana")]),
    ("📅 Decenni", [("50s", "Anni '50"), ("60s", "Anni '60"), ("70s", "Anni '70"), ("80s", "Anni '80"),
                   ("90s", "Anni '90"), ("2000s", "Anni 2000"), ("oldies", "Oldies"), ("retro", "Retrò")]),
    ("🗞️ Parlato", [("news", "Notizie"), ("talk", "Talk"), ("sports", "Sport"), ("comedy", "Comicità"),
                   ("culture", "Cultura"), ("public radio", "Radio pubblica"), ("christian", "Cristiana"),
                   ("kids", "Per bambini")]),
]
MIN_STATIONS = 3
TAG_FIRST = 5                                     # search(): a genre among a station's first tags is its own
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _get(path: str) -> list | dict:
    with _lock:
        hit = _cache.get(path)
    if hit and time.time() - hit[0] < KEEP_S:
        return hit[1]
    last = None
    for base in SERVERS:                                  # the directory's mirrors, the next when one is down
        try:
            data = net_public.request("GET", base + path, headers=UA, timeout=15, max_bytes=4 * 1024 * 1024).raise_for_status().json()
            with _lock:
                _cache[path] = (time.time(), data)
            return data
        except Exception as e:                             # noqa: BLE001 — the next mirror
            last = e
    raise RuntimeError(f"the radio directory did not answer: {type(last).__name__}")


def genres() -> dict:
    """{"families": [{"label", "genres": [{"tag", "label", "stations"}]}], "more": [tag, …]}: every family's genres
    with their stations counted by the directory (one call, kept KEEP_S), the ones with fewer than MIN_STATIONS left
    out; «more», the directory's other tags with most stations, for a search by genre. The directory down: the
    families as they are, without counts."""
    try:
        counts = {str(t.get("name", "")).lower(): int(t.get("stationcount") or 0)
                  for t in _get("/json/tags?order=stationcount&reverse=true&hidebroken=true&limit=1500")}
    except RuntimeError:
        counts = {}
    fams, mine = [], set()
    for label, items in GENRES:
        shown = [{"tag": t, "label": n, "stations": counts.get(t)} for t, n in items
                 if not counts or counts.get(t, 0) >= MIN_STATIONS]
        mine |= {t for t, _ in items}
        if shown:
            fams.append({"label": label, "genres": shown})
    more = [t for t, n in sorted(counts.items(), key=lambda kv: -kv[1])
            if t not in mine and n >= 20 and 2 <= len(t) <= 30][:300]
    return {"families": fams, "more": more}


def _station(s: dict) -> dict:
    return {"id": s.get("stationuuid", ""), "name": str(s.get("name", "")).strip()[:120],
            "tags": str(s.get("tags", ""))[:160], "country": s.get("countrycode", ""), "codec": s.get("codec", ""),
            "bitrate": s.get("bitrate") or None, "favicon": s.get("favicon", "") if str(s.get("favicon", "")).startswith("https://") else "",
            "homepage": s.get("homepage", "")}


def search(name: str = "", tag: str = "", limit: int = 40) -> list[dict]:
    """Stations by name or genre, the most listened first, the broken ones left out. A genre is the whole tag (the
    directory's own match is a part of one: «rock» found «rockabilly»), and a station that names it among its first
    TAG_FIRST tags comes before one listing every genre (owner, 29 Oct: the same few stations under every genre)."""
    from urllib.parse import urlencode
    n = max(1, min(100, limit))
    q = {"hidebroken": "true", "order": "clickcount", "reverse": "true", "limit": str(min(200, n * 2) if tag.strip() else n)}
    if name.strip():
        q["name"] = name.strip()[:80]
    if tag.strip():
        q["tag"] = tag.strip()[:40]
        q["tagExact"] = "true"
    found = [_station(s) for s in _get("/json/stations/search?" + urlencode(q)) if s.get("stationuuid")]
    if tag.strip():
        g = tag.strip().lower()
        found.sort(key=lambda s: g not in [x.strip().lower() for x in s["tags"].split(",")][:TAG_FIRST])
    return found[:n]


def stream_url(sid: str) -> tuple[str, str]:
    """(the stream's address, the station's name) looked up by its id in the directory."""
    if not ID.fullmatch(sid or ""):
        raise ValueError("not a station id")
    found = _get(f"/json/stations/byuuid/{sid}")
    if not found:
        raise ValueError("no such station")
    s = found[0]
    return str(s.get("url_resolved") or s.get("url") or ""), str(s.get("name", ""))


def _file(folder: Path) -> Path:
    return folder / "radio.json"


def favourites(folder: Path) -> list[dict]:
    try:
        return [s for s in json.loads(_file(folder).read_text(encoding="utf-8")).get("stations", []) if ID.fullmatch(str(s.get("id", "")))]
    except (OSError, ValueError, AttributeError):
        return []


def keep(folder: Path, station: dict, on: bool) -> list[dict]:
    """A station kept (on) or let go; the list is the user's."""
    sid = str(station.get("id", ""))
    if not ID.fullmatch(sid):
        raise ValueError("not a station id")
    have = [s for s in favourites(folder) if s["id"] != sid]
    if on:
        have.append({"id": sid, "name": str(station.get("name", ""))[:120], "tags": str(station.get("tags", ""))[:160]})
    f = _file(folder)
    f.write_text(json.dumps({"stations": have[:200]}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(f, 0o600)
    return have
