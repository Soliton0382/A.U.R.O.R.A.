# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Firewall incidents from aurora-sentinel: stored, investigated, closed."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log, note, pipeline, plugin_host, start_run

from .users import admin_only  # noqa: E402

router = APIRouter()


# ---- firewall incidents -------------------------------------------------------------------------
@router.post("/v1/aurora/sentinel/incident", dependencies=[Depends(auth)])
async def sentinel_incident(request: Request) -> dict:
    """aurora-sentinel reports an incident: kept, shown, investigated at once if the .env says so."""
    from aurora import sec_netmap
    from aurora.sec_incidents import Incidents
    incident = await request.json()
    name = sec_netmap.names(cfg).get(incident.get("source", "")) if incident.get("internal") else None
    if name:                                              # one of the owner's devices (the firewall knows its name)
        incident["known"] = name
    if not incident.get("internal"):                      # an address on a public list of attackers (sec_intel)
        from aurora import sec_intel
        hits = sec_intel.lookup(cfg, incident.get("source", ""))
        if hits:
            incident["intel_lists"] = hits
        provider = sec_intel.shared(cfg, incident.get("source", ""))
        if provider:                                      # a CDN's or a cloud's: blocking it cuts off sites (C190)
            incident["shared"] = provider
    item = Incidents(cfg).add(incident)
    if item.get("merged"):                                # a repeat of an open incident: counted, not said again
        return {"id": item["id"], "severity": item["severity"], "merged": True}
    from aurora import sec_defence
    if sec_defence.blocked(cfg, item["source"]):          # blocked already: the firewall drops it — kept, closed, not
        Incidents(cfg).update(item["id"], status="closed", closed=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                              defence="already blocked")  # said again (C174)
        return {"id": item["id"], "severity": item["severity"], "blocked": True}
    who = f"{name} ({item['source']})" if name else item["source"]
    if not (name and item["severity"] == "low"):          # a known device's routine traffic: in the list, no alert
        note("sentinel", "incident", {"id": item["id"], "kind": item["kind"], "source": item["source"],
                                      "severity": item["severity"], "title": f"{item['kind']} · {who}"})
    defend(item)
    if item["kind"] == "honeypot":                        # a decoy touched: off this machine at once (sec_hostfw)
        import threading

        def keep_out():
            from aurora import sec_hostfw
            r = sec_hostfw.block(cfg, item["source"], f"esca toccata (porta {item.get('detail', {}).get('port')})")
            Incidents(cfg).update(item["id"], hostfw="blocked" if r.get("ok") else f"not blocked: {r.get('why')}")
            if r.get("ok"):
                note("security", "hostfw.block", {"title": f"🧱 {item['source']} bloccato sul computer di Aurora", "text": "esca toccata"})
        threading.Thread(target=keep_out, name="hostfw", daemon=True).start()
    if cfg["AURORA_SENTINEL_INVESTIGATE"] and not name:   # the public registry says nothing about a device at home
        def job(q, emit, run_id):
            from aurora.kno_answer import Answer
            from aurora.sec_incidents import investigate
            text = investigate(pipeline(), plugin_host(), item, emit, cfg)
            return Answer(run_id, q, text, False, mode="agent")
        start_run(f"[incident] {item['kind']} {item['source']}", origin="sentinel", job=job)
    return {"id": item["id"], "severity": item["severity"]}


def defend(item: dict) -> None:
    """Autonomous defence (sec_defence): the source blocked now when every limit allows it, told either way."""
    import threading
    from aurora import sec_defence, sec_fwapi
    from aurora.sec_incidents import Incidents
    ok, why = sec_defence.decide(cfg, item)
    if not ok:
        if why != "mode":
            Incidents(cfg).update(item["id"], defence=why)
        return

    def run():
        try:
            out = sec_defence.act(cfg, item)
            Incidents(cfg).update(item["id"], defence="blocked", blocked_until=out["until"])
            note("security", "defence.block", {"title": f"🛡️ {item['source']} bloccato da Aurora",
                                               "text": f"{item['kind']} · {item['severity']} · {cfg['AURORA_DEFENCE_HOURS']} h"})
        except sec_fwapi.FirewallAPIError as e:
            Incidents(cfg).update(item["id"], defence=f"failed: {e}")
            note("security", "defence.failed", {"title": f"⚠️ {item['source']} non bloccato", "text": str(e)[:180]})
    threading.Thread(target=run, name="defence", daemon=True).start()


@router.get("/v1/aurora/incidents", dependencies=[Depends(admin_only)])
def incidents(status: str | None = None, archived: bool = False) -> list[dict]:
    from aurora.sec_incidents import Incidents
    return Incidents(cfg).list(status, archived)[:200]


@router.post("/v1/aurora/incidents/archive-closed", dependencies=[Depends(admin_only)])
def incidents_archive_closed() -> dict:
    """The owner tidies the Security page: closed incidents archived (kept for the reports)."""
    from aurora.sec_incidents import Incidents
    n = Incidents(cfg).archive_closed()
    log.info("audit: owner archived %d closed incidents", n)
    return {"archived": n}


@router.post("/v1/aurora/incidents/{incident_id}/close", dependencies=[Depends(admin_only)])
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
