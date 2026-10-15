# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛡️ Security → Firewall: the house's firewalls set, connected and checked in the page (sec_firewalls); the admin's."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import cfg, log
from .users import admin_only

router = APIRouter()


@router.get("/v1/aurora/security/firewalls", dependencies=[Depends(admin_only)])
def firewalls() -> dict:
    from aurora import sec_firewalls, sec_fwdocs
    out = []
    for it in sec_firewalls.items(cfg):
        v = sec_firewalls.view(cfg, it)
        out.append({**it, "guides": {s: sec_fwdocs.url(v, s) for s in ("manual", "api", "syslog")},
                    "indexed": sec_fwdocs.stats(v)})
    return {"items": out, "kinds": sec_firewalls.kinds(), "receivers": [x["id"] for x in sec_firewalls.receivers(cfg)]}


@router.put("/v1/aurora/security/firewalls/{fid}", dependencies=[Depends(admin_only)])
async def firewall_save(fid: str, request: Request) -> dict:
    """The form's fields; "password" only when typed (never sent back)."""
    from aurora import sec_firewalls
    body = await request.json()
    try:
        out = sec_firewalls.save(cfg, fid, body, str(body.get("password") or "") or None)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such firewall") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: firewall %s saved by the admin", out["id"])
    return out


@router.delete("/v1/aurora/security/firewalls/{fid}", dependencies=[Depends(admin_only)])
def firewall_remove(fid: str) -> dict:
    from aurora import sec_firewalls
    try:
        sec_firewalls.remove(cfg, fid)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: firewall %s removed by the admin", fid)
    return {"removed": fid}


@router.post("/v1/aurora/security/firewalls/{fid}/connect", dependencies=[Depends(admin_only)])
async def firewall_connect(fid: str) -> dict:
    """Log in, the blocking group, the guides indexed in the background: confirmed only if it worked."""
    from aurora import sec_firewalls
    try:
        return await asyncio.to_thread(sec_firewalls.connect, cfg, fid)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such firewall") from None
