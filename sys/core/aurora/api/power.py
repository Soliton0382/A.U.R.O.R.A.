# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Computers and servers restarted or shut down over SSH (sys_power_hosts), and the firewall console's trial
(sec_fwpower): the admin's."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from .core import cfg
from .users import admin_only

router = APIRouter()


def _one(hid: str) -> dict:
    from aurora import sys_power_hosts
    it = next((x for x in sys_power_hosts.load(cfg) if x["id"] == hid), None)
    if it is None:
        raise HTTPException(status_code=404, detail="not found")
    return it


@router.get("/v1/aurora/power/hosts", dependencies=[Depends(admin_only)])
def hosts() -> dict:
    from aurora import sys_power_hosts, sys_ups
    return {"items": sys_power_hosts.load(cfg), "public_key": sys_power_hosts.public_key(cfg), "ups": sys_ups.status(cfg)}


@router.put("/v1/aurora/power/hosts/{hid}", dependencies=[Depends(admin_only)])
def host_put(hid: str, body: dict) -> dict:
    from aurora import sys_power_hosts
    try:
        return sys_power_hosts.put(cfg, body, None if hid == "new" else hid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.delete("/v1/aurora/power/hosts/{hid}", dependencies=[Depends(admin_only)])
def host_delete(hid: str) -> dict:
    from aurora import sys_power_hosts
    if not sys_power_hosts.delete(cfg, hid):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": hid}


@router.get("/v1/aurora/power/hosts/{hid}/setup", dependencies=[Depends(admin_only)])
def host_setup(hid: str) -> dict:
    from aurora import sys_power_hosts
    return sys_power_hosts.setup(cfg, _one(hid))


@router.post("/v1/aurora/power/hosts/{hid}/{action}", dependencies=[Depends(admin_only)])
async def host_action(hid: str, action: str) -> dict:
    from aurora import sys_power_hosts
    if action == "test":
        try:
            return await asyncio.to_thread(sys_power_hosts.test, cfg, hid)
        except KeyError:
            raise HTTPException(status_code=404, detail="not found") from None
    if action not in ("restart", "shutdown"):
        raise HTTPException(status_code=400, detail="action: test, restart or shutdown")
    return await asyncio.to_thread(sys_power_hosts.run, cfg, _one(hid), action)


@router.post("/v1/aurora/security/firewalls/{fid}/console", dependencies=[Depends(admin_only)])
async def firewall_console(fid: str) -> dict:
    """The console reached and left, nothing typed but «exit»: the key works for the restart and the UPS."""
    from aurora import sec_firewalls, sec_fwpower
    it = next((x for x in sec_firewalls.items(cfg) if x["id"] == fid), None)
    if it is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        await asyncio.to_thread(sec_fwpower.act, sec_firewalls.view(cfg, it), "test")
        return {"ok": True}
    except sec_fwpower.PowerError as e:
        return {"ok": False, "error": str(e)}
