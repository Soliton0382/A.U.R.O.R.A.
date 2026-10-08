# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Which model does each step (mdl_router): providers, roles, model lists, cloud statistics."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log

from .users import admin_only  # noqa: E402

router = APIRouter()


# ---- models: which model does each step (mdl_router) ----------------------------------------------------------

@router.get("/v1/aurora/models", dependencies=[Depends(admin_only)])
def models_overview() -> dict:
    from aurora import mdl_router, sys_ethics
    a = mdl_router.assignments(cfg)
    return {"exempt": sys_ethics.exempt(cfg), "mask": True, "backend": "cloud" if mdl_router.cloud_only(cfg) else "local",
            "mask_words": cfg["AURORA_CLOUD_MASK_WORDS"],
            "providers": [{"id": k, "label": mdl_router.label(k, cfg), "kind": v["kind"], "key": v.get("key"),
                           "configured": mdl_router.configured(k, cfg)}
                          for k, v in mdl_router.PROVIDERS.items()],
            "roles": [{"id": r, "it": it, "en": en, "sees": sees, **a[r]} for r, (it, en, sees) in mdl_router.ROLES.items()]}


@router.get("/v1/aurora/models/media", dependencies=[Depends(admin_only)])
def models_media() -> dict:
    """Pictures, edits and videos: who makes them (mdl_media) and who could."""
    from aurora import mdl_media, sys_ethics
    return {"assigned": mdl_media.assignments(cfg), "choices": mdl_media.choices(cfg), "exempt": sys_ethics.exempt(cfg)}


@router.put("/v1/aurora/models/media", dependencies=[Depends(admin_only)])
async def models_media_set(request: Request) -> dict:
    from aurora import mdl_media
    try:
        out = mdl_media.set_assignments(cfg, await request.json())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: media assignments: %s", ", ".join(f"{k}={v['provider']}" for k, v in out.items()))
    return out


@router.get("/v1/aurora/models/limits", dependencies=[Depends(admin_only)])
def models_limits() -> dict:
    """Per provider: the free tier to stay in (on/off and its numbers) and today's use."""
    from aurora import mdl_budget, mdl_router
    d = mdl_budget.today(cfg)
    keys = {p: mdl_router.configured(p, cfg) for p in mdl_router.PROVIDERS}
    return {"limits": mdl_budget.limits(cfg), "configured": keys,
            "today": {p: {"calls": d.get("calls", {}).get(p, 0), "tokens": d.get("tokens", {}).get(p, 0),
                          "stopped": mdl_budget.free_reason(cfg, p, d)} for p in mdl_budget.FREE_PRESETS}}


@router.put("/v1/aurora/models/limits", dependencies=[Depends(admin_only)])
async def models_limits_set(request: Request) -> dict:
    from aurora import mdl_budget
    try:
        out = mdl_budget.set_limits(cfg, await request.json())
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: free-tier limits: %s", ", ".join(p for p, v in out.items() if v["free"]) or "none")
    return out


@router.put("/v1/aurora/models/roles", dependencies=[Depends(admin_only)])
async def models_roles(request: Request) -> dict:
    from aurora import mdl_router
    try:
        out = mdl_router.set_assignments(cfg, await request.json())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log.info("audit: model assignments changed: %s", ", ".join(f"{k}={v['provider']}:{v['model']}" for k, v in out.items()
                                                                  if v["provider"] != "local"))
    return out


# ---- the whole: local, mixed, cloud with privacy, all cloud (mdl_modes) ---------------------------------------------

def _mode_error(e) -> HTTPException:
    return HTTPException(status_code=409, detail={"message": str(e), "need": e.need, "command": e.command})


@router.get("/v1/aurora/models/modes", dependencies=[Depends(admin_only)])
async def models_modes() -> dict:
    from aurora import mdl_modes
    return await asyncio.to_thread(mdl_modes.check, cfg)


@router.post("/v1/aurora/models/mode", dependencies=[Depends(admin_only)])
async def models_mode(request: Request) -> dict:
    """{"mode", "provider", "model"}: every role to the mode; 409 with the shell command when the owner must act."""
    from aurora import mdl_modes
    body = await request.json()
    try:
        out = await asyncio.to_thread(mdl_modes.apply, cfg, str(body.get("mode", "")), str(body.get("provider") or ""),
                                      str(body.get("model") or ""))
    except mdl_modes.ModeError as e:
        raise _mode_error(e) from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: models mode %s (%s %s)", out["mode"], body.get("provider") or "", body.get("model") or "")
    return out


@router.post("/v1/aurora/models/reasoner", dependencies=[Depends(admin_only)])
async def models_reasoner(request: Request) -> dict:
    """{"on": bool}: the local reasoner switched on (rule 6: not during a GPU job) or off (the GPU free)."""
    from aurora import mdl_modes
    on = (await request.json()).get("on") is True
    try:
        out = await asyncio.to_thread(mdl_modes.reasoner, cfg, on)
    except mdl_modes.ModeError as e:
        raise _mode_error(e) from None
    log.info("audit: local reasoner switched %s", "on" if on else "off")
    return out


@router.get("/v1/aurora/models/{provider}/list", dependencies=[Depends(admin_only)])
async def models_list(provider: str) -> dict:
    from aurora import mdl_router
    if provider not in mdl_router.PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    try:
        return {"provider": provider, "models": await asyncio.to_thread(mdl_router.list_models, provider, cfg)}
    except Exception as e:                               # a wrong key, a provider down: said, not hidden
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {str(e)[:300]}")


@router.get("/v1/aurora/models/stats", dependencies=[Depends(admin_only)])
async def models_stats(days: float = 7) -> dict:
    from aurora import mdl_budget, mdl_router
    out = await asyncio.to_thread(mdl_router.stats, cfg, max(1.0, min(days, 90)))
    return {**out, "today": mdl_budget.today(cfg), "daily_cap": cfg["AURORA_CLOUD_DAILY_TOKENS"],
            "paid": sorted(mdl_budget.PAID)}
