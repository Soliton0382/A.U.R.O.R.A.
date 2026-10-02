# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Firewall incidents from aurora-sentinel: stored, investigated, closed."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log, note, pipeline, plugin_host, start_run

router = APIRouter()


# ---- firewall incidents -------------------------------------------------------------------------
@router.post("/v1/aurora/sentinel/incident", dependencies=[Depends(auth)])
async def sentinel_incident(request: Request) -> dict:
    """aurora-sentinel reports an incident: kept, shown, investigated at once if the .env says so."""
    from aurora.sec_incidents import Incidents
    item = Incidents(cfg).add(await request.json())
    note("sentinel", "incident", {"id": item["id"], "kind": item["kind"], "source": item["source"],
                                  "severity": item["severity"], "title": f"{item['kind']} · {item['source']}"})
    if cfg["AURORA_SENTINEL_INVESTIGATE"]:
        def job(q, emit, run_id):
            from aurora.kno_answer import Answer
            from aurora.sec_incidents import investigate
            text = investigate(pipeline(), plugin_host(), item, emit, cfg)
            return Answer(run_id, q, text, False, mode="agent")
        start_run(f"[incident] {item['kind']} {item['source']}", origin="sentinel", job=job)
    return {"id": item["id"], "severity": item["severity"]}


@router.get("/v1/aurora/incidents", dependencies=[Depends(auth)])
def incidents(status: str | None = None) -> list[dict]:
    from aurora.sec_incidents import Incidents
    return Incidents(cfg).list(status)[:200]


@router.post("/v1/aurora/incidents/{incident_id}/close", dependencies=[Depends(auth)])
def close_incident(incident_id: str) -> dict:
    from aurora.sec_incidents import Incidents
    try:
        Incidents(cfg).update(incident_id, status="closed", closed=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    except StopIteration:
        raise HTTPException(status_code=404, detail="unknown incident")
    log.info("audit: incident %s closed by the owner", incident_id)
    return {"id": incident_id, "status": "closed"}


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .system import status  # noqa: E402
