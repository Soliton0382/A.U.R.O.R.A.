# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔑 Keys and recovery (sys_key_recovery, N64): where Aurora's own key is and how it is bound (TPM), the escrow, and the recovery code: made and shown once,
checked without showing it. The admin's alone: the key opens every user's data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from aurora import sys_key_recovery as R
from aurora import sys_keyring
from .core import cfg, in_thread, log
from .users import admin_only

router = APIRouter()


@router.get("/v1/aurora/keys", dependencies=[Depends(admin_only)])
async def keys() -> dict:
    c = cfg.now()
    return {"where": sys_keyring.where(c), "bound": sys_keyring.bound(c), "tpm": await in_thread(sys_keyring.tpm),
            "escrow": (sys_keyring.folder(c) / "aurora.escrow").is_file(), "recovery": R.status(c)}


@router.post("/v1/aurora/keys/recovery", dependencies=[Depends(admin_only)])
async def recovery_new() -> dict:
    """A new recovery code, in this answer only (the old one opens nothing after it)."""
    try:
        code = await in_thread(R.make, cfg.now())
    except sys_keyring.Locked as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    log.info("audit: recovery code made (the old one no longer opens)")
    return {"code": code, "recovery": R.status(cfg.now())}


@router.post("/v1/aurora/keys/recovery/check", dependencies=[Depends(admin_only)])
async def recovery_check(request: Request) -> dict:
    """{"code"} -> whether it opens the recovery file (nothing written, nothing logged of the code)."""
    body = await request.json()
    ok = await in_thread(R.opens, cfg.now(), str(body.get("code") or ""))
    log.info("audit: recovery code checked: %s", "it opens" if ok else "it does not open")
    return {"opens": ok}
