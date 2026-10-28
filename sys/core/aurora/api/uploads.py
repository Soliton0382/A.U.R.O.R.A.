# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The person's files: the uploads (attached in the chat, made by Aurora) and their trash (split from api/knowledge
(ROADMAP D10): no monoliths)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import auth, cfg, log, pipeline

router = APIRouter()
_opened: dict = {}                                     # the last sealed file opened: a video's ranges, one decrypt


def _plain(path, uid: str) -> bytes:
    stamp = (uid, path.stat().st_mtime_ns)
    if _opened.get("stamp") != stamp:
        _opened.clear()
        _opened.update(stamp=stamp, data=path.read_bytes())
    return _opened["data"]


def _range(header: str, size: int) -> tuple[int, int] | None:
    """One range of «bytes=a-b» (a player seeking), clipped to the file; None: the whole file."""
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", (header or "").strip())
    if not m or not (m[1] or m[2]) or size == 0:
        return None
    if m[1]:
        start, end = int(m[1]), min(int(m[2]) if m[2] else size - 1, size - 1)
    else:                                              # «bytes=-n»: the last n bytes
        start, end = max(size - int(m[2]), 0), size - 1
    if start > end or start >= size:
        raise HTTPException(status_code=416, detail="range not satisfiable", headers={"Content-Range": f"bytes */{size}"})
    return start, end

@router.get("/v1/aurora/uploads", dependencies=[Depends(auth)])
def uploads_list() -> dict:
    from aurora import sys_uploads
    return {"files": sys_uploads.all_uploads(cfg), "total_bytes": sys_uploads.total_bytes(cfg),
            "keep_days": cfg["AURORA_UPLOADS_KEEP_DAYS"]}


@router.get("/v1/aurora/uploads/{uid}", dependencies=[Depends(auth)])
def upload_get(uid: str, request: Request):
    """Images, videos and audio inline; anything else only as a download (an HTML or SVG never runs here)."""
    from fastapi.responses import FileResponse
    from aurora import sys_uploads
    found = sys_uploads.get(cfg, uid) if re.fullmatch(r"[0-9a-f]{16}", uid) else None
    if found is None:
        raise HTTPException(status_code=404, detail="no such file")
    path, item = found
    inline = bool(sys_uploads.INLINE.match(item["mime"]))
    media = item["mime"] if inline else "application/octet-stream"
    headers = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox",
               "Cache-Control": "private, max-age=86400"}
    from aurora import sys_seal
    with open(path, "rb") as f:
        plain = f.read(len(sys_seal.MAGIC)) != sys_seal.MAGIC
    if plain:                                          # never sealed (before N64, Aurora's own media): as a file
        return FileResponse(path, media_type=media, filename=item["name"],
                            content_disposition_type="inline" if inline else "attachment", headers=headers)
    try:                                               # sealed with its owner's key (N64): opened here, in memory
        data = _plain(path, uid)
    except ValueError:
        raise HTTPException(status_code=404, detail="no such file") from None
    from urllib.parse import quote
    from fastapi.responses import Response
    headers["Content-Disposition"] = f"{'inline' if inline else 'attachment'}; filename*=utf-8''{quote(item['name'])}"
    headers["Accept-Ranges"] = "bytes"
    span = _range(request.headers.get("range", ""), len(data))
    if span is None:
        return Response(content=data, media_type=media, headers=headers)
    headers["Content-Range"] = f"bytes {span[0]}-{span[1]}/{len(data)}"   # a video seeking (as a plain file does)
    return Response(content=data[span[0]:span[1] + 1], status_code=206, media_type=media, headers=headers)


@router.delete("/v1/aurora/uploads/{uid}", dependencies=[Depends(auth)])
def upload_delete(uid: str) -> dict:
    from aurora import sys_uploads
    if not sys_uploads.delete(cfg, uid):
        raise HTTPException(status_code=404, detail="no such file")
    log.info("audit: owner deleted an attached file (%s)", uid)
    return {"deleted": uid}


@router.get("/v1/aurora/trash", dependencies=[Depends(auth)])
def trash_list() -> dict:
    from aurora import sys_trash
    return {"items": sys_trash.items(cfg), "enabled": bool(cfg["AURORA_TRASH_ENABLED"]), "days": cfg["AURORA_TRASH_DAYS"]}


@router.post("/v1/aurora/trash/{tid}/restore", dependencies=[Depends(auth)])
def trash_restore(tid: str) -> dict:
    from aurora import sys_trash, sys_uploads
    back = sys_trash.restore(cfg, tid)
    if back is None:
        raise HTTPException(status_code=404, detail="not in the trash")
    path, meta = back
    if meta["kind"] == "upload" and meta.get("record"):
        sys_uploads.reindex(cfg, meta["record"], path)
    log.info("audit: %s restored from the trash", meta["name"])
    return {"restored": meta["name"]}


@router.delete("/v1/aurora/trash/{tid}", dependencies=[Depends(auth)])
def trash_remove(tid: str) -> dict:
    """One item removed for good; "all" empties the trash."""
    from aurora import sys_trash
    ids = [i["id"] for i in sys_trash.items(cfg)] if tid == "all" else [tid]
    gone = sum(sys_trash.remove(cfg, i) for i in ids)
    if not gone and tid != "all":
        raise HTTPException(status_code=404, detail="not in the trash")
    log.info("audit: %d items removed from the trash", gone)
    return {"removed": gone}


@router.post("/v1/aurora/uploads/purge", dependencies=[Depends(auth)])
def uploads_purge() -> dict:
    """aurora-rem, daily: files whose conversation turn is gone, and those older than AURORA_UPLOADS_KEEP_DAYS."""
    from aurora import sys_uploads
    live = {t.extra.get("run_id") for t in pipeline().reader.recent(1_000_000)} - {None}
    removed = sys_uploads.purge(cfg, live)
    if removed:
        log.info("uploads purge: %d files removed", len(removed))
    from aurora import sys_trash                       # the same daily round empties every user's expired trash
    expired = sys_trash.expire(cfg)
    if expired:
        log.info("trash: %d expired items removed", expired)
    return {"removed": len(removed), "trash_expired": expired}
