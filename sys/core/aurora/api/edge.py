# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""☁️ Cloudflare in the Security area (owner, 16 Oct: «lo metterei direttamente come una pagina in sicurezza dove
possiamo anche decidere cosa può fare in autonomia Aurora… cosa ha bloccato, rimozioni»): the tunnel's state, who hit
the origin through Cloudflare (net_cfwaf.culprits, with Aurora's guess), the blocks — Aurora's own and the owner's,
active and lifted — and the owner's block and unblock (the click is the consent). The autonomy of these blocks is the
«edge» area of 🤖 Autonomy (AURORA_CLOUDFLARE_AUTOBLOCK). The admin's."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import cfg, log, note
from .users import admin_only

router = APIRouter()


@router.get("/v1/aurora/security/edge", dependencies=[Depends(admin_only)])
async def edge() -> dict:
    from aurora import net_cfwaf, net_cloudflare, sys_ethics

    def work():
        items = net_cfwaf._load(cfg)
        try:
            state = net_cloudflare.status(cfg)
        except Exception as e:                           # noqa: BLE001 — the page shows what it could read
            state = f"⚠️ {e}"
        return {"tunnel": state, "active": net_cfwaf.active(cfg), "history": items[-60:][::-1],
                "autoblock": bool(cfg["AURORA_CLOUDFLARE_AUTOBLOCK"]), "exempt": sys_ethics.exempt(cfg)}
    return await asyncio.to_thread(work)


@router.get("/v1/aurora/security/edge/culprits", dependencies=[Depends(admin_only)])
async def edge_culprits(hours: float = 24) -> dict:
    """Who the origin refused through Cloudflare in the last hours, with Aurora's guess (never a verdict)."""
    from aurora import net_cfwaf

    try:                                                  # each row with Aurora's guess («looks»), ≤ 24 hours
        return {"culprits": await asyncio.to_thread(net_cfwaf.culprits, cfg, max(1.0, min(hours, 24)))}
    except net_cfwaf.CloudflareError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None


@router.post("/v1/aurora/security/edge/block", dependencies=[Depends(admin_only)])
async def edge_block(request: Request) -> dict:
    """{"ip", "reason", "hours"}: the owner's click on a culprit."""
    from aurora import net_cfwaf
    b = await request.json()
    try:
        rec = await asyncio.to_thread(net_cfwaf.block, cfg, str(b.get("ip", "")), str(b.get("reason") or "blocked by the owner"),
                                      float(b.get("hours") or 24))
    except (net_cfwaf.CloudflareError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: owner blocked %s on Cloudflare", rec["ip"])
    note("security", "security.action", {"title": f"☁️ {rec['ip']} bloccato su Cloudflare", "text": rec["reason"]})
    return rec


@router.post("/v1/aurora/security/edge/unblock", dependencies=[Depends(admin_only)])
async def edge_unblock(request: Request) -> dict:
    """{"ip"}: a block lifted now, Aurora's own or the owner's."""
    from aurora import net_cfwaf
    b = await request.json()
    try:
        rec = await asyncio.to_thread(net_cfwaf.unblock, cfg, str(b.get("ip", "")), "owner")
    except net_cfwaf.CloudflareError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: owner lifted the Cloudflare block of %s", rec["ip"])
    note("security", "security.action", {"title": f"☁️ {rec['ip']} sbloccato su Cloudflare", "text": ""})
    return rec
