# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The pages 🧭 CISO and 🧱 Firewall of the security area (owner, 2026-10-08: «espanderei il menù security con sotto
menù specifici CISO, etc… così teniamo le cose separate e pulite»). The admin's only.

CISO: the posture (risks, suspects with their playbook) and the threat hunt. Firewall: the audit, Aurora's changes
(planned → the owner's click on «Applica» is the approval, like ⛔ on an incident; undone with «Annulla»), the
documentation searched. The readings of the firewall are slow (11 s the audit, 4 s the hunt): kept two minutes.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import cfg, log
from .users import admin_only

router = APIRouter()
_kept: dict = {}


def _cached(key: str, make, seconds: float = 120, again: bool = False):
    hit = _kept.get(key)
    if hit and not again and time.time() - hit[0] < seconds:
        return hit[1]
    value = make()
    _kept[key] = (time.time(), value)
    return value


def _audit(again: bool = False, fw: str = "main") -> dict:
    """One firewall's audit (any dialect, sec_fwmodel); «main» the settings' one, as before."""
    from aurora import sec_audit, sec_firewalls, sec_fwapi
    if fw == "main":
        return _cached("audit", lambda: sec_audit.run(cfg), again=again)
    item = next((x for x in sec_firewalls.items(cfg) if x["id"] == fw), None)
    if item is None:
        raise sec_fwapi.FirewallAPIError(f"no firewall {fw!r}")
    return _cached(f"audit:{fw}", lambda: sec_audit.run(sec_firewalls.view(cfg, item)), again=again)


def _hunt(hours: float, again: bool = False) -> dict:
    from aurora import sec_hunt
    return _cached(f"hunt:{hours}", lambda: sec_hunt.run(cfg, hours), again=again)


@router.get("/v1/aurora/security/audit", dependencies=[Depends(admin_only)])
async def audit(again: bool = False, fw: str = "main") -> dict:
    from aurora import sec_fwapi
    from aurora import sec_firewalls
    try:
        out = await asyncio.to_thread(_audit, again, fw)
        firewalls = [{"id": x["id"], "name": x.get("name") or x["id"], "kind": x.get("kind")}
                     for x in await asyncio.to_thread(sec_firewalls.items, cfg) if x.get("confirmed") or x["id"] == "main"]
        return {**out, "fw": fw, "firewalls": firewalls}
    except sec_fwapi.FirewallAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None


@router.get("/v1/aurora/security/hunt", dependencies=[Depends(admin_only)])
async def hunt(hours: float = 24, again: bool = False) -> dict:
    return await asyncio.to_thread(_hunt, max(1.0, min(hours, 72.0)), again)


@router.get("/v1/aurora/security/posture", dependencies=[Depends(admin_only)])
async def posture(hours: float = 24, again: bool = False) -> dict:
    """{"risks", "groups" (with their playbook), "audit_error"}: the security officer's page."""
    from aurora import sec_fwapi, sec_incidents, sec_netmap, sec_playbook

    def make():
        try:
            a, err = _audit(again), ""
        except sec_fwapi.FirewallAPIError as e:
            a, err = None, str(e)
        h = _hunt(max(1.0, min(hours, 72.0)), again)
        groups = sec_playbook.correlate(h["findings"], sec_incidents.Incidents(cfg).list("open", archived=False))
        names = sec_netmap.names(cfg)
        for g in groups:
            g["label"] = ("firewall" if g["who"] == sec_playbook.FIREWALL
                          else f"{names[g['who']]} ({g['who']})" if g["who"] in names else g["who"])
            pb = sec_playbook.PLAYBOOKS.get(g["scenario"])
            g["playbook"] = {"title": pb["title"], "steps": [{"what": s, "who": w} for s, w in pb["steps"]]} if pb else None
        return {"risks": sec_playbook.register(a, groups), "groups": [g for g in groups if g["scenario"]],
                "audit_error": err, "hunt": {"lines": h["lines"], "hours": h["hours"]}}
    return await asyncio.to_thread(make)


# ---- Aurora's changes on the firewall --------------------------------------------------------------------------
@router.get("/v1/aurora/security/changes", dependencies=[Depends(admin_only)])
def changes() -> dict:
    from aurora import sec_fwwrite
    return {"write": bool(cfg["AURORA_FIREWALL_WRITE"]), "items": sec_fwwrite.history(cfg)[-30:][::-1]}


@router.post("/v1/aurora/security/changes/plan", dependencies=[Depends(admin_only)])
async def plan(request: Request) -> dict:
    """{"kind": harden | publish | unpublish | quarantine | release | portblock, ...its fields, "fw": the firewall (its
    id in 🔌 Firewall; «main» the settings' one)}: a change planned, not applied."""
    from aurora import sec_fwapi, sec_fwport, sec_fwwrite
    body = await request.json()
    kind = str(body.get("kind", ""))
    fw = str(body.get("fw") or "main")
    try:
        fwc = await asyncio.to_thread(sec_fwwrite.target, cfg, fw)       # the firewall's configuration
    except sec_fwwrite.WriteError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    makers = {
        "harden": lambda: sec_fwwrite.plan_harden(fwc, str(body["rule"]), str(body["ips"]), bool(body.get("log", True))),
        "publish": lambda: sec_fwwrite.plan_publish(fwc, str(body["name"]), str(body["host"]), str(body["ports"]),
                                                    str(body.get("sources", ""))),
        "unpublish": lambda: sec_fwwrite.plan_unpublish(fwc, str(body["name"])),
        "quarantine": lambda: sec_fwwrite.plan_quarantine(fwc, str(body["ip"]), str(body.get("reason", "") or "dalla pagina Firewall")),
        "release": lambda: sec_fwwrite.plan_release(fwc, str(body["ip"])),
        "portblock": lambda: sec_fwport.plan_port_block(fwc, str(body["ip"]), str(body["ports"]),
                                                        str(body.get("reason", "") or "dalla pagina Firewall"),
                                                        float(body.get("hours", 24))),
    }
    if kind not in makers:
        raise HTTPException(status_code=400, detail=f"kind: one of {sorted(makers)}")
    try:
        return await asyncio.to_thread(lambda: sec_fwwrite.propose(cfg, makers[kind](), fw))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"missing field {e}") from None
    except (sec_fwwrite.WriteError, sec_fwapi.FirewallAPIError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/v1/aurora/security/changes/ask", dependencies=[Depends(admin_only)])
async def ask(request: Request) -> dict:
    """{"text": what the owner wants on the firewall}: the local model plans it (sec_fwplan), the code checks every
    step; a planned change, or {"questions"} when the request needs an answer first."""
    from aurora import sec_fwapi, sec_fwplan, sec_fwwrite
    body = await request.json()
    text, fw = str(body.get("text", "")), str(body.get("fw") or "main")      # fw: the firewall it is for
    try:
        fwc = await asyncio.to_thread(sec_fwwrite.target, cfg, fw)
        out = await asyncio.to_thread(sec_fwplan.plan, fwc, text)
    except (sec_fwwrite.WriteError, sec_fwapi.FirewallAPIError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    if "questions" in out:
        return out
    change = sec_fwwrite.propose(cfg, out, fw)
    log.info("audit: owner asked a firewall change in words → %s planned (%d steps)", change["id"], len(change["steps"]))
    return change


@router.post("/v1/aurora/security/changes/{change_id}/{action}", dependencies=[Depends(admin_only)])
async def change_action(change_id: str, action: str) -> dict:
    """apply (the owner's click is the approval), revert, or discard a plan."""
    from aurora import sec_fwapi, sec_fwwrite
    if action not in ("apply", "revert", "discard"):
        raise HTTPException(status_code=404, detail="apply, revert or discard")
    fn = {"apply": sec_fwwrite.apply, "revert": sec_fwwrite.revert, "discard": sec_fwwrite.discard}[action]
    try:
        out = await asyncio.to_thread(fn, cfg, change_id)
    except (sec_fwwrite.WriteError, sec_fwapi.FirewallAPIError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    _kept.pop("audit", None)                        # the configuration changed: read it again next time
    log.info("audit: owner %s firewall change %s → %s", action, change_id, out["status"])
    return out


# ---- Aurora's own machine and firewall (owner, 2026-10-08: «un menù a parte per il firewall di Aurora… mini CISO») --
@router.get("/v1/aurora/security/aurora", dependencies=[Depends(admin_only)])
async def aurora_host() -> dict:
    """Her firewall (installed, on, the addresses it keeps off), the decoys, what listens on her machine and who can
    reach it, the incidents about her machine (a decoy touched, the API's lockout)."""
    from aurora import sec_hostaudit, sec_hostfw, sec_incidents

    def make():
        incidents = [i for i in sec_incidents.Incidents(cfg).list(archived=False)
                     if i.get("kind") in ("honeypot", "auth_fail", "login")][-20:][::-1]
        return {"hostfw": {"on": bool(cfg["AURORA_HOSTFW"]), "installed": sec_hostfw.available(),
                           "active": sec_hostfw.active(cfg)},
                "decoys": [p for p in str(cfg["AURORA_HONEYPOT_PORTS"] or "").split(",") if p.strip()],
                "audit": sec_hostaudit.run(cfg), "incidents": incidents}
    return await asyncio.to_thread(make)


@router.post("/v1/aurora/security/aurora/block", dependencies=[Depends(admin_only)])
async def aurora_block(request: Request) -> dict:
    """{"ip", "why", "hours"}: an address kept off Aurora's machine by the owner (her nftables table)."""
    from aurora import sec_hostfw
    body = await request.json()
    try:
        out = await asyncio.to_thread(sec_hostfw.block, cfg, str(body.get("ip", "")), str(body.get("why") or "dal proprietario")[:200],
                                      float(body.get("hours") or 24))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    log.info("audit: owner kept %s off Aurora's machine", body.get("ip"))
    return out


# ---- the firewall's documentation ------------------------------------------------------------------------------
@router.get("/v1/aurora/security/docs", dependencies=[Depends(admin_only)])
def docs(q: str = "", kind: str = "") -> dict:
    from aurora import sec_fwdocs
    return {"stats": sec_fwdocs.stats(cfg), "hits": sec_fwdocs.search(cfg, q, 6, kind or None) if q.strip() else []}
