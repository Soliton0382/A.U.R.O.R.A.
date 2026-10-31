# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💶 The expenses page (fin_store): a month's totals, movements, fixed items, budgets and saving goal, each user's own
(owner, 1 Nov: «la possibilità di aggiungere le spese… entrate stipendio e uscite fisse, e grafici… obiettivo di
risparmio mensile»). The chat goes on through the expenses plugin, on the same file."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log

router = APIRouter()


def _do(fn, *a):
    try:
        return fn(*a)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such item") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.get("/v1/aurora/expenses", dependencies=[Depends(auth)])
def money_view(month: str = "") -> dict:
    from aurora import fin_store
    return _do(fin_store.view, cfg, month)


@router.post("/v1/aurora/expenses/moves", dependencies=[Depends(auth)])
async def money_add(request: Request) -> dict:
    """{"kind": "out"|"in", "amount", "what", "category", "day", "monthly": bool}: a movement, or a fixed one of every
    month from that day on."""
    from aurora import fin_store
    b = await request.json()
    kind = str(b.get("kind", "out"))
    if b.get("monthly"):
        when = _do(fin_store.day, str(b.get("day", "")))
        out = _do(fin_store.fixed_add, cfg, kind, b.get("amount"), str(b.get("what", "")), str(b.get("category", "")),
                  int(when[8:]), when[:7])
    else:
        out = _do(fin_store.add, cfg, kind, b.get("amount"), str(b.get("what", "")), str(b.get("category", "")),
                  str(b.get("day", "")))
    log.info("audit: expenses: a %s %s added from the page", "fixed" if b.get("monthly") else "movement", kind)
    return out


@router.delete("/v1/aurora/expenses/moves/{kind}/{mid}", dependencies=[Depends(auth)])
def money_remove(kind: str, mid: int) -> dict:
    from aurora import fin_store
    _do(fin_store.remove, cfg, kind, mid)
    return {"removed": mid}


@router.delete("/v1/aurora/expenses/fixed/{fid}", dependencies=[Depends(auth)])
def money_fixed_stop(fid: int) -> dict:
    from aurora import fin_store
    _do(fin_store.fixed_stop, cfg, fid)
    return {"stopped": fid}


@router.put("/v1/aurora/expenses/goal", dependencies=[Depends(auth)])
async def money_goal(request: Request) -> dict:
    from aurora import fin_store
    return {"goal": _do(fin_store.set_goal, cfg, (await request.json()).get("amount", 0))}


@router.put("/v1/aurora/expenses/budget", dependencies=[Depends(auth)])
async def money_budget(request: Request) -> dict:
    from aurora import fin_store
    b = await request.json()
    return {"category": b.get("category"), "budget": _do(fin_store.set_budget, cfg, str(b.get("category", "")), b.get("amount", 0))}
