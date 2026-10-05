# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Synapses (kno_synapse): the links between passages of different domains — how many, grown at night, faded daily."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log, pipeline
from .users import admin_only

router = APIRouter()
_growing = threading.Event()


@router.get("/v1/aurora/synapses", dependencies=[Depends(auth)])
def synapses() -> dict:
    from aurora import kno_synapse
    return {**kno_synapse.stats(cfg), "growing": _growing.is_set()}


@router.post("/v1/aurora/synapses/grow", dependencies=[Depends(admin_only)])
def synapses_grow(limit: int = 0) -> dict:
    """aurora-rem's nightly round (or the admin): new links for the next passages, in the background; then the fade."""
    from aurora import kno_synapse
    if _growing.is_set():
        return {"started": False, "reason": "already growing"}
    n = limit or int(cfg["AURORA_SYNAPSE_PER_NIGHT"])
    s = pipeline().search

    def work():
        _growing.set()
        try:
            out = kno_synapse.grow(cfg, s.reader, s.index, s.embedder, n)
            faded = kno_synapse.fade(cfg)
            log.info("synapses: %d passages looked at, %d links made in %.0f s; faded %d, asleep %d",
                     out["seen"], out["made"], out["seconds"], faded["weaker"], faded["gone"])
            _level2_if_due()
        except Exception as e:                            # noqa: BLE001 — a bad round never stops the next
            log.warning("synapses: growth failed: %s", e)
        finally:
            _growing.clear()
    threading.Thread(target=work, name="synapses", daemon=True).start()
    return {"started": True, "passages": n}


_level2 = threading.Event()


def _level2_if_due(force: bool = False) -> bool:
    """Synapses of synapses (kno_synapse2) in the background, when enough new links have grown."""
    from aurora import kno_synapse2
    if _level2.is_set() or not (force or kno_synapse2.due(cfg)):
        return False
    p = pipeline()

    def work():
        _level2.set()
        try:
            out = kno_synapse2.round_(cfg, p.search.reader, p.search.embedder, p.llm)
            log.info("synapses level 2: %d triads looked at, %d links of level 2, %d concepts in %.0f s",
                     out["candidates"], out["made"], out["concepts"], out["seconds"])
        except Exception as e:                            # noqa: BLE001
            log.warning("synapses level 2 failed: %s", e)
        finally:
            _level2.clear()
    threading.Thread(target=work, name="synapses-l2", daemon=True).start()
    return True


@router.post("/v1/aurora/synapses/level2", dependencies=[Depends(admin_only)])
def synapses_level2(if_due: bool = False) -> dict:
    """The level-2 round now (the admin), or only when due (aurora-rem's tick)."""
    return {"started": _level2_if_due(force=not if_due)}


@router.get("/v1/aurora/synapses/list", dependencies=[Depends(auth)])
def synapses_list(active: bool = True, domain: str = "", level: int = 0, limit: int = 60, offset: int = 0) -> dict:
    """The links for the Synapses page, each with its two passages (title, domain, the start of the text)."""
    from aurora import kno_synapse
    rows = kno_synapse.listing(cfg, active, domain, level, max(1, min(limit, 300)), max(0, offset))
    sols = pipeline().search.reader.get_many({x: 0 for r in rows for x in (r["a"], r["b"])})
    side = lambda sid: ({"title": sols[sid].title, "domain": sols[sid].domain, "text": sols[sid].text[:240],
                         "source": sols[sid].source_id} if sid in sols else {"title": "", "text": "", "domain": ""})
    return {"links": [{**r, "pa": side(r["a"]), "pb": side(r["b"])} for r in rows]}


@router.put("/v1/aurora/synapses/link", dependencies=[Depends(admin_only)])
async def synapses_edit(request: Request) -> dict:
    """{"a", "b", "w"?, "pinned"?, "active"?, "delete"?}: the owner strengthens, pins, wakes or deletes a link."""
    from aurora import kno_synapse
    b = await request.json()
    out = kno_synapse.edit(cfg, str(b.get("a", "")), str(b.get("b", "")), b.get("w"), b.get("pinned"), b.get("active"),
                           bool(b.get("delete")))
    if out is None and not b.get("delete"):
        raise HTTPException(status_code=404, detail="no such link")
    log.info("audit: synapse %s ↔ %s changed by the owner: %s", b.get("a"), b.get("b"),
             {k: b[k] for k in ("w", "pinned", "active", "delete") if k in b})
    return out or {"deleted": True}


@router.get("/v1/aurora/synapses/concepts", dependencies=[Depends(auth)])
def synapses_concepts() -> list[dict]:
    from aurora import kno_synapse2
    items = kno_synapse2.list_concepts(cfg)
    sols = pipeline().search.reader.get_many({x: 0 for c in items for x in c["members"]})
    return [{**c, "passages": [{"title": sols[s].title, "domain": sols[s].domain} for s in c["members"] if s in sols]}
            for c in items]
