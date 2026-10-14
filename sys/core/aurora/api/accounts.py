# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""☁️ Cloud accounts from the WebUI (mdl_accounts, ROADMAP 106): each user sees the shared accounts and their own, adds
their own (a key, or a Claude subscription logged in from the page); the admin adds the shared ones and sets the
policy."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from aurora import mdl_accounts

from .core import _admin, auth, cfg, log, me

router = APIRouter()


def _is_admin() -> bool:
    return me() == _admin()


def _owned(account_id: str) -> dict:
    """The account, if this user may act on it: their own, or any for the admin."""
    try:
        a = mdl_accounts.get(cfg.now(), account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such account") from None
    if not _is_admin() and not (a["scope"] == "user" and a.get("user") == me()):
        raise HTTPException(status_code=403, detail="not your account")
    return a


@router.get("/v1/aurora/accounts", dependencies=[Depends(auth)])
def accounts() -> dict:
    from aurora.mdl_router import PROVIDERS, configured
    c = cfg.now()
    d = mdl_accounts.load(c)
    return {"policy": d["policy"], "policies": list(mdl_accounts.POLICIES), "admin": _is_admin(), "me": me(),
            "accounts": mdl_accounts.visible(c, me(), _is_admin()),
            "providers": [{"id": p, "key": p != "claude_code", "key_optional": bool(s.get("key_optional")),
                           "ready": configured(p, c)}
                          for p, s in PROVIDERS.items() if s["kind"] != "local"],
            # what this user's calls use now, per provider: an account, the installation's setup, or nothing
            "using": {p: ("installation" if (a := mdl_accounts.pick(c, p)) is mdl_accounts.LEGACY else
                          a["id"] if a else None) for p, s in PROVIDERS.items() if s["kind"] != "local"}}


@router.post("/v1/aurora/accounts", dependencies=[Depends(auth)])
async def add(request: Request) -> dict:
    body = await request.json()
    scope = body.get("scope", "user")
    if scope == "shared" and not _is_admin():
        raise HTTPException(status_code=403, detail="only the admin adds a shared account")
    try:
        a = mdl_accounts.add(cfg.now(), str(body.get("provider", "")), scope, me(), str(body.get("label", "")),
                             str(body.get("key", "")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    log.info("audit: cloud account %s added (%s, %s) by %s", a["id"], a["provider"], scope, me())
    return {"id": a["id"], "provider": a["provider"], "scope": a["scope"]}


@router.post("/v1/aurora/accounts/{account_id}/login", dependencies=[Depends(auth)])
def login(account_id: str) -> dict:
    a = _owned(account_id)
    if a["provider"] != "claude_code":
        raise HTTPException(status_code=400, detail="only a Claude account signs in")
    try:
        return {"url": mdl_accounts.login_start(cfg.now(), account_id)}
    except ImportError:                                  # Windows: no terminal of its own for the CLI (pty)
        raise HTTPException(status_code=501, detail="the sign-in from the page needs Linux or macOS: run «claude auth "
                                                    "login» once on this machine") from None
    except (RuntimeError, OSError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from None


@router.post("/v1/aurora/accounts/{account_id}/code", dependencies=[Depends(auth)])
async def code(account_id: str, request: Request) -> dict:
    _owned(account_id)
    text = str((await request.json()).get("code", "")).strip()
    if not text or len(text) > 500:
        raise HTTPException(status_code=400, detail="the code from the sign-in page")
    try:
        st = mdl_accounts.login_finish(cfg.now(), account_id, text)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    log.info("audit: cloud account %s signed in: %s", account_id, st["logged_in"])
    return st


@router.get("/v1/aurora/accounts/{account_id}/status", dependencies=[Depends(auth)])
def status(account_id: str) -> dict:
    a = _owned(account_id) if not _shared(account_id) else mdl_accounts.get(cfg.now(), account_id)
    st = mdl_accounts.status(cfg.now(), a["id"])
    return st if _is_admin() or a["scope"] == "user" else {**st, "email": ""}    # a shared account's address: admin


def _shared(account_id: str) -> bool:
    try:
        return mdl_accounts.get(cfg.now(), account_id)["scope"] == "shared"
    except KeyError:
        raise HTTPException(status_code=404, detail="no such account") from None


@router.delete("/v1/aurora/accounts/{account_id}", dependencies=[Depends(auth)])
def remove(account_id: str) -> dict:
    _owned(account_id)
    mdl_accounts.remove(cfg.now(), account_id)
    log.info("audit: cloud account %s removed by %s", account_id, me())
    return {"removed": account_id}


@router.put("/v1/aurora/accounts/policy", dependencies=[Depends(auth)])
async def policy(request: Request) -> dict:
    if not _is_admin():
        raise HTTPException(status_code=403, detail="only the admin")
    p = str((await request.json()).get("policy", ""))
    try:
        mdl_accounts.set_policy(cfg.now(), p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    log.info("audit: cloud accounts policy → %s", p)
    return {"policy": p}
