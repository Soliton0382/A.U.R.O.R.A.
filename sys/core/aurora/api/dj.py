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
from fastapi.responses import FileResponse

from .core import auth, cfg, log, me, note

router = APIRouter()
AUDIO = re.compile(r"\.(mp3|wav|flac|ogg|m4a|aac|opus|webm)$", re.I)
NAME = re.compile(r"[\w\- .()'àèéìòù]{1,120}")
_busy: dict[str, dict] = {}                 # user -> the job running


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


def _list(folder) -> list[dict]:
    return [{"name": f.name, "bytes": f.stat().st_size, "at": f.stat().st_mtime}
            for f in sorted(folder.iterdir(), key=lambda f: -f.stat().st_mtime) if f.is_file() and AUDIO.search(f.name)]


@router.get("/v1/aurora/dj", dependencies=[Depends(auth)])
def dj_state() -> dict:
    from aurora import aud_dj
    d = _dir()
    lang = str(cfg["AURORA_LANG_DEFAULT"])
    return {"styles": aud_dj.styles(lang), "tracks": _list(d), "mixes": _list(d / "mixes"),
            "busy": _busy.get(me() or "", {}).get("title"), "max_minutes": cfg["AURORA_DJ_MAX_MINUTES"]}


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
    tid = sys_trash.discard(cfg, f, "music")
    return {"deleted": name, "trash": tid}


@router.get("/v1/aurora/dj/{kind}/{name}", dependencies=[Depends(auth)])
def dj_file(kind: str, name: str):
    f = _file(name, mixes=kind == "mixes")
    return FileResponse(f, media_type="audio/mpeg" if f.suffix.lower() == ".mp3" else "application/octet-stream",
                        filename=f.name, content_disposition_type="inline")


@router.post("/v1/aurora/dj/make", dependencies=[Depends(auth)])
async def dj_make(request: Request) -> dict:
    """{"tracks": [names], "style", "title"?}: one track → a remix, several → a mix; made in the background."""
    from aurora import aud_dj
    body = await request.json()
    who = me() or ""
    if who in _busy:
        raise HTTPException(status_code=409, detail=f"already mixing: {_busy[who]['title']}")
    style = str(body.get("style", ""))
    if style not in aud_dj.STYLES:
        raise HTTPException(status_code=422, detail=f"style: one of {', '.join(aud_dj.STYLES)}")
    names = [str(n) for n in body.get("tracks") or []][:12]
    paths = [_file(n) for n in names]
    if not paths:
        raise HTTPException(status_code=422, detail="choose at least one track")
    stem = re.sub(r"[^\w-]+", "-", str(body.get("title") or f"{paths[0].stem}-{style}").lower()).strip("-")[:60] or "mix"
    out = _dir() / "mixes" / f"{stem}-{time.strftime('%Y%m%d-%H%M')}.mp3"
    title = f"{', '.join(p.stem for p in paths)[:80]} → {aud_dj.STYLES[style]['it']}"
    _busy[who] = {"title": title, "since": time.time()}
    minutes = float(cfg["AURORA_DJ_MAX_MINUTES"])

    def work():
        try:
            r = aud_dj.make(paths, style, out, seconds=minutes * 60)
            note("dj", "dj.done", {"text": f"{title}: {r['seconds']:.0f} s, {r['tracks'][0]['bpm']} BPM", "file": r["file"]})
            log.info("dj: %s made %s in %s (%.0f s)", who, r["file"], style, r["seconds"])
        except Exception as e:  # noqa: BLE001 — the owner is told, never silence
            log.exception("dj failed")
            note("dj", "dj.failed", {"text": f"{title}: {type(e).__name__}: {str(e)[:150]}"})
        finally:
            _busy.pop(who, None)
    sys_context.start(work, name=f"dj-{who}")
    return {"started": True, "title": title, "file": out.name}
