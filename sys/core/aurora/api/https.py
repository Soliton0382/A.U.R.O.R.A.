# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 HTTPS (net_https): the names Aurora answers to, the certificate in use, the owner's own certificate, the way back to
Caddy's local authority. The admin's only; nothing here needs sudo (aurora-https is reloaded through 50-aurora.rules)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import cfg, log
from .users import admin_only

router = APIRouter()


@router.get("/v1/aurora/https", dependencies=[Depends(admin_only)])
def https_status() -> dict:
    from aurora import net_https
    return net_https.status(cfg)


@router.put("/v1/aurora/https/cert", dependencies=[Depends(admin_only)])
async def https_cert(request: Request) -> dict:
    """{"cert": fullchain PEM text, "key": private key PEM text}: checked, then in use; refused with the reason."""
    from aurora import net_https
    body = await request.json()
    cert, key = str(body.get("cert") or ""), str(body.get("key") or "")
    if not cert.strip() or not key.strip() or len(cert) + len(key) > 200_000:
        raise HTTPException(status_code=422, detail="a certificate and its key, as PEM text")
    try:
        return await asyncio.to_thread(net_https.install_cert, cfg, cert.encode(), key.encode())
    except net_https.HttpsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.delete("/v1/aurora/https/cert", dependencies=[Depends(admin_only)])
async def https_internal() -> dict:
    from aurora import net_https
    try:
        return await asyncio.to_thread(net_https.use_internal, cfg)
    except net_https.HttpsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.put("/v1/aurora/https/names", dependencies=[Depends(admin_only)])
async def https_names(request: Request) -> dict:
    """{"aliases": ["192.168.1.20", "name.local"]}: the other names of this machine."""
    from aurora import net_https
    aliases = (await request.json()).get("aliases") or []
    if not isinstance(aliases, list) or len(aliases) > 10:
        raise HTTPException(status_code=422, detail="aliases: a list of up to 10 names")
    try:
        out = await asyncio.to_thread(net_https.set_aliases, cfg, [str(a) for a in aliases])
    except net_https.HttpsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: HTTPS names now %s", ", ".join(out["names"]))
    return out


@router.put("/v1/aurora/https/ports", dependencies=[Depends(admin_only)])
async def https_ports(request: Request) -> dict:
    """{"https": 8443, "http": 8080}: Aurora's ports; checked, then in use (the API restarts a moment after)."""
    from aurora import net_https
    body = await request.json()
    try:
        out = await asyncio.to_thread(net_https.set_ports, cfg, int(body.get("https", 0)), int(body.get("http", 0)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="https and http: port numbers") from None
    except net_https.HttpsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return out
