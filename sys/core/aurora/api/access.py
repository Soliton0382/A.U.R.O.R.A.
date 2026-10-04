# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Registered devices (WebUI login with the key, cookie), logout."""
from __future__ import annotations

from aurora import sys_log
from aurora.sys_devices import COOKIE
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .core import _admin, _failed, _is_key, _locked, auth, cfg, devices, log

router = APIRouter()


# ---- devices -----------------------------------------------------------------------------------
@router.post("/v1/aurora/devices")
async def register_device(request: Request) -> Response:
    """Only the API key can register a device: a device cannot make more devices."""
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    _locked(request)
    if not _is_key(bearer):
        _failed(request)
        raise HTTPException(status_code=401, detail="the API key is required to register a device")
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    token, rec = devices.register(body.get("name", ""), request.headers.get("user-agent", ""))
    log.info("audit: device registered: %s (%s)", rec["name"], rec["id"])
    sys_log.trace("api", "device.register", {"id": rec["id"], "name": rec["name"]})
    from .core import note
    note("api", "device.new", {"text": rec["name"]})              # a new device on the account: told
    resp = JSONResponse(rec)
    resp.set_cookie(COOKIE, token, max_age=cfg["AURORA_DEVICE_DAYS"] * 86400, httponly=True, secure=True,
                    samesite="strict", path="/")
    return resp


@router.get("/v1/aurora/devices", dependencies=[Depends(auth)])
def list_devices(request: Request) -> list[dict]:
    """The user's own devices; the admin sees everyone's (with whose they are)."""
    mine_dev = getattr(request.state, "device", None)
    who, admin = request.state.user, _admin()
    return [{**d, "current": bool(mine_dev and mine_dev["id"] == d["id"])} for d in devices.list()
            if who == admin or (d.get("user") or admin) == who]


@router.delete("/v1/aurora/devices/{device_id}", dependencies=[Depends(auth)])
def revoke_device(device_id: str, request: Request) -> dict:
    who, admin = request.state.user, _admin()
    d = next((x for x in devices.list() if x["id"] == device_id), None)
    if d is None or (who != admin and (d.get("user") or admin) != who):  # another user's device: as if absent
        raise HTTPException(status_code=404, detail="unknown device")
    if not devices.revoke(device_id):
        raise HTTPException(status_code=404, detail="unknown device")
    log.info("audit: device revoked: %s", device_id)
    sys_log.trace("api", "device.revoke", {"id": device_id})
    return {"revoked": device_id}


@router.post("/v1/aurora/logout", dependencies=[Depends(auth)])
def logout(request: Request) -> Response:
    me = getattr(request.state, "device", None)
    if me:
        devices.revoke(me["id"])
    resp = JSONResponse({"logged_out": bool(me)})
    resp.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return resp
