# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A social account connected from the plugin's card (owner, 15 Oct: TikTok's review wants the whole flow in the
website, and «da cli voglio che si acceda il minimo possibile»): the card asks for the address to open, the provider
sends the browser back to the WebUI (the Redirect URI) with a code and the state, the page hands them here, the code
becomes the refresh token, kept in the plugin's settings. Replaces the terminal's authorize.py for TikTok."""
from __future__ import annotations

import secrets
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request

from aurora import sys_config

from .core import auth, cfg, log, me

router = APIRouter()
STATE_S = 600                                      # a sign-in left open longer is started again
_states: dict[str, dict] = {}
PROVIDERS = {
    "tiktok": {
        "authorize": "https://www.tiktok.com/v2/auth/authorize/",
        "token": "https://open.tiktokapis.com/v2/oauth/token/",
        # what the plugin uses: the account (creator_info) and Direct Post — not video.upload (the inbox), which the
        # review would want shown
        "scope": "user.info.basic,video.publish",
        "keys": ("AURORA_TIKTOK_CLIENT_KEY", "AURORA_TIKTOK_CLIENT_SECRET", "AURORA_TIKTOK_REDIRECT_URI"),
        "save": "AURORA_TIKTOK_REFRESH_TOKEN",
    },
}


def _base() -> sys_config.Config:
    c = cfg.now()
    return c.base or c


def _own(user: str | None) -> bool:
    """Whether the settings are this user's own .env (multi-user, after U3) or the machine's."""
    from aurora import sys_users_layout
    return bool(user) and bool(sys_users_layout.migrated(_base()))


def _keys(spec: dict, user: str | None) -> tuple[str, ...]:
    """The card's values as the .env holds them NOW — saved a moment ago, before any restart (as authorize.py read
    them): the user's own (the TikTok app and account are each person's, scope user), else the machine's."""
    from aurora import sys_user_config
    now = sys_user_config.for_user(_base(), user) if _own(user) else sys_config.load(_base().env_file, check_root=False)
    return tuple(str(now.values.get(k) or "").strip() for k in spec["keys"])


def _spec(provider: str) -> dict:
    spec = PROVIDERS.get(provider)
    if not spec:
        raise HTTPException(status_code=404, detail="no such provider")
    return spec


@router.post("/v1/aurora/oauth/{provider}/start", dependencies=[Depends(auth)])
def start(provider: str) -> dict:
    spec = _spec(provider)
    key, _secret, redirect = _keys(spec, me())
    if not (key and _secret and redirect):
        raise HTTPException(status_code=409, detail="first the client key, the client secret and the redirect URI in the card")
    now = time.time()
    for s in [s for s, v in _states.items() if now - v["at"] > STATE_S]:
        _states.pop(s, None)
    state = f"{provider}.{secrets.token_urlsafe(24)}"
    _states[state] = {"provider": provider, "at": now, "user": me()}
    url = spec["authorize"] + "?" + urllib.parse.urlencode({"client_key": key, "scope": spec["scope"],
                                                            "response_type": "code", "redirect_uri": redirect, "state": state})
    return {"url": url}


@router.post("/v1/aurora/oauth/finish", dependencies=[Depends(auth)])
async def finish(request: Request) -> dict:
    """{"code", "state"} as the provider sent them back: the state must be one this API gave to this same person,
    unused, recent."""
    import httpx
    body = await request.json()
    state, code = str(body.get("state", "")), str(body.get("code", "")).strip()
    got = _states.get(state)
    if got and got["user"] != me():                    # another person's sign-in: not theirs to finish, left for its own
        raise HTTPException(status_code=403, detail="this sign-in was started by another person")
    _states.pop(state, None)
    if not got or time.time() - got["at"] > STATE_S:
        raise HTTPException(status_code=409, detail="this sign-in is not one Aurora started, or it is too old: start it again")
    if not code or len(code) > 2000:
        raise HTTPException(status_code=400, detail="no code from the provider")
    spec = PROVIDERS[got["provider"]]
    key, secret, redirect = _keys(spec, me())
    try:
        r = httpx.post(spec["token"], timeout=30, data={"client_key": key, "client_secret": secret, "code": code,
                                                        "grant_type": "authorization_code", "redirect_uri": redirect}).json()
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"{got['provider']} does not answer: {str(e)[:200]}") from None
    if not r.get("refresh_token"):
        raise HTTPException(status_code=502, detail=f"{got['provider']}: {r.get('error_description') or r.get('error') or 'no token'}")
    if _own(me()):
        from aurora import sys_user_config
        sys_user_config.write(_base(), me(), {spec["save"]: r["refresh_token"]})
    else:
        sys_config.write_env(_base().env_file, {spec["save"]: r["refresh_token"]})
    log.info("audit: %s connected from the WebUI by %s (scopes: %s)", got["provider"], me(), r.get("scope"))
    return {"provider": got["provider"], "scope": r.get("scope", ""), "days": int(r.get("refresh_expires_in", 0)) // 86400}
