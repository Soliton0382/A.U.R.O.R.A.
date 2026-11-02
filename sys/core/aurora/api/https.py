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


# ---- 🔏 the certificate looked after by Aurora (net_certs): the admin's only -------------------------------------
@router.get("/v1/aurora/https/acme", dependencies=[Depends(admin_only)])
def https_acme() -> dict:
    from aurora import net_certs
    return net_certs.status(cfg)


@router.post("/v1/aurora/https/acme/renew", dependencies=[Depends(admin_only)])
async def https_acme_renew(force: bool = False) -> dict:
    """A new certificate now (`force`, the page's button) or only when due (aurora-rem's daily look); the copy for the
    other devices either way."""
    from aurora import net_certs, net_https
    if not net_https.fresh(cfg)["AURORA_ACME_ENABLED"] and not force:   # the settings as saved now, not at start
        return {"renewed": False, "why": None, "copied": await asyncio.to_thread(net_certs.copy, cfg), "off": True}
    try:
        out = await asyncio.to_thread(net_certs.renew, cfg, force)
    except net_certs.CertError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if out.get("waiting") and not force:                 # by hand: the admin told what to add, once a day at most
        from .core import note
        note("https", "certificate.dns", {"title": f"🔏 Certificato da rinnovare ({out['why']}): aggiungi "
                                                   f"{len(out['waiting']['records'])} record TXT e verifica in 🔒 HTTPS"})
    return out


@router.post("/v1/aurora/https/acme/start", dependencies=[Depends(admin_only)])
async def https_acme_start() -> dict:
    """The guided way, step one: an order for the names saved, its TXT records written or to add by hand."""
    from aurora import net_certs
    try:
        return await asyncio.to_thread(net_certs.start, cfg)
    except net_certs.CertError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.get("/v1/aurora/https/acme/check", dependencies=[Depends(admin_only)])
async def https_acme_check() -> dict:
    """Step two: each record as the Internet sees it now."""
    from aurora import net_certs
    out = await asyncio.to_thread(net_certs.check, cfg)
    if out is None:
        raise HTTPException(status_code=404, detail="no certificate being asked")
    return out


@router.post("/v1/aurora/https/acme/verify", dependencies=[Depends(admin_only)])
async def https_acme_verify() -> dict:
    """Step three: the authority looks; the certificate in use and copied."""
    from aurora import net_certs
    try:
        return await asyncio.to_thread(net_certs.verify, cfg)
    except net_certs.CertError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.delete("/v1/aurora/https/acme/order", dependencies=[Depends(admin_only)])
async def https_acme_cancel() -> dict:
    from aurora import net_certs
    await asyncio.to_thread(net_certs.cancel, cfg)
    return {"cancelled": True}


@router.post("/v1/aurora/https/acme/copy", dependencies=[Depends(admin_only)])
async def https_acme_copy(scheduled: bool = False) -> dict:
    """The copy now (the page's button), or `scheduled` (svc_rem, each hour): only inside AURORA_CERTS_COPY_WINDOW."""
    from aurora import net_certs
    if scheduled:
        return await asyncio.to_thread(net_certs.copy_when, cfg, None, True)
    out = await asyncio.to_thread(net_certs.copy, cfg)
    if out is None:
        raise HTTPException(status_code=422, detail="no folder to copy to (AURORA_CERTS_COPY_DIR)")
    return out
