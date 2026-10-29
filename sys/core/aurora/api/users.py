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


def may_manage(area: str):
    """A route of a user's own area (sys_users_perm): the admin always, a user when the admin lets them."""
    async def dep(request: Request, _: None = Depends(auth)) -> None:     # auth as a sub-dependency: seen as such
        from aurora import sys_users_perm
        if not sys_users_perm.may(BASE, me(), area, _admin()):
            raise HTTPException(status_code=403, detail=f"the admin keeps «{area}» for themselves (👥 Users → permissions)")
    return dep


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
def whoami(request: Request) -> dict:
    name = me()
    u = _users().by_name(name) if name else None
    from aurora import sys_persona, sys_users_perm
    return {"name": name, "role": (u or {}).get("role", "admin"), "admin": name == _admin(),
            "assistant": sys_persona.name(cfg), "personality": str(cfg["AURORA_PERSONALITY"]),
            "gender": str(cfg["AURORA_ASSISTANT_GENDER"]), "person": str(cfg["AURORA_OWNER_NAME"]),
            "mode": str(cfg["AURORA_USER_MODE"]), "mfa": bool(cfg["AURORA_USERS_MFA"]),
            "has_password": bool(u and u["has_password"]), "totp_on": bool(u and u["totp_on"]),
            "welcomed": (name or "") in _welcomed(), "prefs": _prefs().get(name or "", {}),
            "may": {a: sys_users_perm.may(BASE, name, a, _admin()) for a in sys_users_perm.AREAS},
            "assist": getattr(request.state, "assist", None)}       # 🛟 the admin inside this account: the banner


# each person's look of the WebUI, on any device (ROADMAP 107; owner, 15 Oct: «salva lo stile per utente sul server»):
# the menu's style, the pinned pages and the colours (owner, 15 Oct: «leghiamo le configurazioni agli utenti e non ai
# device»)
PREFS = {"style": ("completo", "essenziale", "misto"),
         "theme": ("aurora", "notte", "oceano", "foresta", "tramonto", "chiaro", "contrasto"),
         # how dates are written (owner, 19 Oct: «la selezione del tipo di formato della data, sai dd-mm-aaaa o mm-dd-aaaa»)
         "date_format": ("dd/mm/yyyy", "dd-mm-yyyy", "mm/dd/yyyy", "mm-dd-yyyy", "yyyy-mm-dd")}


def _prefs_file():
    return (BASE.base or BASE).path("AURORA_STATUS_DIR") / "ui_prefs.json"


def _prefs() -> dict:
    import json
    try:
        return json.loads(_prefs_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@router.put("/v1/aurora/me/prefs", dependencies=[Depends(auth)])
async def my_prefs(request: Request) -> dict:
    """{"style"?, "theme"?, "date_format"?, "pins"?, "tiles"?}: only what is sent changes; a value out of its list is
    refused."""
    import json
    import re
    body = await request.json()
    mine = dict(_prefs().get(me() or "", {}))
    for key, allowed in PREFS.items():
        if key in body:
            if body[key] not in allowed:
                raise HTTPException(status_code=422, detail=f"{key}: one of {allowed}")
            mine[key] = body[key]
    if "pins" in body:
        pins = body["pins"] if isinstance(body["pins"], list) else []
        if not all(isinstance(x, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", x) for x in pins):
            raise HTTPException(status_code=422, detail="pins: page ids")
        mine["pins"] = list(dict.fromkeys(pins))[-8:]
    if "tiles" in body:                              # Oggi's tiles: their order and the hidden ones (today_edit.js)
        tiles = body["tiles"] if isinstance(body["tiles"], dict) else {}
        lists = [tiles.get("order", []), tiles.get("off", [])]
        if not all(isinstance(x, list) and len(x) <= 80 for x in lists) or not all(   # a tile, or a page ("page:<id>")
                isinstance(x, str) and re.fullmatch(r"(page:)?[a-z][a-z0-9_-]{0,40}", x) for x in lists[0] + lists[1]):
            raise HTTPException(status_code=422, detail="tiles: {order: [ids], off: [ids]}")
        mine["tiles"] = {"order": list(dict.fromkeys(lists[0])), "off": list(dict.fromkeys(lists[1]))}
    allp = {**_prefs(), me() or "": mine}
    f = _prefs_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(allp), encoding="utf-8")
    return mine


# the first run's five screens (ROADMAP 107): seen once per person, on any device; the Appearance dialog opens them again
def _welcome_file():
    return (BASE.base or BASE).path("AURORA_STATUS_DIR") / "welcomed.json"


def _welcomed() -> dict:
    import json
    try:
        return json.loads(_welcome_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@router.post("/v1/aurora/me/welcomed", dependencies=[Depends(auth)])
def welcomed() -> dict:
    import json
    import time
    seen = {**_welcomed(), me() or "": time.time()}
    f = _welcome_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(seen), encoding="utf-8")
    return {"welcomed": True}


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
    here = getattr(request.state, "device", None)       # C428: the other sessions out, this one kept
    out = devices.revoke_user(name, keep=here["id"] if here else None)
    log.info("audit: %s changed their password; %d other device(s) logged out", name, out)
    return {"ok": True, "logged_out": out}


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
        if u["totp_on"]:                                 # C440: changing an active authenticator asks for both first
            if users.check_password(name, str(body.get("password", ""))) is None:
                raise HTTPException(status_code=401, detail="the password is wrong")
            if not users.totp_current(u["id"], str(body.get("current", "")).strip()):
                raise HTTPException(status_code=401, detail="the current authenticator's code is wrong")
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
    from aurora import kno_anger, mdl_budget, sys_assist, sys_user_config, sys_users_perm
    base = BASE.base or BASE
    used = mdl_budget.today(base).get("users", {})       # each user's cloud tokens today, every provider
    out = []
    for u in _users().list():
        home = sys_users_layout.usr_home(base, u["name"])
        out.append({**u, "files": sum(1 for p in home.rglob("*") if p.is_file()) if home.exists() else 0,
                    "devices": sum(1 for d in devices.list() if d.get("user") == u["name"]),
                    "cloud_cap": sys_users_perm.cloud_cap(base, u["name"]), "cloud_today": used.get(u["name"], 0),
                    "conduct": kno_anger.card(sys_user_config.for_user(base, u["name"])),
                    "assist": sys_assist.granted(base, u["name"])})
    return {"users": out, "admin": _admin(), "mode": str(cfg["AURORA_USER_MODE"])}


@router.get("/v1/aurora/users/permissions", dependencies=[Depends(admin_only)])
def users_permissions() -> dict:
    from aurora import sys_users_perm
    return sys_users_perm.table(BASE, [u["name"] for u in _users().list()], _admin())


@router.put("/v1/aurora/users/permissions", dependencies=[Depends(admin_only)])
async def users_permission_set(request: Request) -> dict:
    """{"user", "area", "allowed"}: whether a user manages that area of their own."""
    from aurora import sys_users_perm
    body = await request.json()
    user, area = str(body.get("user", "")), str(body.get("area", ""))
    if not _users().by_name(user):
        raise HTTPException(status_code=404, detail="no such user")
    try:
        sys_users_perm.set_(BASE, user, area, bool(body.get("allowed")))
    except KeyError:
        raise HTTPException(status_code=422, detail="area: one of routines, settings, autonomy") from None
    log.info("audit: %s may%s manage their %s", user, "" if body.get("allowed") else " not", area)
    return sys_users_perm.table(BASE, [u["name"] for u in _users().list()], _admin())


@router.put("/v1/aurora/users/cloud", dependencies=[Depends(admin_only)])
async def users_cloud_set(request: Request) -> dict:
    """{"user", "tokens"}: a user's tokens a day on the cloud, every provider and the subscription (0: no ceiling);
    the admin's own use is never capped here."""
    from aurora import sys_users_perm
    body = await request.json()
    user = str(body.get("user", ""))
    if not _users().by_name(user):
        raise HTTPException(status_code=404, detail="no such user")
    if user == _admin():
        raise HTTPException(status_code=422, detail="the admin has no ceiling of their own")
    try:
        sys_users_perm.set_cloud(BASE, user, int(body.get("tokens", 0)))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: %s's cloud ceiling set to %s tokens a day", user, body.get("tokens"))
    return sys_users_perm.table(BASE, [u["name"] for u in _users().list()], _admin())


@router.post("/v1/aurora/users", dependencies=[Depends(admin_only)])
async def users_add(request: Request) -> dict:
    """{"name", "password"}: a user with their usr/<name>/ tree; they enrol their authenticator at the first login."""
    body = await request.json()
    base = BASE.base or BASE
    name = str(body.get("name", "")).strip().lower()     # "Giulia" and "giulia" are one user
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
    person = str(body.get("person", "")).strip()[:60]           # how the assistant calls them: not the login name
    if person:
        from aurora import sys_user_config
        sys_user_config.write(base, name, {"AURORA_OWNER_NAME": person})
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
    out = devices.revoke_user(name)                      # C428: whoever had a session of theirs is out
    log.info("audit: password of %s reset by %s; %d device(s) logged out", name, me(), out)
    return {"ok": True, "logged_out": out}


@router.post("/v1/aurora/users/{name}/totp-reset", dependencies=[Depends(admin_only)])
def users_totp_reset(name: str) -> dict:
    u = _users().by_name(name)
    if u is None:
        raise HTTPException(status_code=404, detail="no such user")
    _users().totp_reset(u["id"])
    out = devices.revoke_user(name)                      # C428
    log.info("audit: authenticator of %s reset by %s; %d device(s) logged out", name, me(), out)
    return {"ok": True, "logged_out": out}


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
