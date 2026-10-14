# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The harvester's side of the API: its domains, its state, its actions (split from api/knowledge (ROADMAP D10): no
monoliths)."""
from __future__ import annotations

import json

from aurora import sys_config
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log

from .users import admin_only  # noqa: E402

router = APIRouter()

def _harvest_domains() -> list[dict]:
    from aurora import kno_sources
    from aurora.sol_schema import load_taxonomy
    tax = load_taxonomy()
    return [{"id": d, "it": tax.get(d, {}).get("it", d), "en": tax.get(d, {}).get("en", d), "mode": m,
             **kno_sources.progress(cfg, d)} for d, m in kno_sources.modes(cfg).items()]


@router.put("/v1/aurora/harvester/domains", dependencies=[Depends(admin_only)])
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


@router.post("/v1/aurora/harvester/{action}", dependencies=[Depends(admin_only)])
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
    if action == "plan":                                # the projection again now (kno_harvest_plan)
        item = kno_harvest.send(cfg, "plan")
        log.info("audit: owner asked the harvester's projection now")
        return {"queued": item["id"]}
    raise HTTPException(status_code=404, detail="unknown action")
