# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A local reasoner of one's own (roadmap 73, mdl_custom): a Hugging Face repository looked at, a file checked before
it is downloaded, downloaded with its SHA-256, tried, used — and the model before always one click away."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import cfg, log, start_run
from .users import admin_only

router = APIRouter()


def _err(e: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(e))


@router.get("/v1/aurora/models/custom", dependencies=[Depends(admin_only)])
def custom_state() -> dict:
    from aurora import mdl_custom
    return mdl_custom.installed(cfg)


@router.get("/v1/aurora/models/custom/inspect", dependencies=[Depends(admin_only)])
async def custom_inspect(repo: str) -> dict:
    from aurora import mdl_custom
    try:
        return await asyncio.to_thread(mdl_custom.inspect, repo.strip())
    except mdl_custom.CustomError as e:
        raise _err(e) from None


@router.get("/v1/aurora/models/custom/check", dependencies=[Depends(admin_only)])
async def custom_check(repo: str, revision: str, file: str, size_gb: float) -> dict:
    from aurora import mdl_custom
    try:
        return await asyncio.to_thread(mdl_custom.check, repo, revision, file, size_gb)
    except mdl_custom.CustomError as e:
        raise _err(e) from None


@router.post("/v1/aurora/models/custom/download", dependencies=[Depends(admin_only)])
async def custom_download(request: Request) -> dict:
    """{"repo", "revision", "files": [...]} downloaded in the background: a run, its events the progress."""
    body = await request.json()
    repo, revision, files = str(body.get("repo", "")), str(body.get("revision", "")), list(body.get("files") or [])
    if not repo or not revision or not files:
        raise HTTPException(status_code=422, detail="repo, revision and files are needed")

    def job(q, emit, run_id):
        from aurora import mdl_custom
        from aurora.kno_answer import Answer
        try:
            out = {"ok": True, "paths": mdl_custom.download(cfg, repo, revision, files, emit)}
        except Exception as e:                          # noqa: BLE001 - said in the run, never a crash
            out = {"ok": False, "error": str(e)[:300]}
        log.info("audit: custom model download %s@%s %s: %s", repo, revision[:12], files, "ok" if out["ok"] else out["error"])
        return Answer(run_id, q, json.dumps(out, ensure_ascii=False), False, mode="agent")
    return {"run_id": start_run(f"[model] {repo}", origin="models", job=job)["id"]}


@router.post("/v1/aurora/models/custom/switch", dependencies=[Depends(admin_only)])
async def custom_switch(request: Request) -> dict:
    """{"model", "mmproj"}: aurora-llm on that model, one trial question; undone at once if it does not answer."""
    from aurora import mdl_custom
    body = await request.json()
    try:
        out = await asyncio.to_thread(mdl_custom.switch, cfg, str(body.get("model", "")), str(body.get("mmproj") or ""))
    except mdl_custom.CustomError as e:
        raise _err(e) from None
    log.info("audit: local reasoner now %s (trial answer in %s s)", out["model"], out["seconds"])
    return out


@router.post("/v1/aurora/models/custom/revert", dependencies=[Depends(admin_only)])
async def custom_revert() -> dict:
    from aurora import mdl_custom
    try:
        out = await asyncio.to_thread(mdl_custom.revert, cfg)
    except mdl_custom.CustomError as e:
        raise _err(e) from None
    log.info("audit: local reasoner back to %s", out["model"])
    return out
