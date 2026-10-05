# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Knowledge and memory: import, solitons, sources, domains, uploads, harvester, update, senses, REM tasks."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import subprocess
import threading
import time

from aurora import sys_config, sys_features
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import _run_lock, _state, auth, cfg, log, note, pipeline, start_run

router = APIRouter()


# ---- knowledge import -------------------------------------------------------------------------
@router.get("/v1/aurora/domains", dependencies=[Depends(auth)])
def domains() -> list[dict]:
    from aurora.sol_schema import load_taxonomy
    return [d for d in load_taxonomy().values() if not d.get("memory")]


def _import(name: str, data: bytes, domain: str, title: str, origin: str = "upload", meta: dict | None = None) -> dict:
    from aurora.kno_ingest import Importer
    p = pipeline()
    with _run_lock:                                   # vault and index have one writer: this process
        rep = Importer(p.writer, p.indexer, cfg, llm=p.llm).add(name, data, domain, title, origin=origin, meta=meta)
    return {"name": rep.name, "source_id": rep.source_id, "domain": rep.domain, "chunks": rep.chunks,
            "written": rep.written, "duplicates": rep.duplicates, "rejected": rep.rejected, "indexed": rep.indexed}


@router.post("/v1/aurora/import", dependencies=[Depends(auth)])
async def import_document(request: Request) -> dict:
    body = await request.json()
    from aurora.sol_schema import load_taxonomy
    taxonomy = load_taxonomy()
    domain = body.get("domain", "")
    if domain not in taxonomy or taxonomy[domain].get("memory"):
        raise HTTPException(status_code=422, detail=f"unknown knowledge domain {domain!r}")
    try:
        data = base64.b64decode(body.get("data", ""), validate=True)
    except binascii.Error:
        raise HTTPException(status_code=422, detail="data is not valid base64")
    if not data:
        raise HTTPException(status_code=422, detail="empty document")
    try:
        return await asyncio.to_thread(_import, os.path.basename(body.get("name", "document.txt")), data, domain,
                                       body.get("title", "").strip(), body.get("origin", "upload"),
                                       {"licence": body.get("licence", ""), "url": body.get("url", "")})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _add_solitons(items: list[dict]) -> dict:
    from aurora.sol_schema import Soliton
    p = pipeline()
    sols = [Soliton.new(x["text"], x["domain"], "knowledge", x.get("lang") or "en", x["source_id"], x.get("title", ""),
                        chunk_index=int(x.get("chunk_index", 0)), chunk_count=int(x.get("chunk_count", 1)),
                        extra=x.get("extra") or {}) for x in items]
    with _run_lock:                                   # vault and index have one writer: this process
        rep = p.writer.add_many(sols)
        indexed = {d: p.indexer.update(d) for d in sorted({s.domain for s in sols})} if rep.written else {}
    return {"received": len(items), "written": len(rep.written), "duplicates": len(rep.duplicates),
            "rejected": rep.rejected, "indexed": indexed}


@router.post("/v1/aurora/solitons", dependencies=[Depends(auth)])
async def add_solitons(request: Request) -> dict:
    items = (await request.json()).get("items", [])
    from aurora.sol_schema import load_taxonomy
    taxonomy = load_taxonomy()
    bad = sorted({x.get("domain") for x in items if x.get("domain") not in taxonomy or taxonomy[x["domain"]].get("memory")})
    if bad:
        raise HTTPException(status_code=422, detail=f"not knowledge domains: {bad}")
    if any(not x.get("source_id") for x in items):
        raise HTTPException(status_code=422, detail="every item needs a source_id")
    # an empty or invalid text is not an error of the batch: the writer rejects that soliton and reports it
    return await asyncio.to_thread(_add_solitons, items)


@router.delete("/v1/aurora/sources", dependencies=[Depends(auth)])
async def remove_source(domain: str, source_id: str) -> dict:
    from aurora.sol_schema import load_taxonomy
    if domain not in load_taxonomy():
        raise HTTPException(status_code=422, detail=f"unknown domain {domain!r}")

    def work():
        p = pipeline()
        with _run_lock:
            sids = p.writer.remove_source(domain, source_id)
            return {"domain": domain, "source_id": source_id, "removed": len(sids),
                    "index_rows_removed": p.indexer.drop(domain, sids)}
    out = await asyncio.to_thread(work)
    if not out["removed"]:
        raise HTTPException(status_code=404, detail="no solitons of that source in that domain")
    return out


@router.post("/v1/aurora/memory/reset", dependencies=[Depends(auth)])
async def reset_memory(request: Request) -> dict:
    if (await request.json()).get("confirm") is not True:
        raise HTTPException(status_code=400, detail='send {"confirm": true}: this deletes every conversation')

    def work():
        with _run_lock:
            files = pipeline().writer.reset_memory(confirm=True)
            _state.pop("pipeline", None)          # readers and indexes start again from the new state
            from aurora import sys_uploads
            uploads = sys_uploads.purge(cfg, set(), grace=0)     # no turn left: no attached file either
            return {"files_removed": files, "uploads_removed": len(uploads)}
    return await asyncio.to_thread(work)


@router.get("/v1/aurora/history", dependencies=[Depends(auth)])
def history(n: int = 8) -> list[dict]:
    turns = pipeline().reader.recent(max(0, min(n, 100)))
    items = [{"sid": t.sid, "role": t.extra.get("role"), "text": t.text, "created_at": t.created_at,
             "run_id": t.extra.get("run_id"), "abstained": t.extra.get("abstained", False),
             "mode": t.extra.get("mode"), "seconds": t.extra.get("seconds"), "speed": t.extra.get("speed"),
             "sources": t.extra.get("source_list", []), "trace": t.extra.get("trace", []),
             "thought": t.extra.get("thought", ""), "suggestions": t.extra.get("suggestions", []),
             "long_term": t.consolidated} for t in turns]
    from aurora import sys_uploads
    files = sys_uploads.by_run(cfg, {i["run_id"] for i in items if i["run_id"]})
    for i in items:                                   # the owner's files with his turn, Aurora's (edits) with hers
        i["attachments"] = [f for f in files.get(i["run_id"], []) if f["role"] == ("user" if i["role"] == "user" else "assistant")]
    return sorted(items + recent_dreams(), key=lambda x: x["created_at"])          # same UTC ISO format


@router.get("/v1/aurora/uploads", dependencies=[Depends(auth)])
def uploads_list() -> dict:
    from aurora import sys_uploads
    return {"files": sys_uploads.all_uploads(cfg), "total_bytes": sys_uploads.total_bytes(cfg),
            "keep_days": cfg["AURORA_UPLOADS_KEEP_DAYS"]}


@router.get("/v1/aurora/uploads/{uid}", dependencies=[Depends(auth)])
def upload_get(uid: str):
    """Images, videos and audio inline; anything else only as a download (an HTML or SVG never runs here)."""
    from fastapi.responses import FileResponse
    from aurora import sys_uploads
    found = sys_uploads.get(cfg, uid) if re.fullmatch(r"[0-9a-f]{16}", uid) else None
    if found is None:
        raise HTTPException(status_code=404, detail="no such file")
    path, item = found
    inline = bool(sys_uploads.INLINE.match(item["mime"]))
    return FileResponse(path, media_type=item["mime"] if inline else "application/octet-stream",
                        filename=item["name"], content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox",
                                 "Cache-Control": "private, max-age=86400"})


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


def recent_dreams() -> list[dict]:
    """Last nights' dreams, shown in the chat among the turns (AURORA_CHAT_DREAM_HOURS; 0 = never)."""
    from datetime import datetime, timedelta, timezone
    hours = cfg["AURORA_CHAT_DREAM_HOURS"]
    if not hours:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    dreams = [d for d in pipeline().reader.recent(100, domain="reflection")
              if d.extra.get("type") == "dream" and datetime.fromisoformat(d.created_at) >= since]
    return [{"sid": d.sid, "role": "dream", "text": d.text, "created_at": d.created_at,
             "image": f"/v1/aurora/images/{d.extra['image']}" if d.extra.get("image") else None,
             "image_prompt": d.extra.get("image_prompt", "")} for d in dreams[-2:]]


@router.get("/v1/aurora/senses/devices", dependencies=[Depends(auth)])
def senses_devices() -> dict:
    from aurora import sns_av
    return {**sns_av.devices(), "camera": cfg["AURORA_SENSES_CAMERA"], "microphone": cfg["AURORA_SENSES_MIC"]}


@router.post("/v1/aurora/senses/{action}", dependencies=[Depends(auth)])
async def senses_action(action: str, request: Request) -> dict:
    """The owner's own click in the WebUI (📷, 🎙️): consent is the click itself, no approval needed."""
    from aurora import sns_av
    if action in ("listen", "transcribe"):
        try:
            sys_features.need(cfg, "speech", str(cfg["AURORA_LANG_DEFAULT"]))
        except sys_features.Missing as e:
            raise HTTPException(status_code=409, detail=str(e))
    try:
        if action == "photo":
            jpeg = await asyncio.to_thread(sns_av.photo, cfg)
            log.info("audit: owner took a photo from the camera (%d bytes)", len(jpeg))
            return {"name": time.strftime("camera-%Y%m%d-%H%M%S.jpg"), "mime": "image/jpeg",
                    "data": base64.b64encode(jpeg).decode("ascii")}
        if action == "listen":
            seconds = float((await request.json()).get("seconds", 6))
            audio = await asyncio.to_thread(sns_av.record, seconds, cfg)
            out = await asyncio.to_thread(sns_av.transcribe, audio, str(cfg["AURORA_LANG_DEFAULT"])[:2], cfg)
            log.info("audit: owner dictated %.1f s (clear: %s)", out["audio_s"], out["clear"])
            return out
        if action == "transcribe":                       # the owner's own device (phone, PC browser) recorded it
            body = await request.json()
            try:
                data = base64.b64decode(str(body.get("data", "")), validate=True)
            except binascii.Error:
                raise HTTPException(status_code=422, detail="data is not valid base64")
            if not data or len(data) > 20 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="audio missing or larger than 20 MB")
            try:
                audio = await asyncio.to_thread(sns_av.decode, data, cfg)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            out = await asyncio.to_thread(sns_av.transcribe, audio, str(cfg["AURORA_LANG_DEFAULT"])[:2], cfg)
            log.info("audit: owner dictated %.1f s from a device (%s, %d bytes; clear: %s)", out["audio_s"],
                     str(body.get("mime", "?"))[:40], len(data), out["clear"])
            return out
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    raise HTTPException(status_code=404, detail="unknown action")


@router.get("/v1/aurora/features", dependencies=[Depends(auth)])
def features() -> dict:
    """What this installation can do, what is missing for the rest (and how to add it), contradicting settings."""
    return {"features": sys_features.report(cfg), "config": sys_features.config_problems(cfg)}


@router.get("/v1/aurora/update", dependencies=[Depends(auth)])
def update_info() -> dict:
    from aurora import sys_update
    return {**sys_update.last(cfg), "mode": cfg["AURORA_UPDATE_MODE"]}


@router.post("/v1/aurora/update/check", dependencies=[Depends(auth)])
async def update_check() -> dict:
    """Fetch and compare; new commits become a notification and an approval (notify), or are applied (auto, when safe)."""
    from aurora import sys_update
    from aurora.sys_approvals import Approvals
    info = await asyncio.to_thread(sys_update.check, cfg)
    if info.get("error") or not info.get("commits"):
        return info
    pending = [a for a in Approvals(cfg).list("pending") if a["kind"] == "update"]
    if pending and pending[-1]["action"].get("to") == info["there"]:
        return {**info, "approval": pending[-1]["id"]}           # already asked for this version
    text = sys_update.changelog(info, "it")
    note("update", "update.available", {"text": f"{info['behind']} novità: " + "; ".join(c["subject"] for c in info["commits"])[:300],
                                         "to": info["there"]})
    if cfg["AURORA_UPDATE_MODE"] == "auto" and info["safe"]:
        from aurora import sys_autonomy
        sys_autonomy.log(cfg, "updates", f"update to {info['there']} ({info['behind']} commits) started by herself")
        return {**info, "run_id": _start_update(info["there"])}
    item = Approvals(cfg).request("update", "code_change", f"Aggiornamento: {info['behind']} commit fino a {info['there']}",
                                  text, {"commits": info["commits"], "files": info["files"], "protected": info["protected"]},
                                  {"to": info["there"]})
    return {**info, "approval": item["id"]}


def _env_add_missing() -> list[str]:
    """Keys a new schema declares and .env lacks get their recommended value (an update must not stop Aurora)."""
    added = sys_config.add_missing()
    if added:
        log.info("audit: update added settings with their recommended value: %s", ", ".join(added))
    return added


def _runs_here(unit: str) -> bool:
    """The unit runs this folder's code (its ExecStart names cfg.root): units of the same name may be another copy's."""
    try:
        out = subprocess.run(["systemctl", "show", unit, "-p", "ExecStart"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f"{cfg.root}/" in out


def _start_update(to: str) -> str:
    def job(q, emit, run_id):
        from aurora import sys_update
        from aurora.kno_answer import Answer
        out = sys_update.apply(cfg, emit)
        if out.get("applied"):
            out["settings_added"] = _env_add_missing()
            mine = [u for u in UNITS if _runs_here(u)]          # a second copy never restarts another's services (C140)
            out["restarted"] = mine
            if [u for u in mine if u != "aurora-api"]:
                threading.Timer(2.0, lambda: subprocess.run(["systemctl", "restart", "--no-block",
                                                             *[u for u in mine if u != "aurora-api"]], capture_output=True)).start()
            if "aurora-api" in mine:
                threading.Timer(4.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                            capture_output=True)).start()
        note("update", "update.done", {"ok": out.get("applied", False), "text": out.get("reason", f"aggiornata a {to}")})
        return Answer(run_id, q, json.dumps(out, ensure_ascii=False), False, mode="agent")
    return start_run(f"[update] {to}", origin="update", job=job)["id"]


def _harvest_domains() -> list[dict]:
    from aurora import kno_sources
    from aurora.sol_schema import load_taxonomy
    tax = load_taxonomy()
    return [{"id": d, "it": tax.get(d, {}).get("it", d), "en": tax.get(d, {}).get("en", d), "mode": m,
             **kno_sources.progress(cfg, d)} for d, m in kno_sources.modes(cfg).items()]


@router.put("/v1/aurora/harvester/domains", dependencies=[Depends(auth)])
async def harvester_domains(request: Request) -> dict:
    from aurora import kno_harvest, kno_sources
    changes = {str(k): str(v) for k, v in (await request.json()).items()}
    try:
        kno_sources.set_modes(cfg, changes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if any(v != "off" for v in changes.values()):
        kno_harvest.send(cfg, "wake")                   # the harvester re-reads the choice within seconds
    log.info("audit: harvester domains: %s", ", ".join(f"{k}={v}" for k, v in sorted(changes.items())))
    return {"domains": _harvest_domains()}


@router.get("/v1/aurora/harvester", dependencies=[Depends(auth)])
def harvester() -> dict:
    from aurora import kno_harvest
    env = sys_config.parse_env(sys_config.env_file_path().read_text(encoding="utf-8"))
    seen = cfg.path("AURORA_STATUS_DIR") / "harvest" / "seen.json"
    return {**kno_harvest.status(cfg), "pending": kno_harvest.pending(cfg),
            "enabled_setting": env.get("AURORA_HARVEST_ENABLED", "0").lower() in sys_config.TRUE_WORDS,
            "categories": cfg["AURORA_HARVEST_CATEGORIES"], "per_category": cfg["AURORA_HARVEST_PER_CATEGORY"],
            "interval_h": cfg["AURORA_HARVEST_INTERVAL_H"],
            "papers_seen": len(json.loads(seen.read_text())) if seen.exists() else 0,
            "domains": _harvest_domains()}


@router.post("/v1/aurora/harvester/{action}", dependencies=[Depends(auth)])
async def harvester_action(action: str, request: Request) -> dict:
    from aurora import kno_harvest
    if action == "now":
        item = kno_harvest.send(cfg, "now")
        log.info("audit: owner asked the harvester for a round now")
        return {"queued": item["id"]}
    if action == "batch":
        ids, unsupported = kno_harvest.parse_items(str((await request.json()).get("items", ""))[:50000])
        if not ids:
            raise HTTPException(status_code=422, detail={"message": "no arXiv id or link found", "unsupported": unsupported})
        item = kno_harvest.send(cfg, "batch", ids=ids)
        log.info("audit: owner sent the harvester a batch of %d papers", len(ids))
        return {"queued": item["id"], "ids": ids, "unsupported": unsupported}
    raise HTTPException(status_code=404, detail="unknown action")


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .agents import UNITS  # noqa: E402
