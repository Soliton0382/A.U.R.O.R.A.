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


def _station(s: dict) -> dict:
    return {"id": s.get("stationuuid", ""), "name": str(s.get("name", "")).strip()[:120],
            "tags": str(s.get("tags", ""))[:160], "country": s.get("countrycode", ""), "codec": s.get("codec", ""),
            "bitrate": s.get("bitrate") or None, "favicon": s.get("favicon", "") if str(s.get("favicon", "")).startswith("https://") else "",
            "homepage": s.get("homepage", "")}


def search(name: str = "", tag: str = "", limit: int = 40) -> list[dict]:
    """Stations by name or genre, the most listened first, the broken ones left out."""
    from urllib.parse import urlencode
    q = {"hidebroken": "true", "order": "clickcount", "reverse": "true", "limit": str(max(1, min(100, limit)))}
    if name.strip():
        q["name"] = name.strip()[:80]
    if tag.strip():
        q["tag"] = tag.strip()[:40]
    return [_station(s) for s in _get("/json/stations/search?" + urlencode(q)) if s.get("stationuuid")]


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
