# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Autonomy panel (sys_autonomy): areas and levels, profiles, the daily line, the statistics, who may choose."""
from __future__ import annotations

import asyncio

from aurora import sys_config, sys_log
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import BASE, _admin, auth, cfg, log, user_of
from .users import admin_only

router = APIRouter()


def _view(user: str | None) -> dict:
    from aurora import sys_autonomy, sys_ethics, sys_user_config
    ucfg = sys_user_config.for_user(BASE, user) if user else cfg
    lv = sys_autonomy.levels(ucfg)
    admin = user is None or user == _admin()
    may = admin or sys_autonomy.policy(cfg).get("may_choose", {}).get(user, False)
    areas = [{"id": a, "scope": scope, "levels": sorted(lvl), "level": lv[a],
              "mine": admin if scope == "machine" else may, "external": a in sys_autonomy.EXTERNAL}
             for a, (scope, lvl) in sys_autonomy.AREAS.items()]
    return {"user": user, "admin": admin, "may_choose": may, "areas": areas, "profile": sys_autonomy.profile_of(lv),
            "profiles": sys_autonomy.PROFILES, "exempt": sys_ethics.exempt(cfg)}


@router.get("/v1/aurora/autonomy", dependencies=[Depends(auth)])
async def autonomy(request: Request, days: int = 14) -> dict:
    from aurora import sys_autonomy
    from aurora.sys_approvals import Approvals, auto_tools
    user = user_of(request)
    out = _view(user)
    out["days"] = sys_autonomy.days(cfg, max(1, min(days, 90)), None if out["admin"] else user)
    if out["admin"]:
        out["stats"] = await asyncio.to_thread(sys_autonomy.statistics, cfg, Approvals(cfg)._load(), auto_tools(cfg))
        from aurora.sys_users import Users
        try:
            users = [u["name"] for u in Users(BASE.base or BASE).list() if u["role"] != "admin"]
        except Exception:                                 # noqa: BLE001 — single-user: no users store
            users = []
        out["users"] = [{"name": u, **_view(u)} for u in users]
    return out


@router.put("/v1/aurora/autonomy", dependencies=[Depends(auth)])
async def autonomy_set(request: Request) -> dict:
    """{"profile": "careful|balanced|free"} or {"levels": {area: n}}, optional "user" (the admin choosing for a user).
    The machine's areas: the admin only; a user's own: the user if the admin lets them, else the admin."""
    from aurora import sys_autonomy, sys_user_config
    body = await request.json()
    me, admin = user_of(request), _admin()
    is_admin = me is None or me == admin
    target = str(body.get("user") or me or "") or None
    if target != me and not is_admin:
        raise HTTPException(status_code=403, detail="only the admin chooses for another user")
    choice = dict(sys_autonomy.PROFILES.get(str(body.get("profile")), {})) if body.get("profile") else {}
    choice.update({str(k): int(v) for k, v in (body.get("levels") or {}).items()})
    if not choice:
        raise HTTPException(status_code=422, detail="a profile or levels")
    if target and target != admin:                       # a user: only their own areas
        choice = {a: n for a, n in choice.items() if sys_autonomy.AREAS.get(a, ("machine",))[0] == "user"}
        if not is_admin and not sys_autonomy.policy(cfg).get("may_choose", {}).get(target, False):
            raise HTTPException(status_code=403, detail="the admin chooses your autonomy")
    elif not is_admin:
        raise HTTPException(status_code=403, detail="only the admin")
    try:
        machine, user = sys_autonomy.changes(choice)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if machine:
        sys_config.write_env(sys_config.env_file_path(), machine)
    if user:
        from aurora import sys_users_layout
        if target and sys_users_layout.migrated(BASE.base or BASE):   # the user's own usr/<name>/.env
            sys_user_config.write(BASE.base or BASE, target, user)
        else:
            sys_config.write_env(sys_config.env_file_path(), user)
    specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    restart = sorted({svc for k in {**machine, **user} for svc in specs[k]["services"]})
    log.info("audit: autonomy of %s set by %s: %s", target or "the machine", me or "admin",
             ", ".join(f"{a}={n}" for a, n in choice.items()))
    sys_log.trace("api", "autonomy.change", {"user": target, "levels": choice})
    return {**_view(target if target != admin else None), "restart": restart}


@router.put("/v1/aurora/autonomy/may-choose", dependencies=[Depends(admin_only)])
async def autonomy_may_choose(request: Request) -> dict:
    """{"user", "allowed"}: whether a user chooses their own autonomy."""
    from aurora import sys_autonomy
    body = await request.json()
    user = str(body.get("user", ""))
    if not user:
        raise HTTPException(status_code=422, detail="user")
    p = sys_autonomy.set_may_choose(cfg, user, bool(body.get("allowed")))
    log.info("audit: %s may%s choose their autonomy", user, "" if body.get("allowed") else " not")
    return p
