# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's advice on the agents and routines (sys_routine_advice), shown in the «Agenti e routine» page with
«Applica» and «Scarta» (owner, 2026-10-08). Each user sees and applies their own: their routines, their plugins.
Aurora looks again by herself once a day when the page is opened (or at once with «Rivedi»); new advice is told in
the notifications, so that it does not pass unnoticed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log, me, note, pipeline, plugin_host

router = APIRouter()
_reviewing: set[str] = set()


def _ready() -> set[str]:
    return {p.name for p in plugin_host().plugins(with_tools=False) if p.available}


def _system() -> list[str]:
    """What the machine does by itself outside the routines: Aurora must not propose it again."""
    out = ["ogni notte Aurora consolida le memorie, sogna, studia le domande a cui non ha saputo rispondere e si "
           "autodiagnostica (aurora-rem)", "il report giornaliero dei social (aurora-rem)"]
    if str(cfg.values.get("AURORA_BACKUP_TIME") or "").strip():
        out.append(f"il backup cifrato, ogni giorno alle {cfg.values['AURORA_BACKUP_TIME']} (aurora-backup.timer)")
    return out


def _review(who: str | None) -> None:
    from aurora import sys_routine_advice, sys_routines
    try:
        plugins = [{"name": p.name, "description": (p.manifest.get("description") or {}).get("it", ""),
                    "tools": [t["name"] for t in p.tools]} for p in plugin_host().plugins() if p.available]
        fresh = sys_routine_advice.review(pipeline().llm, sys_routines.all_routines(cfg), plugins, _system())
        added = sys_routine_advice.remember(cfg, fresh)
        log.info("routine advice: Aurora reviewed the routines: %d proposals, %d new", len(fresh), added)
        if added:
            note("routines", "routine.advice", {"text": f"💡 Ho {added} suggerimenti per i tuoi agenti e routine: "
                                                        "li trovi nella pagina 🤖 Agenti e routine, con «Applica»."})
    except Exception:                                    # noqa: BLE001 - a failed review is retried tomorrow
        log.exception("routine advice: review failed")
    finally:
        _reviewing.discard(who or "")


def _start(force: bool = False) -> bool:
    from aurora import sys_context, sys_routine_advice
    who = me() or ""
    if who in _reviewing or not (force or sys_routine_advice.due(cfg)):
        return False
    _reviewing.add(who)
    sys_context.start(_review, who, name="routine-advice")
    return True


@router.get("/v1/aurora/routines/advice", dependencies=[Depends(auth)])
def advice() -> dict:
    """{"items", "reviewed", "reviewing"}: the open advice; Aurora's daily look starts here when it is due."""
    from aurora import sys_routine_advice
    started = _start()
    return {**sys_routine_advice.current(cfg, _ready()), "reviewing": started or (me() or "") in _reviewing}


@router.post("/v1/aurora/routines/advice/review", dependencies=[Depends(auth)])
def advice_review() -> dict:
    return {"started": _start(force=True)}


@router.post("/v1/aurora/routines/advice/{aid}/{action}", dependencies=[Depends(auth)])
def advice_action(aid: str, action: str) -> dict:
    """apply (the owner's click makes the change) or dismiss (never proposed again)."""
    from aurora import sys_routine_advice
    if action not in ("apply", "dismiss"):
        raise HTTPException(status_code=404, detail="apply or dismiss")
    try:
        if action == "dismiss":
            sys_routine_advice.dismiss(cfg, aid, _ready())
            return {"dismissed": aid}
        out = sys_routine_advice.apply(cfg, aid, _ready())
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown advice") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if out.get("run"):
        from aurora import sys_routines
        from .routines import _start_routine
        r = sys_routines.get(cfg, out["run"])
        out["run_id"] = _start_routine(r) if r else None
    log.info("audit: routine advice %s applied", aid)
    return out


# ---- sets of agents and routines by use, and the owner's own as a set (sys_routine_templates) -----------------
def _lang() -> str:
    return "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"


def _is_admin() -> bool:
    from .core import _admin
    return me() == _admin()


@router.get("/v1/aurora/routines/templates", dependencies=[Depends(auth)])
def templates() -> list[dict]:
    """The sets this user may apply, each routine with its state (new, present, missing plugins)."""
    from aurora import sys_routine_templates
    return sys_routine_templates.view(cfg, _lang(), _ready(), _is_admin(), me())


@router.post("/v1/aurora/routines/templates/{pack}/apply", dependencies=[Depends(auth)])
def template_apply(pack: str) -> dict:
    from aurora import sys_routine_templates
    try:
        out = sys_routine_templates.apply(cfg, pack, _lang(), _ready(), _is_admin())
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown set") from None
    log.info("audit: routine set %s applied: %d created", pack, len(out["created"]))
    return out


@router.post("/v1/aurora/routines/templates", dependencies=[Depends(auth)])
async def template_save(request: Request) -> dict:
    """{"title", "description"}: this user's routines switched on, kept as a set."""
    from aurora import sys_routine_templates
    body = await request.json()
    title = str(body.get("title", "")).strip()[:60]
    if not title:
        raise HTTPException(status_code=422, detail="a title")
    try:
        out = sys_routine_templates.save_mine(cfg, title, me(), str(body.get("description", ""))[:300])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: routines saved as the set %s", out["id"])
    return out


@router.delete("/v1/aurora/routines/templates/{pack}", dependencies=[Depends(auth)])
def template_delete(pack: str) -> dict:
    from aurora import sys_routine_templates
    try:
        sys_routine_templates.delete_saved(cfg, pack, me(), _is_admin())
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown saved set") from None
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None
    return {"deleted": pack}
