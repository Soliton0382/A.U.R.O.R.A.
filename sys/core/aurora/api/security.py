# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Security, configurable (owner, 2026-10-04): what the firewall sends, the checks Aurora proposes from its
documentation (switched on by the owner), and the defence on the firewall through its API — on the owner's click."""
from __future__ import annotations

import asyncio
import time

from aurora import sys_log
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import cfg, log, note, pipeline
from .users import admin_only

router = APIRouter()


_traffic: dict = {"at": 0.0, "hours": 0.0, "groups": []}


@router.get("/v1/aurora/security/profile", dependencies=[Depends(admin_only)])
def profile(hours: float = 24, traffic: bool = True) -> dict:
    """The checks, and (traffic=1) the last hours' traffic in groups — 4.5 s to read, so asked apart and kept 5 min."""
    from aurora import sec_profile, sec_rules, sec_fwapi
    groups = []
    if traffic:
        h = max(1.0, min(hours, 168.0))
        if time.time() - _traffic["at"] > 300 or _traffic["hours"] != h:
            _traffic.update(at=time.time(), hours=h, groups=sec_profile.observe(cfg, h))
        groups = _traffic["groups"]
    return {"groups": groups, "rules": sec_rules.load(cfg),
            "doc": cfg["AURORA_SECURITY_SYSLOG_DOC"], "firewall_api": sec_fwapi.configured(cfg), "group": cfg["AURORA_FIREWALL_BLOCK_GROUP"]}


@router.post("/v1/aurora/security/learn", dependencies=[Depends(admin_only)])
async def learn() -> dict:
    """Read the documentation and the last day's traffic; propose checks (off until the owner turns them on)."""
    from aurora import sec_profile
    try:
        out = await asyncio.to_thread(sec_profile.learn, cfg, pipeline()._for("agent"))
    except Exception as e:  # noqa: BLE001 — the documentation unreachable, the model failing: said in the page
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {str(e)[:300]}") from None
    log.info("audit: security checks proposed: %d (%d groups, %d lines)", out["proposed"], out["groups"], out["lines"])
    return out


@router.put("/v1/aurora/security/rules", dependencies=[Depends(admin_only)])
async def rules_set(request: Request) -> dict:
    """{"on": {id: true/false}} switches checks; {"remove": [ids]} drops proposals. aurora-sentinel follows in 1 min."""
    from aurora import sec_rules
    body = await request.json()
    on, gone = body.get("on") or {}, set(body.get("remove") or [])
    rules = [{**r, "on": bool(on.get(r["id"], r["on"]))} for r in sec_rules.load(cfg) if r["id"] not in gone]
    rules = sec_rules.save(cfg, rules)
    log.info("audit: security checks on: %s", ", ".join(r["id"] for r in rules if r["on"]) or "-")
    return {"rules": rules}


@router.get("/v1/aurora/security/netmap", dependencies=[Depends(admin_only)])
def netmap() -> dict:
    """The network seen from the firewall (sec_netmap): counts, what the last look changed, address -> name."""
    from aurora import sec_fwapi, sec_netmap
    try:
        m = sec_netmap.load(cfg)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    return {**sec_netmap.summary(m), "changes": (m or {}).get("changes"), "names": sec_netmap.names(cfg),
            "configured": sec_fwapi.configured(cfg)}


@router.post("/v1/aurora/security/netmap/refresh", dependencies=[Depends(admin_only)])
async def netmap_refresh() -> dict:
    from aurora import sec_fwapi, sec_netmap
    try:
        r = await asyncio.to_thread(sec_netmap.refresh, cfg)
    except sec_fwapi.FirewallAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    log.info("audit: network map refreshed (%d hosts, %d new, %d gone)", r["hosts"], len(r["changes"]["new"]),
             len(r["changes"]["gone"]))
    return r


@router.get("/v1/aurora/security/netmap/graph", dependencies=[Depends(admin_only)])
def netmap_graph() -> dict:
    from aurora import sec_netmap
    return sec_netmap.graph(sec_netmap.load(cfg))


@router.get("/v1/aurora/security/netmap/find", dependencies=[Depends(admin_only)])
def netmap_find(q: str) -> dict:
    from aurora import sec_netmap
    m = sec_netmap.load(cfg)
    return {"lines": sec_netmap.find(m, q) if m and q.strip() else []}


@router.post("/v1/aurora/security/firewall/test", dependencies=[Depends(admin_only)])
async def firewall_test() -> dict:
    from aurora import sec_fwapi
    try:
        return await asyncio.to_thread(sec_fwapi.test, cfg)
    except sec_fwapi.FirewallAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None


@router.get("/v1/aurora/security/outbound", dependencies=[Depends(admin_only)])
async def outbound(days: float = 1) -> dict:
    """What left this machine in the last days: cloud calls and what was masked, posts, pushes, firewall actions."""
    from aurora import sec_outbound
    from aurora.sys_approvals import Approvals, auto_tools
    return await asyncio.to_thread(sec_outbound.summary, cfg, Approvals(cfg)._load(), auto_tools(cfg), max(1.0, min(days, 30)))


@router.get("/v1/aurora/security/defence", dependencies=[Depends(admin_only)])
def defence_state() -> dict:
    from aurora import sec_defence
    return sec_defence.summary(cfg)


@router.post("/v1/aurora/security/defence/release", dependencies=[Depends(admin_only)])
async def defence_release(request: Request) -> dict:
    """{"ip"}: the owner lifts an automatic block before its time."""
    from aurora import sec_defence, sec_fwapi
    ip = str((await request.json()).get("ip", ""))
    try:
        out = await asyncio.to_thread(sec_defence.release, cfg, ip, "owner")
    except sec_fwapi.FirewallAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    log.info("audit: owner lifted Aurora's block of %s", ip)
    return out


def watch_defence() -> None:
    """Every 5 minutes: the automatic blocks whose time is over are lifted (a thread of the API)."""
    import time as _t
    from aurora import sec_defence
    while True:
        _t.sleep(300)
        try:
            for ip in sec_defence.release_due(cfg):
                note("security", "defence.release", {"title": f"🛡️ {ip}: blocco scaduto, tolto", "text": ""})
        except Exception as e:                        # noqa: BLE001 — a bad round never stops the next
            log.warning("defence: release round failed: %s", e)


@router.post("/v1/aurora/security/block", dependencies=[Depends(admin_only)])
async def firewall_block(request: Request) -> dict:
    """{"ip", "reason", "unblock": bool}: the owner's click on an incident is the consent; recorded and told."""
    from aurora import sec_fwapi
    body = await request.json()
    ip, reason = str(body.get("ip", "")), str(body.get("reason", ""))[:200]
    try:
        out = await asyncio.to_thread(sec_fwapi.unblock if body.get("unblock") else sec_fwapi.block, cfg, ip,
                                      *(() if body.get("unblock") else (reason,)))
    except sec_fwapi.FirewallAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    what = "unblocked" if body.get("unblock") else "blocked"
    from aurora import sec_defence                     # kept, so that "undo" finds it (owner, 2026-10-05)
    if body.get("unblock"):
        sec_defence.mark_released(cfg, out["unblocked"], "owner")
    else:
        sec_defence.record_manual(cfg, out["blocked"], reason)
    log.info("audit: owner %s %s on the firewall (%s)", what, ip, reason or "-")
    sys_log.trace("security", f"firewall.{what}", {"ip": ip, "reason": reason})
    note("security", "security.action", {"title": f"🛡️ {ip} {'sbloccato' if what == 'unblocked' else 'bloccato'} sul firewall",
                                  "text": reason})
    return out
