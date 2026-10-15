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
    from aurora import mdl_services
    from aurora.mdl_router import PROVIDERS, _services, configured
    c = cfg.now()
    _services(c)
    d = mdl_accounts.load(c)
    return {"policy": d["policy"], "policies": list(mdl_accounts.POLICIES), "admin": _is_admin(), "me": me(),
            "accounts": mdl_accounts.visible(c, me(), _is_admin()), "presets": mdl_services.PRESETS,
            "providers": [{"id": p, "key": p != "claude_code", "key_optional": bool(s.get("key_optional")),
                           "ready": configured(p, c), "label": s["label"], "custom": bool(s.get("custom")),
                           "base": s.get("base", "") if s.get("custom") else ""}
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


# ---- services of one's own (mdl_services): OpenAI-compatible, named, added and removed by the admin ----------------
def _admin_needed() -> None:
    if not _is_admin():
        raise HTTPException(status_code=403, detail="only the admin adds or removes a service")


@router.post("/v1/aurora/accounts/services/try", dependencies=[Depends(auth)])
async def try_service(request: Request) -> dict:
    """The service's own list of models (GET <address>/models), before it is saved: the address proved, not trusted."""
    import httpx

    from aurora import mdl_services
    _admin_needed()
    body = await request.json()
    try:
        base = mdl_services.clean_base(str(body.get("base", "")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    key = str(body.get("key", "")).strip()
    try:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=10)
        r.raise_for_status()
        data = r.json().get("data") or r.json().get("models") or []
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"{base}: {str(e)[:200]}") from None
    models = sorted({str(m.get("id") or m.get("name") or "") for m in data if isinstance(m, dict)} - {""})
    return {"ok": True, "models": models[:200], "count": len(models)}


@router.post("/v1/aurora/accounts/services", dependencies=[Depends(auth)])
async def add_service(request: Request) -> dict:
    """A named service; with a key, its shared account too (the key travels like every other)."""
    from aurora import mdl_services
    _admin_needed()
    body = await request.json()
    try:
        row = mdl_services.add(cfg.now(), str(body.get("name", "")), str(body.get("base", "")))
        key = str(body.get("key", "")).strip()
        if key:
            mdl_accounts.add(cfg.now(), row["id"], "shared", me(), row["name"], key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    log.info("audit: cloud service %s added (%s) by %s", row["id"], row["base"], me())
    return row


@router.delete("/v1/aurora/accounts/services/{sid}", dependencies=[Depends(auth)])
def remove_service(sid: str) -> dict:
    from aurora import mdl_services
    _admin_needed()
    try:
        mdl_services.remove(cfg.now(), sid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="no such service") from None
    log.info("audit: cloud service %s removed by %s", sid, me())
    return {"removed": sid}


# ---- 🔒 what is masked toward the cloud (owner, 16 Oct: «oltre a vedere il set delle parole mascherate, avere la
# possibilità di aggiungerle»): the owner's own words (AURORA_CLOUD_MASK_WORDS, changed here), and the ones Aurora masks
# by herself (the owner's name, domain, place, coordinates, home folder) shown, not changed here
@router.get("/v1/aurora/accounts/mask", dependencies=[Depends(auth)])
def mask_words() -> dict:
    """What is masked towards the cloud for the asking person (owner, 16 Oct: «far vedere i mascheramenti di default e
    quelli impostati per utente»): the rules always on, the person's own words, the installation's (their words to
    the admin; how many, to a user), and those taken from the settings."""
    from aurora import sec_mask
    words = lambda k: [w.strip() for w in str(cfg[k] or "").split(",") if w.strip()]   # noqa: E731
    admin = me() == _admin()
    mine, house = words("AURORA_CLOUD_MASK_MINE"), words("AURORA_CLOUD_MASK_WORDS")
    p = sec_mask.Pseudonymizer(cfg)
    auto = [w for w in p.private if w not in mine and w not in house]
    return {"rules": [{"kind": k, "it": i, "en": e, "example": x} for k, i, e, x in sec_mask.RULES],
            "mine": mine, "installation": house if admin else [], "installation_n": len(house), "admin": admin,
            "automatic": auto, "secrets": len(p.secrets)}
