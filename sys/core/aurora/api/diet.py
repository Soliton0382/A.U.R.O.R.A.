# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The diet followed day by day (hlt_diet, roadmap 55): «Elabora documenti», the meal proposed with its alternatives,
what was eaten, and the reminders at meal times (a notification, a message in the chat) — each user's own, sealed."""
from __future__ import annotations

import time
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, in_thread, log, me, note

router = APIRouter()


def _today() -> date:
    return datetime.now().astimezone().date()


def _times() -> dict[str, str]:
    from aurora import hlt_diet
    return hlt_diet.parse_times(str(cfg["AURORA_DIET_TIMES"]))


def _day_view(p: dict, day: date) -> list[dict]:
    from aurora import hlt_diet
    rows = hlt_diet.choices(cfg)
    meals = [m for m in hlt_diet.MEALS if any(o["meal"] == m for o in p["options"])]
    return [hlt_diet.suggest(p, rows, day, m) for m in meals]


@router.get("/v1/aurora/diet", dependencies=[Depends(auth)])
def diet(day: str | None = None) -> dict:
    """The plan (or null), whether documents changed since it was read, the day's meals with their proposals, the
    week's groups against the frequencies, and the reminders' settings."""
    from aurora import hlt_diet, hlt_store, sys_seal
    sys_seal._key(cfg, cfg.user, "health")
    p = hlt_diet.plan(cfg)
    docs = [i["id"] for i in hlt_store.items(cfg, "diet")]
    out = {"plan": p, "documents": len(docs), "reminders": bool(cfg["AURORA_DIET_REMINDERS"]), "times": _times()}
    if not p:
        return out
    d = date.fromisoformat(day) if day else _today()
    out["stale"] = sorted(docs) != sorted(p.get("documents", []))
    out["day"] = d.isoformat()
    out["meals"] = _day_view(p, d)
    out["week"] = hlt_diet.week_counts(hlt_diet.choices(cfg), d)
    return out


@router.post("/v1/aurora/diet/process", dependencies=[Depends(auth)])
async def diet_process() -> dict:
    """«Elabora documenti»: the plan read again from the diet documents; the rules summarised by the LOCAL model."""
    from aurora import hlt_diet
    from .core import pipeline
    t0 = time.time()
    try:
        p = await in_thread(hlt_diet.process, cfg, pipeline().llm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: %s processed the diet plan (%d options, %d frequencies, %.1f s)", me(), len(p["options"]),
             len(p["frequencies"]), time.time() - t0)
    return {"plan": p, "seconds": round(time.time() - t0, 1)}


@router.post("/v1/aurora/diet/choice", dependencies=[Depends(auth)])
async def diet_choice(request: Request) -> dict:
    """{"day", "meal", "option"? , "free"?, "text"?}: what was eaten; the proposals re-weighed at once."""
    from aurora import hlt_diet
    b = await request.json()
    try:
        row = hlt_diet.choose(cfg, str(b.get("day") or _today().isoformat()), str(b.get("meal", "")),
                              b.get("option") or None, str(b.get("text") or ""), bool(b.get("free")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return {"choice": row}


@router.delete("/v1/aurora/diet/choice/{cid}", dependencies=[Depends(auth)])
def diet_unchoose(cid: str) -> dict:
    from aurora import hlt_diet
    if not hlt_diet.unchoose(cfg, cid):
        raise HTTPException(status_code=404, detail="no such choice")
    return {"deleted": cid}


@router.get("/v1/aurora/diet/pending", dependencies=[Depends(auth)])
def diet_pending() -> dict:
    """The meals reminded today and not answered yet (the chat shows them when it opens)."""
    from aurora import hlt_diet
    p = hlt_diet.plan(cfg)
    if not p or not cfg["AURORA_DIET_REMINDERS"]:
        return {"meals": []}
    told = _reminded().get(_today().isoformat(), {})
    meals = [s for s in _day_view(p, _today()) if s["meal"] in told and not s["chosen"]
             and time.time() - told[s["meal"]] < 3 * 3600]
    return {"meals": meals}


# ---- the reminders --------------------------------------------------------------------------------------------------
def _reminded() -> dict:
    from aurora import hlt_diet
    return hlt_diet._read(cfg, "reminded", {})


def remind_now(now: datetime | None = None) -> str | None:
    """The meal of this minute for the current user, told once a day: a notification and a chat message."""
    from aurora import hlt_diet
    if not cfg["AURORA_DIET_REMINDERS"]:
        return None
    p = hlt_diet.plan(cfg)
    now = now or datetime.now().astimezone()
    meal = hlt_diet.meal_now(_times(), now) if p else None
    if not meal:
        return None
    day = now.date().isoformat()
    told = _reminded()
    if meal in told.get(day, {}):
        return None
    s = hlt_diet.suggest(p, hlt_diet.choices(cfg), now.date(), meal)
    told = {day: {**told.get(day, {}), meal: time.time()}}             # only today's: the file stays small
    hlt_diet._write(cfg, "reminded", told)
    if s["chosen"] or not s["suggested"]:
        return None
    note("diet", "diet.meal", {"text": hlt_diet.reminder_text(s), "meal": meal, "day": day})
    return meal


def watch_diet(every_s: int = 60) -> None:
    """Each minute, for each user with the reminders on: the meal whose time it is (owner, 2026-10-07)."""
    from aurora import sys_context
    from .core import _admin
    from .users import _users
    while True:
        time.sleep(every_s)
        try:
            names = [u["name"] for u in _users().list()] if _admin() else [None]
        except Exception:  # noqa: BLE001 — the watcher never dies
            continue
        for name in names:
            try:
                with sys_context.acting_as(name):
                    remind_now()
            except Exception as e:  # noqa: BLE001 — one user's problem never stops the others'
                log.warning("diet reminder: %s", type(e).__name__)
