# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Knowledge and memory: import, solitons, sources, domains, the history, senses, features (uploads, updates and the
harvester in their own modules since ROADMAP D10)."""
from __future__ import annotations

import asyncio
import base64
import binascii
import os
import time

from aurora import sys_features
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import _run_lock, _state, _write_lock, auth, cfg, log, pipeline

from .users import admin_only  # noqa: E402

router = APIRouter()


# ---- knowledge import -------------------------------------------------------------------------
@router.get("/v1/aurora/domains", dependencies=[Depends(auth)])
def domains() -> list[dict]:
    from aurora.sol_schema import load_taxonomy
    return [d for d in load_taxonomy().values() if not d.get("memory")]


def _import(name: str, data: bytes, domain: str, title: str, origin: str = "upload", meta: dict | None = None) -> dict:
    from aurora.kno_ingest import Importer
    from aurora import sec_detonate, sec_filecheck
    if origin in sec_detonate.OWNER_ORIGINS:          # a person's file: its reputation by its hash (and the decoy, in add)
        sec_filecheck.gate(cfg, name, data)
    p = pipeline()
    with _write_lock:                                 # one import at a time; the answers go on (C219)
        rep = Importer(p.writer, p.indexer, cfg, llm=p.llm, decoy=p.llm).add(name, data, domain, title,
                                                                                     origin=origin, meta=meta)
    return {"name": rep.name, "source_id": rep.source_id, "domain": rep.domain, "chunks": rep.chunks,
            "written": rep.written, "duplicates": rep.duplicates, "rejected": rep.rejected, "indexed": rep.indexed}


@router.post("/v1/aurora/import", dependencies=[Depends(admin_only)])
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
                                       {"licence": body.get("licence", ""), "url": body.get("url", ""),
                                        # a deliberate replacement (the vault's realignment: the HTML of a paper that
                                        # came as PDF): written although the same identity is there, removed after
                                        **({"replace": "yes"} if body.get("replace") is True else {})})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _add_solitons(items: list[dict]) -> dict:
    from aurora import kno_dedup
    from aurora.sol_schema import Soliton
    p = pipeline()
    # one document, one copy (C293): a document whose first passage comes with an official identity already in the
    # vault is not written again — its later batches (no first passage) go on as they come
    skip = {}
    for x in items:
        if int(x.get("chunk_index", 0)) == 0 and x["source_id"] not in skip:
            hit = kno_dedup.known(cfg, p.reader, str((x.get("extra") or {}).get("origin") or x["source_id"]))
            if hit:
                skip[x["source_id"]] = f"{hit[0]}/{hit[1]}"
    received = len(items)
    items = [x for x in items if x["source_id"] not in skip]
    poisoned = {}                                     # passages from the network (the harvester's: a url) tried on a
    from aurora import sec_detonate                   # decoy first, per document (sec_detonate, ROADMAP 104)
    for sid in sorted({x["source_id"] for x in items if (x.get("extra") or {}).get("url")}):
        group = [x for x in items if x["source_id"] == sid]
        extra = group[0].get("extra") or {}
        try:
            sec_detonate.import_gate(cfg, p.llm, str(extra.get("origin") or sid), str(extra["url"]),
                                     "\n\n".join(x["text"] for x in group))
        except ValueError as e:
            poisoned[sid] = str(e)
    items = [x for x in items if x["source_id"] not in poisoned]
    sols = [Soliton.new(x["text"], x["domain"], "knowledge", x.get("lang") or "en", x["source_id"], x.get("title", ""),
                        chunk_index=int(x.get("chunk_index", 0)), chunk_count=int(x.get("chunk_count", 1)),
                        extra=x.get("extra") or {}) for x in items]
    with _write_lock:                                 # one import at a time; the answers go on (C219)
        rep = p.writer.add_many(sols)
        indexed = {d: p.indexer.update(d) for d in sorted({s.domain for s in sols})} if rep.written else {}
    for x in items:                                   # the identities written now: known to the next import
        if int(x.get("chunk_index", 0)) == 0:
            kno_dedup.remember(cfg, x.get("title", ""), x["domain"], x["source_id"], x.get("lang") or "en", x["text"],
                               str((x.get("extra") or {}).get("origin") or x["source_id"]))
    return {"received": received, "written": len(rep.written), "duplicates": len(rep.duplicates),
            "rejected": rep.rejected, "indexed": indexed, "copies_of": skip, "poisoned": poisoned}


@router.post("/v1/aurora/solitons", dependencies=[Depends(admin_only)])
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


@router.delete("/v1/aurora/sources", dependencies=[Depends(admin_only)])
async def remove_source(domain: str, source_id: str) -> dict:
    from aurora.sol_schema import load_taxonomy
    if domain not in load_taxonomy():
        raise HTTPException(status_code=422, detail=f"unknown domain {domain!r}")

    def work():
        p = pipeline()
        with _run_lock:
            sids = p.writer.remove_source(domain, source_id)
            from aurora import kno_synapse
            return {"domain": domain, "source_id": source_id, "removed": len(sids),
                    "index_rows_removed": p.indexer.drop(domain, sids),
                    "links_removed": kno_synapse.forget(cfg, sids)}      # no synapse left pointing to nothing
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
             "reply_to": t.extra.get("reply_to"),
             "long_term": t.consolidated} for t in turns]
    from aurora import sys_uploads
    files = sys_uploads.by_run(cfg, {i["run_id"] for i in items if i["run_id"]})
    for i in items:                                   # the owner's files with his turn, Aurora's (edits) with hers
        i["attachments"] = [f for f in files.get(i["run_id"], []) if f["role"] == ("user" if i["role"] == "user" else "assistant")]
    return sorted(items + recent_dreams(), key=lambda x: x["created_at"])          # same UTC ISO format


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
             "image_prompt": d.extra.get("image_prompt", "")} for d in dreams[-2:]] + [
        {"sid": m.sid, "role": "morning", "text": m.text, "created_at": m.created_at}       # today's good morning
        for m in [d for d in pipeline().reader.recent(100, domain="reflection")
                  if d.extra.get("type") == "morning" and datetime.fromisoformat(d.created_at) >= since][-1:]] + [
        {"sid": r.sid, "role": "review", "text": r.text, "created_at": r.created_at}        # second thoughts (kno_review)
        for r in pipeline().reader.recent(100, domain="reflection")
        if r.extra.get("type") == "review" and datetime.fromisoformat(r.created_at) >= since]


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
            if out.get("clear") and out.get("text"):      # her memory searched while the person still speaks, and with
                pipeline().ahead(out["text"])            # the final words before they come back as the question (sol_ahead)
            if not body.get("partial"):                  # the words so far while speaking (ROADMAP 99): not a dictation
                log.info("audit: owner dictated %.1f s from a device (%s, %d bytes; clear: %s)", out["audio_s"],
                         str(body.get("mime", "?"))[:40], len(data), out["clear"])
            return out
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    raise HTTPException(status_code=404, detail="unknown action")


@router.get("/v1/aurora/features", dependencies=[Depends(auth)])
def features() -> dict:
    """What this installation can do, what is missing for the rest (and how to add it), contradicting settings."""
    from aurora import sys_capabilities
    from .core import plugin_host
    return {"features": sys_features.report(cfg), "config": sys_features.config_problems(cfg),
            "live": sys_capabilities.report(cfg, plugin_host())}
