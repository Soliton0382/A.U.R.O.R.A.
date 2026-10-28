# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's DJ (owner, 2026-10-05): the user's tracks, a remix or a mix made in the background, the mixes to play.

Everything in the user's AURORA_MUSIC_DIR (usr/<name>/music): the tracks at its top, the results in mixes/. One job
at a time per user; the result is told by a notification (dj.done). Only the user's own files are read or served.
"""
from __future__ import annotations

import base64
import binascii
import re
import time

from aurora import sys_context
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from .core import auth, cfg, in_thread, log, me, note, pipeline

router = APIRouter()
AUDIO = re.compile(r"\.(mp3|wav|flac|ogg|m4a|aac|opus|webm)$", re.I)
NAME = re.compile(r"[\w\- .()'àèéìòù]{1,120}")
_busy: dict[str, dict] = {}                 # user -> the job running
_learnt: dict[str, dict] = {}               # user -> how their last 🎓 listen ended (the page shows it)
_listening: dict[str, dict] = {}            # user -> {"title", "at"}: the player playing (her mood: 🎧)
LISTEN_S = 75                               # the page says it every 30 s: two missed and she has stopped listening


def _dir():
    d = cfg.path("AURORA_MUSIC_DIR")
    (d / "mixes").mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _file(name: str, mixes: bool = False):
    if not NAME.fullmatch(name or "") or name.startswith(".") or not AUDIO.search(name):
        raise HTTPException(status_code=404, detail="no such track")
    f = _dir() / ("mixes" if mixes else "") / name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such track")
    return f


def _pick(ref: str):
    """A track to mix: an uploaded one by its name, or one of the mixes — a song Aurora sang, a remix — as «mixes/<name>»
    (owner, 27 Oct: «le canzoni create e caricate finiscono nel player ma si possono selezionare per il mix»)."""
    return _file(ref.removeprefix("mixes/"), mixes=True) if ref.startswith("mixes/") else _file(ref)


def _list(folder) -> list[dict]:
    return [{"name": f.name, "bytes": f.stat().st_size, "at": f.stat().st_mtime, "set": f.with_suffix(".json").is_file(),
             "song": f.with_suffix(".song.json").is_file()}
            for f in sorted(folder.iterdir(), key=lambda f: -f.stat().st_mtime) if f.is_file() and AUDIO.search(f.name)]


@router.get("/v1/aurora/dj", dependencies=[Depends(auth)])
def dj_state() -> dict:
    from aurora import aud_dj
    d = _dir()
    lang = str(cfg["AURORA_LANG_DEFAULT"])
    from aurora import aud_playlists, aud_song, aud_song_style
    tracks, mixes = _list(d), _list(d / "mixes")
    have = {t["name"] for t in tracks} | {f"mixes/{m['name']}" for m in mixes}
    return {"styles": aud_dj.styles(lang), "tracks": tracks, "mixes": mixes, "song": aud_song.installed(cfg),
            "playlists": aud_playlists.load(d, have),
            "spotify": {"client_id": str(cfg["AURORA_SPOTIFY_CLIENT_ID"] or "").strip()},
            "song_style": aud_song_style.options(lang),
            "busy": _busy.get(me() or "", {}).get("title"), "max_minutes": cfg["AURORA_DJ_MAX_MINUTES"]}


@router.put("/v1/aurora/dj/playlists", dependencies=[Depends(auth)])
async def dj_playlists(request: Request) -> dict:
    """{"lists": [{"id"?, "name", "items": [track refs]}]}: the player's folders, saved whole (aud_playlists)."""
    from aurora import aud_playlists
    try:
        return {"lists": aud_playlists.save(_dir(), (await request.json()).get("lists"))}
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("/v1/aurora/dj/tracks", dependencies=[Depends(auth)])
async def dj_upload(request: Request) -> dict:
    """{"name", "data": base64}: a track of the user's (their own music, at most 100 MB)."""
    body = await request.json()
    name = re.sub(r"[^\w\- .()'àèéìòù]", "_", str(body.get("name", "")).strip())[-120:].lstrip(".")
    if not AUDIO.search(name):
        raise HTTPException(status_code=422, detail="an audio file: mp3, wav, flac, ogg, m4a, aac, opus, webm")
    try:
        data = base64.b64decode(str(body.get("data", "")), validate=True)
    except binascii.Error:
        raise HTTPException(status_code=422, detail="data is not valid base64") from None
    if not data or len(data) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="the file is empty or larger than 100 MB")
    f = _dir() / name
    f.write_bytes(data)
    f.chmod(0o600)
    log.info("audit: %s added a track for the DJ (%d bytes)", me(), len(data))
    return {"name": name, "bytes": len(data)}


@router.delete("/v1/aurora/dj/{kind}/{name}", dependencies=[Depends(auth)])
def dj_delete(kind: str, name: str) -> dict:
    from aurora import sys_trash
    f = _file(name, mixes=kind == "mixes")
    beside = [f.with_suffix(".json"), f.with_suffix(".song.json")]   # a set's timeline, a song's lyrics: with it
    tid = sys_trash.discard(cfg, f, "music")
    for extra in beside if kind == "mixes" else []:
        if extra.is_file():
            sys_trash.discard(cfg, extra, "music")
    return {"deleted": name, "trash": tid}


@router.get("/v1/aurora/dj/{kind}/{name}", dependencies=[Depends(auth)])
def dj_file(kind: str, name: str, download: bool = False):
    """A track to play, or with ?download=1 to keep (the player's ⬇️; the phone app saves it to Downloads)."""
    f = _file(name, mixes=kind == "mixes")
    return FileResponse(f, media_type="audio/mpeg" if f.suffix.lower() == ".mp3" else "application/octet-stream",
                        filename=f.name, content_disposition_type="attachment" if download else "inline")


@router.post("/v1/aurora/dj/make", dependencies=[Depends(auth)])
async def dj_make(request: Request) -> dict:
    """{"tracks": [names], "style", "title"?, "deck"?}: one track → a remix, several → a mix; two with "deck" (the
    user's choices: aud_deck.options) → the two-deck mixer. Made in the background."""
    from aurora import aud_deck, aud_dj
    body = await request.json()
    deck = body.get("deck")
    if deck is not None:
        try:
            aud_deck.options(deck if isinstance(deck, dict) else {})
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail=f"deck: {e}") from None
    who = me() or ""
    if who in _busy:
        raise HTTPException(status_code=409, detail=f"already mixing: {_busy[who]['title']}")
    style = str(body.get("style", ""))
    try:
        named = aud_dj.find(style).get("it", style)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    names = [str(n) for n in body.get("tracks") or []][:12]
    paths = [_pick(n) for n in names]
    if not paths:
        raise HTTPException(status_code=422, detail="choose at least one track")
    stem = re.sub(r"[^\w-]+", "-", str(body.get("title") or f"{paths[0].stem}-{style}").lower()).strip("-")[:60] or "mix"
    out = _dir() / "mixes" / f"{stem}-{time.strftime('%Y%m%d-%H%M')}.mp3"
    if deck is not None and len(paths) != 2:
        raise HTTPException(status_code=422, detail="the two decks take two tracks")
    title = (f"{paths[0].stem[:38]} × {paths[1].stem[:38]} (🎚️)" if deck is not None
             else f"{', '.join(p.stem for p in paths)[:80]} → {named}")
    _busy[who] = {"title": title, "since": time.time()}
    minutes = float(cfg["AURORA_DJ_MAX_MINUTES"])

    def work():
        try:
            r = aud_dj.make(paths, style, out, seconds=minutes * 60, deck=deck)
            note("dj", "dj.done", {"text": f"{title}: {r['seconds']:.0f} s, {r['tracks'][0]['bpm']} BPM", "file": r["file"]})
            log.info("dj: %s made %s in %s (%.0f s)", who, r["file"], style, r["seconds"])
        except Exception as e:  # noqa: BLE001 — the owner is told, never silence
            log.exception("dj failed")
            note("dj", "dj.failed", {"text": f"{title}: {type(e).__name__}: {str(e)[:150]}"})
        finally:
            _busy.pop(who, None)
    sys_context.start(work, name=f"dj-{who}")
    return {"started": True, "title": title, "file": out.name}

@router.post("/v1/aurora/dj/learn", dependencies=[Depends(auth)])
async def dj_learn(request: Request) -> dict:
    """{"station": id, "seconds"?: 45-900, "name"?} or {"track": name}: 🎓 the DJ learns a style from the radio or
    from one of the user's own tracks (aud_learn) — the radio heard in memory and let go, only the style kept. In the
    background; told when done (and GET says how far it is)."""
    from aurora import aud_analysis, aud_learn
    body = await request.json()
    who, sid = me() or "", str(body.get("station") or "")
    track = _pick(str(body["track"])) if body.get("track") else None       # 404 when it is not theirs
    if track is None and not sid:
        raise HTTPException(status_code=422, detail="a station or one of your tracks")
    if who in _busy:
        raise HTTPException(status_code=409, detail=f"already busy: {_busy[who]['title']}")
    seconds = max(aud_learn.SECONDS[0], min(aud_learn.SECONDS[1], float(body.get("seconds") or 150)))   # up to 15 min
    title = f"🎓 {str(body.get('name') or '').strip()[:60] or (track.stem[:60] if track else 'radio')}"
    if track is not None:
        seconds = 0.0                                     # a file: nothing to wait for, straight to the analysis
    import threading
    stop = threading.Event()
    _busy[who] = {"title": title, "since": time.time(), "learn": True, "seconds": seconds, "stop": stop,
                  "phase": "analysing" if track is not None else "listening"}
    _learnt.pop(who, None)
    folder = _dir()

    def work():
        try:
            if track is not None:
                x, station = aud_analysis.load(track, 600), track.stem   # the first ten minutes are plenty
            else:
                x, station = aud_learn.record(sid, seconds, stop)
            _busy[who]["phase"] = "analysing"
            try:
                style = aud_learn.learn(x)
            finally:
                del x                                     # the audio heard: never kept
            sid_ = aud_learn.save(folder, str(body.get("name") or (track.stem if track else "")), style, station)
            text = f"{title}: {style['bpm']} BPM, cassa {style['kick']}, clap {style['clap']}"
            note("dj", "dj.learned", {"text": text, "style": sid_})
            _learnt[who] = {"ok": True, "text": text, "style": sid_, "at": time.time()}
            log.info("dj: %s learnt %s from %s", who, sid_, "a track" if track is not None else f"a radio ({seconds:.0f} s heard)")
        except Exception as e:  # noqa: BLE001 — the owner is told, never silence
            log.warning("dj learn failed: %s", e)
            note("dj", "dj.learn_failed", {"text": f"{title}: {str(e)[:200]}"})
            _learnt[who] = {"ok": False, "text": f"{title}: {str(e)[:200]}", "at": time.time()}
        finally:
            _busy.pop(who, None)
    sys_context.start(work, name=f"dj-learn-{who}")
    return {"started": True, "title": title, "seconds": seconds}


@router.post("/v1/aurora/dj/learn/stop", dependencies=[Depends(auth)])
def dj_learn_stop() -> dict:
    """🎓 «Fine»: the listen ends now and the DJ learns from what it heard."""
    job = _busy.get(me() or "")
    if not job or not job.get("learn"):
        raise HTTPException(status_code=409, detail="no listen going on")
    job["stop"].set()
    return {"stopping": True}


@router.get("/v1/aurora/dj/learn", dependencies=[Depends(auth)])
def dj_learn_state() -> dict:
    """The 🎓 listen going on (its seconds, elapsed, listening or analysing), or how the last one ended."""
    who = me() or ""
    job = _busy.get(who)
    if job and job.get("learn"):
        return {"running": True, "title": job["title"], "seconds": job["seconds"], "phase": job["phase"],
                "elapsed": round(time.time() - job["since"], 1), "stopping": job["stop"].is_set()}
    return {"running": False, "last": _learnt.get(who)}


@router.get("/v1/aurora/dj/styles/{sid}/preview", dependencies=[Depends(auth)])
async def dj_style_preview(sid: str) -> Response:
    """▶ How a style sounds: 16 bars of the DJ's own drums and bass in it, over silence (0.3 s to make), never kept."""
    from aurora import aud_dj

    def make() -> bytes:
        import subprocess
        import numpy as np
        from aurora.aud_analysis import SR
        st = aud_dj.find(sid)
        bpm = float(st.get("bpm") or 124)
        with np.errstate(all="ignore"):                   # silence has no key: the analysis divides by zero there
            y, _ = aud_dj.remix(np.zeros((int(16 * 4 * 60 / bpm * SR), 2), np.float32), sid)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2",
                            "-i", "-", "-af", "loudnorm=I=-14:TP=-1.0", "-b:a", "160k", "-f", "mp3", "-"],
                           input=np.clip(y, -1, 1).astype(np.float32).tobytes(), capture_output=True, timeout=60)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError("the preview could not be encoded")
        return r.stdout
    try:
        mp3 = await in_thread(make)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return Response(mp3, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.delete("/v1/aurora/dj/styles/{sid}", dependencies=[Depends(auth)])
def dj_style_delete(sid: str) -> dict:
    """A style the DJ learnt, forgotten (the DJ's own cannot be)."""
    from aurora import aud_learn
    if not sid.startswith(aud_learn.PREFIX) or not aud_learn.delete(_dir(), sid):
        raise HTTPException(status_code=404, detail="no such learnt style")
    return {"deleted": sid}


@router.post("/v1/aurora/dj/set", dependencies=[Depends(auth)])
async def dj_set(request: Request) -> dict:
    """{"tracks": [names], "keep_order"?: bool, "bars"?: 8|16|32, "title"?}: Aurora's set (aud_set) — the order by key
    and tempo unless kept, each track in on the beat of the one ending. Made in the background; its timeline beside it."""
    from aurora import aud_set
    body = await request.json()
    who = me() or ""
    if who in _busy:
        raise HTTPException(status_code=409, detail=f"already mixing: {_busy[who]['title']}")
    names = [str(n) for n in body.get("tracks") or []][:20]
    paths = [_pick(n) for n in names]
    if len(paths) < 2:
        raise HTTPException(status_code=422, detail="a set takes at least two tracks")
    bars = int(body.get("bars") or 16)
    if bars not in (8, 16, 32):
        raise HTTPException(status_code=422, detail="bars: 8, 16 or 32")
    keep = bool(body.get("keep_order"))
    stem = re.sub(r"[^\w-]+", "-", str(body.get("title") or "set").lower()).strip("-")[:60] or "set"
    out = _dir() / "mixes" / f"{stem}-{time.strftime('%Y%m%d-%H%M')}.mp3"
    title = f"🎛️ Set: {len(paths)} brani"
    _busy[who] = {"title": title, "since": time.time()}
    minutes = float(cfg["AURORA_DJ_MAX_MINUTES"])

    def work():
        try:
            r = aud_set.make(paths, out, keep_order=keep, bars=bars, seconds=minutes * 60)
            note("dj", "dj.done", {"text": f"{title}: {r['seconds'] / 60:.0f} min a {r['bpm']} BPM", "file": r["file"]})
            log.info("dj: %s made the set %s (%d tracks, %.0f s)", who, r["file"], len(paths), r["seconds"])
        except Exception as e:  # noqa: BLE001 — the owner is told, never silence
            log.exception("dj set failed")
            note("dj", "dj.failed", {"text": f"{title}: {type(e).__name__}: {str(e)[:150]}"})
        finally:
            _busy.pop(who, None)
    sys_context.start(work, name=f"djset-{who}")
    return {"started": True, "title": title, "file": out.name}


@router.get("/v1/aurora/dj-timeline/{name}", dependencies=[Depends(auth)])   # not under /dj/{kind}/{name}
def dj_timeline(name: str) -> dict:
    """A set's timeline (aud_set): each track's place, the transitions, the waveform — the console draws it."""
    import json
    f = _file(name, mixes=True).with_suffix(".json")
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no timeline: not a set")
    return json.loads(f.read_text(encoding="utf-8"))


@router.post("/v1/aurora/dj/song", dependencies=[Depends(auth)])
async def dj_song(request: Request) -> dict:
    """{"idea", "language"?: en|it|…, "seconds"?: 30-300, "lyrics"?, "caption"?, "title"?}: a song from an idea
    (aud_song) — the local reasoner writes it, then the music model sings it with the reasoner out of the GPU; made in
    the background. With lyrics and caption both given (the player's «sing it again»), nothing is written: sung as is."""
    from aurora import aud_song
    body = await request.json()
    who = me() or ""
    if who in _busy:
        raise HTTPException(status_code=409, detail=f"already working: {_busy[who]['title']}")
    idea = str(body.get("idea") or "").strip()[:1500]
    lyrics = str(body.get("lyrics") or "").strip()[:6000]
    if len(idea) < 8 and not lyrics:
        raise HTTPException(status_code=422, detail="describe the song in a few words")
    lang = str(body.get("language") or "en")
    if lang not in aud_song.LANGS:
        raise HTTPException(status_code=422, detail=f"language: one of {', '.join(aud_song.LANGS)}")
    seconds = int(body.get("seconds") or 180)
    if not 30 <= seconds <= 300:
        raise HTTPException(status_code=422, detail="seconds: 30 to 300")
    have = aud_song.installed(cfg)
    if not (have["code"] and have["weights"]):
        raise HTTPException(status_code=409, detail="the music model is not installed yet (DJ page: how to)")
    from aurora import aud_song_style                     # the dress: genre, arrangement, voice, tempo, key, boldness
    try:
        style = aud_song_style.check(body.get("style") if isinstance(body.get("style"), dict) else {})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    caption = str(body.get("caption") or "").strip()[:600]
    given = None
    if caption and lyrics:                                # sung again — in other clothes when a dress is chosen
        r = aud_song_style.resolve(style)
        given = {"title": str(body.get("title") or idea[:40] or "canzone").strip()[:80],
                 "caption": aud_song_style.redress(caption, style) if style else caption,
                 "lyrics": "[instrumental]" if r["instrumental"] else lyrics, "language": lang, "style": style,
                 **{k: r[k] for k in ("bpm", "key_scale", "lm_temperature", "negative", "time_signature", "inference_steps", "lm_cfg_scale") if k in r}}
    title = f"🎤 {(given or {}).get('title') or idea[:60] or 'canzone'}"
    _busy[who] = {"title": title, "since": time.time()}

    def work():
        try:
            song = given or aud_song.write(pipeline().llm, idea or "a song on these lyrics", lang, lyrics, style)
            stem = re.sub(r"[^\w-]+", "-", song["title"].lower()).strip("-")[:50] or "song"
            out = _dir() / "mixes" / f"{stem}-{time.strftime('%Y%m%d-%H%M')}.mp3"
            r = aud_song.sing(cfg, song, seconds, out)
            note("dj", "dj.done", {"text": f"🎤 {song['title']}: pronta ({r['seconds'] / 60:.0f} min di lavoro)", "file": r["file"]})
            log.info("dj: %s made the song %s (%s, %d s)", who, r["file"], lang, seconds)
        except Exception as e:  # noqa: BLE001 — the owner is told, never silence
            log.exception("dj song failed")
            note("dj", "dj.failed", {"text": f"{title}: {type(e).__name__}: {str(e)[:150]}"})
        finally:
            _busy.pop(who, None)
    sys_context.start(work, name=f"djsong-{who}")
    return {"started": True, "title": title}


@router.get("/v1/aurora/dj-song/{name}", dependencies=[Depends(auth)])
def dj_song_text(name: str) -> dict:
    """A song's lyrics and caption, as the reasoner wrote them."""
    import json
    f = _file(name, mixes=True).with_suffix(".song.json")
    if not f.is_file():
        raise HTTPException(status_code=404, detail="not a song")
    return json.loads(f.read_text(encoding="utf-8"))


@router.put("/v1/aurora/dj-song/{name}", dependencies=[Depends(auth)])
async def dj_song_edit(name: str, request: Request) -> dict:
    """{"title"?, "lyrics"?, "caption"?}: a song's words changed (the player's ✏️); the audio stays as it was sung —
    «sing it again» makes a new one from them."""
    import json
    f = _file(name, mixes=True).with_suffix(".song.json")
    if not f.is_file():
        raise HTTPException(status_code=404, detail="not a song")
    body = await request.json()
    song = json.loads(f.read_text(encoding="utf-8"))
    for k, most in (("title", 80), ("lyrics", 6000), ("caption", 600)):
        if isinstance(body.get(k), str) and body[k].strip():
            song[k] = body[k].strip()[:most]
    f.write_text(json.dumps(song, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("dj: %s edited the words of %s", me(), name)
    return song


@router.post("/v1/aurora/dj/listening", dependencies=[Depends(auth)])
async def dj_listening(request: Request) -> dict:
    """{"playing": bool, "title"}: the music player says what it plays, every half minute (her mood shows 🎧)."""
    body = await request.json()
    who = me() or ""
    if body.get("playing"):
        _listening[who] = {"title": str(body.get("title") or "")[:120], "at": time.time()}
    else:
        _listening.pop(who, None)
    return {"listening": who in _listening}


def listening(who: str) -> dict | None:
    """What this user's player plays now, or None (silent, or no word for LISTEN_S)."""
    x = _listening.get(who or "")
    return x if x and time.time() - x["at"] < LISTEN_S else None
