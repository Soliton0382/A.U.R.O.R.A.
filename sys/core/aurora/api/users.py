# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Login and users (docs/MULTIUSER.md, U5): name, password and the Authenticator's code; the first login enrols the
code (a QR); each user's own account; the admin's Users page (create, reset, delete with the purge's list)."""
from __future__ import annotations

from aurora import sys_context, sys_log, sys_users_layout
from aurora.sys_devices import COOKIE
from aurora.sys_users import Users, otpauth_uri
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .core import BASE, _admin, _failed, _locked, auth, cfg, devices, log, me

router = APIRouter()


def _users() -> Users:
    return Users(BASE.base or BASE)


async def admin_only(request: Request) -> None:
    await auth(request)
    if me() != _admin():
        raise HTTPException(status_code=403, detail="only the admin")


# ---- login --------------------------------------------------------------------------------------------------------
def users_login() -> bool:
    """Name, password and code at the login: multi-user, or single-user with the admin's password (and code) set."""
    if str(cfg["AURORA_USER_MODE"]) == "multi":
        return True
    admin = _admin()
    u = _users().by_name(admin) if admin else None
    return bool(u and u["has_password"] and (u["totp_on"] or not cfg["AURORA_USERS_MFA"]))



@router.post("/v1/aurora/login")
async def login(request: Request) -> JSONResponse:
    """{"name", "password", "code", "device"}. Multi-user only (single-user logs in with the API key). With a right
    password and no authenticator yet: {"enroll": {"secret", "uri"}}, then the same call with the first code."""
    _locked(request)
    if not users_login():
        raise HTTPException(status_code=409, detail="single-user without the admin's password: log in with the API key")
    body = await request.json()
    name, password, code = str(body.get("name", "")).strip(), str(body.get("password", "")), str(body.get("code", "")).strip()
    if str(cfg["AURORA_USER_MODE"]) != "multi" and name != _admin():     # single-user: the admin alone
        _failed(request)
        raise HTTPException(status_code=401, detail="wrong name or password")
    users = _users()
    u = users.check_password(name, password)
    if u is None:
        _failed(request)
        raise HTTPException(status_code=401, detail="wrong name or password")
    mfa = bool(cfg["AURORA_USERS_MFA"])
    if mfa and not u["totp_on"]:
        if not code:                                       # the first login: scan the QR, then the first code
            secret = users.totp_begin(u["id"])
            return JSONResponse({"enroll": {"secret": secret, "uri": otpauth_uri(secret, name)}})
        if not users.totp_confirm(u["id"], code):
            _failed(request)
            raise HTTPException(status_code=401, detail="wrong code")
    elif users.login(name, password, code, mfa=mfa) is None:
        _failed(request)
        raise HTTPException(status_code=401, detail="wrong code")
    token, rec = devices.register(str(body.get("device", "")) or request.headers.get("user-agent", "")[:60],
                                  request.headers.get("user-agent", ""), user=u["name"])
    log.info("audit: login of %s, device %s", u["name"], rec["id"])
    with sys_context.acting_as(u["name"]):              # the user's own line: their purge removes it
        sys_log.trace("api", "user.login", {"device": rec["id"]})
        from .core import note
        note("api", "device.new", {"text": rec["name"]})
    resp = JSONResponse({"user": u["name"], "role": u["role"]})
    resp.set_cookie(COOKIE, token, max_age=cfg["AURORA_DEVICE_DAYS"] * 86400, httponly=True, secure=True,
                    samesite="strict", path="/")
    return resp


# ---- the user's own account ---------------------------------------------------------------------------------------
@router.get("/v1/aurora/me", dependencies=[Depends(auth)])
def whoami() -> dict:
    name = me()
    u = _users().by_name(name) if name else None
    return {"name": name, "role": (u or {}).get("role", "admin"), "admin": name == _admin(),
            "mode": str(cfg["AURORA_USER_MODE"]), "mfa": bool(cfg["AURORA_USERS_MFA"]),
            "has_password": bool(u and u["has_password"]), "totp_on": bool(u and u["totp_on"])}


@router.post("/v1/aurora/me/password", dependencies=[Depends(auth)])
async def my_password(request: Request) -> dict:
    """{"old", "new"}: the old one is asked when there is one."""
    body = await request.json()
    users, name = _users(), me()
    u = users.by_name(name or "")
    if u is None:
        raise HTTPException(status_code=409, detail="no users on this installation yet")
    if u["has_password"] and users.check_password(name, str(body.get("old", ""))) is None:
        raise HTTPException(status_code=401, detail="the current password is wrong")
    try:
        users.set_password(u["id"], str(body.get("new", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: %s changed their password", name)
    return {"ok": True}


@router.post("/v1/aurora/me/totp", dependencies=[Depends(auth)])
async def my_totp(request: Request) -> dict:
    """Without a code: a new secret and its QR (not active yet). With {"code"}: confirmed and active."""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    users, name = _users(), me()
    u = users.by_name(name or "")
    if u is None:
        raise HTTPException(status_code=409, detail="no users on this installation yet")
    code = str(body.get("code", "")).strip()
    if not code:
        secret = users.totp_begin(u["id"])
        return {"secret": secret, "uri": otpauth_uri(secret, name)}
    if not users.totp_confirm(u["id"], code):
        raise HTTPException(status_code=401, detail="wrong code")
    log.info("audit: %s enrolled an authenticator", name)
    return {"ok": True}


def forget(name: str) -> None:
    """What the API holds in memory of a deleted user: their activity, runs, pipeline, plugins, configuration."""
    from aurora import sys_user_config
    from . import core
    with core._activity_cond:
        core._activity[:] = [a for a in core._activity if a.get("user") != name]
    for rid in [k for k, r in list(core._runs.items()) if r.get("user") == name]:
        core._runs.pop(rid, None)
    core._state.get("pipelines", {}).pop(name, None)
    core._state.get("plugin_hosts", {}).pop(name, None)
    sys_user_config._cache.pop(name, None)


# ---- the user's own API keys (Chatbox, LibreChat...: an OpenAI-compatible client works as this user) ------------
@router.get("/v1/aurora/me/keys", dependencies=[Depends(auth)])
def my_keys() -> dict:
    who = me()
    keys = [d for d in devices.list() if d.get("kind") == "api" and (d.get("user") or _admin()) == who]
    domain, port = cfg["AURORA_DOMAIN"], cfg["AURORA_HTTPS_PORT"]
    return {"keys": keys, "base_url": f"https://{domain}{'' if port == 443 else f':{port}'}/v1", "model": "aurora"}


@router.post("/v1/aurora/me/keys", dependencies=[Depends(auth)])
async def my_key_new(request: Request) -> dict:
    """{"name"}: a key for one program; shown only now, kept only as a hash; it works as this user."""
    name = str((await request.json()).get("name", "")).strip()[:60] or "API"
    token, rec = devices.register(name, "api key", user=me(), kind="api")
    log.info("audit: %s created an API key (%s)", me(), rec["id"])
    return {"key": token, **rec}


@router.delete("/v1/aurora/me/keys/{key_id}", dependencies=[Depends(auth)])
def my_key_revoke(key_id: str) -> dict:
    who = me()
    d = next((x for x in devices.list() if x["id"] == key_id and x.get("kind") == "api"), None)
    if d is None or (d.get("user") or _admin()) != who:
        raise HTTPException(status_code=404, detail="unknown key")
    devices.revoke(key_id)
    log.info("audit: %s revoked an API key (%s)", who, key_id)
    return {"revoked": key_id}


# ---- the admin's Users page ---------------------------------------------------------------------------------------
@router.get("/v1/aurora/users", dependencies=[Depends(admin_only)])
def users_list() -> dict:
    base = BASE.base or BASE
    out = []
    for u in _users().list():
        home = sys_users_layout.usr_home(base, u["name"])
        out.append({**u, "files": sum(1 for p in home.rglob("*") if p.is_file()) if home.exists() else 0,
                    "devices": sum(1 for d in devices.list() if d.get("user") == u["name"])})
    return {"users": out, "admin": _admin(), "mode": str(cfg["AURORA_USER_MODE"])}


@router.post("/v1/aurora/users", dependencies=[Depends(admin_only)])
async def users_add(request: Request) -> dict:
    """{"name", "password"}: a user with their usr/<name>/ tree; they enrol their authenticator at the first login."""
    body = await request.json()
    base = BASE.base or BASE
    name = str(body.get("name", "")).strip()
    try:
        sys_users_layout.check_name(base, name)
        if not sys_users_layout.migrated(base):
            raise ValueError("the per-user layout comes first (sys/core/script/sys_users_migrate.py)")
        if len(str(body.get("password", ""))) < 10:
            raise ValueError("password: at least 10 characters")
        rec = _users().add(name, "user", str(body["password"]))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    sys_users_layout.make_home(base, name)
    log.info("audit: user %s created by %s", name, me())
    sys_log.trace("api", "user.create", {"name": name})
    return rec


@router.post("/v1/aurora/users/{name}/password", dependencies=[Depends(admin_only)])
async def users_password(name: str, request: Request) -> dict:
    u = _users().by_name(name)
    if u is None:
        raise HTTPException(status_code=404, detail="no such user")
    try:
        _users().set_password(u["id"], str((await request.json()).get("password", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: password of %s reset by %s", name, me())
    return {"ok": True}


@router.post("/v1/aurora/users/{name}/totp-reset", dependencies=[Depends(admin_only)])
def users_totp_reset(name: str) -> dict:
    u = _users().by_name(name)
    if u is None:
        raise HTTPException(status_code=404, detail="no such user")
    _users().totp_reset(u["id"])
    log.info("audit: authenticator of %s reset by %s", name, me())
    return {"ok": True}


@router.delete("/v1/aurora/users/{name}", dependencies=[Depends(admin_only)])
def users_delete(name: str, request: Request) -> dict:
    """Without ?confirm=purge: what would go (409 with the list). With it: the user and all that is theirs."""
    base, admin = BASE.base or BASE, _admin()
    if name == admin:
        raise HTTPException(status_code=422, detail="the admin cannot be deleted")
    if _users().by_name(name) is None:
        raise HTTPException(status_code=404, detail="no such user")
    if request.query_params.get("confirm") != "purge":
        raise HTTPException(status_code=409, detail={"message": f"deleting {name} removes all that is theirs",
                                                     "plan": [{"user": name, "items": sys_users_layout.purge_plan(base, name)}]})
    try:
        out = sys_users_layout.purge(base, name, admin)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    forget(name)
    log.info("audit: user %s deleted by %s", name, me())
    sys_log.trace("api", "user.delete", {"name": name})
    return {"deleted": name, "devices": out["devices"]}
