# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 The VPN of Aurora's own internet (net_vpn; the tunnel is aurora-vpn's, svc_vpn.py): the profiles imported (.ovpn),
the account, the default ticked, on and off, the unprotected line asked for while every profile fails, the address
the internet sees. The admin's: it is the machine's traffic."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import BASE, cfg, in_thread, log, note
from .users import admin_only

router = APIRouter()
MAX_BODY = 80 * 1024


def _base():
    return BASE.base or BASE


def _view() -> dict:
    from aurora import net_vpn as V
    p = V.prefs(_base())
    return {"prefs": {k: p[k] for k in ("on", "default", "last", "unprotected", "account", "through", "split",
                                        *V.OPTIONS)},
            "recommended": {"through": list(V.RECOMMENDED), **V.OPTIONS, "split": V.suggested_split(_base())},
            "suggested_split": [d for d in V.suggested_split(_base()) if d not in p["split"]],
            "profiles": p["profiles"], "state": V.state(_base()),
            "choices": [{"id": u, **lab, "recommended": u in V.RECOMMENDED} for u, lab in V.CHOICES.items()]}


@router.get("/v1/aurora/vpn", dependencies=[Depends(admin_only)])
def vpn() -> dict:
    return _view()


@router.post("/v1/aurora/vpn/profiles", dependencies=[Depends(admin_only)])
async def vpn_import(request: Request) -> dict:
    """{"name", "text"}: an .ovpn imported (adapted: what was dropped is said)."""
    from aurora import net_vpn as V
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(status_code=413, detail="an .ovpn of at most 64 kB")
    b = await request.json()
    try:
        it = V.add(_base(), str(b.get("name", "")), str(b.get("text", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: VPN profile %s imported (%d lines dropped)", it["id"], len(it["dropped"]))
    return {"profile": it, **_view()}


@router.delete("/v1/aurora/vpn/profiles/{pid}", dependencies=[Depends(admin_only)])
def vpn_remove(pid: str) -> dict:
    from aurora import net_vpn as V
    try:
        V.remove(_base(), pid)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such profile") from None
    return _view()


@router.post("/v1/aurora/vpn/default", dependencies=[Depends(admin_only)])
async def vpn_default(request: Request) -> dict:
    from aurora import net_vpn as V
    try:
        V.set_default(_base(), str((await request.json()).get("id", "")))
    except KeyError:
        raise HTTPException(status_code=404, detail="no such profile") from None
    return _view()


@router.post("/v1/aurora/vpn/account", dependencies=[Depends(admin_only)])
async def vpn_account(request: Request) -> dict:
    """{"user", "password"}: the provider's manual-configuration pair, sealed; never shown again."""
    from aurora import net_vpn as V
    b = await request.json()
    try:
        V.set_account(_base(), b.get("user", ""), b.get("password", ""))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: VPN account set")
    return _view()


@router.post("/v1/aurora/vpn/want", dependencies=[Depends(admin_only)])
async def vpn_want(request: Request) -> dict:
    """{"on"?: bool, "unprotected"?: bool, "use"?: profile}: the unit follows within seconds."""
    from aurora import net_vpn as V
    b = await request.json()
    try:
        V.want(_base(), **{k: b[k] for k in ("on", "unprotected", "use") if k in b})
    except KeyError:
        raise HTTPException(status_code=404, detail="no such profile") from None
    log.info("audit: VPN wanted %s", {k: b[k] for k in ("on", "unprotected", "use") if k in b})
    return _view()


@router.post("/v1/aurora/vpn/through", dependencies=[Depends(admin_only)])
async def vpn_through(request: Request) -> dict:
    """{"units": [...]}: the services whose traffic passes through the tunnel (net_vpn.CHOICES)."""
    from aurora import net_vpn as V
    try:
        V.set_through(_base(), list((await request.json()).get("units") or []))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return _view()


@router.post("/v1/aurora/vpn/split", dependencies=[Depends(admin_only)])
async def vpn_split(request: Request) -> dict:
    """{"domains": [...]}: the domains kept on the normal network (the home's DNS, the normal line)."""
    from aurora import net_vpn as V
    try:
        V.set_split(_base(), list((await request.json()).get("domains") or []))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return _view()


@router.post("/v1/aurora/vpn/options", dependencies=[Depends(admin_only)])
async def vpn_options(request: Request) -> dict:
    """{"killswitch"?, "failover"?, "dns"?, "dns_servers"?}."""
    from aurora import net_vpn as V
    b = await request.json()
    try:
        V.set_options(_base(), **{k: b[k] for k in V.OPTIONS if k in b})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: VPN options %s", {k: b[k] for k in V.OPTIONS if k in b})
    return _view()


@router.post("/v1/aurora/vpn/recommended", dependencies=[Depends(admin_only)])
def vpn_recommended() -> dict:
    from aurora import net_vpn as V
    V.recommended(_base())
    return _view()


@router.get("/v1/aurora/vpn/ip", dependencies=[Depends(admin_only)])
async def vpn_ip() -> dict:
    """The address the internet sees for Aurora now (asked from this process: Aurora's own traffic)."""
    import httpx

    def ask():
        r = httpx.get("https://api.ipify.org?format=json", timeout=10)
        return r.raise_for_status().json().get("ip", "")
    try:
        return {"ip": await in_thread(ask)}
    except Exception as e:  # noqa: BLE001 — no internet (the kill switch, or the line): said
        return {"ip": None, "error": type(e).__name__}


def notice() -> None:
    """aurora-rem's tick: every profile failed → the owner asked once whether to use the unprotected line; back up
    after that → told once."""
    from aurora import net_vpn as V
    base = _base()
    s, f = V.state(base), V.folder(base) / "told.json"
    told = V._read(f, {})
    if s.get("phase") == "failed" and not told.get("failed"):
        note("vpn", "vpn.failed", {"text": "La VPN non si connette con nessun profilo: Aurora è senza internet per non uscire "
                                           "dalla linea normale. Vuoi usare la linea non protetta finché la VPN non torna? "
                                           "🛡️ Sicurezza → VPN"})
        V._write(f, {"failed": True})
    elif s.get("phase") == "up" and told.get("failed"):
        note("vpn", "vpn.back", {"text": "La VPN è tornata: il traffico di Aurora passa di nuovo dal tunnel."})
        V._write(f, {})
