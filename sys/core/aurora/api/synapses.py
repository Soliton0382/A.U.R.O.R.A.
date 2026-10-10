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
            out = kno_synapse2.round_(cfg, p.search.reader, p.search.embedder, p._for("rem"))
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



# ---- deductions (kno_deduce, roadmap 77): bridges between distant fields, the owner's judgement --------------------
@router.get("/v1/aurora/deductions", dependencies=[Depends(auth)])
def deductions(limit: int = 50) -> list[dict]:
    from aurora import kno_deduce
    items = kno_deduce.listing(cfg, max(1, min(limit, 200)))
    sols = pipeline().search.reader.get_many({x: 0 for d in items for x in (d["a"], d["b"])})
    for d in items:
        for side in ("a", "b"):
            s = sols.get(d[side])
            d[f"{side}_title"] = (s.title or s.source_id) if s else ""
    return items


@router.put("/v1/aurora/deductions/{did}", dependencies=[Depends(admin_only)])
async def deduction_judge(did: int, request: Request) -> dict:
    """The owner's judgement: {"verdict": "flash" | "no" | "", "note": "…"} — the measure of roadmap 77."""
    from aurora import kno_deduce
    body = await request.json()
    try:
        out = kno_deduce.judge(cfg, did, str(body.get("verdict", "")), str(body.get("note", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="no such deduction") from None
    log.info("audit: deduction %d judged %s", did, out["verdict"] or "(cleared)")
    return out


@router.post("/v1/aurora/deductions/{did}/pdf", dependencies=[Depends(auth)])
def deduction_pdf(did: int) -> dict:
    """The deduction as a PDF among the user's documents (doc_pdf): the bridge, both sides and their sources."""
    from aurora import doc_pdf, kno_deduce
    d = next((x for x in kno_deduce.listing(cfg, 500) if x["id"] == did), None)
    if d is None:
        raise HTTPException(status_code=404, detail="no such deduction")
    p = pipeline()
    path = doc_pdf.create(f"Deduzione {did}", kno_deduce.as_markdown(p, d), "it", p.cfg)
    return {"name": path.name}


@router.post("/v1/aurora/deductions/round", dependencies=[Depends(admin_only)])
def deduction_round(n: int = 6) -> dict:
    """Look for deductions now (the night does it by itself: AURORA_DEDUCE_PER_NIGHT), as a run of its own."""
    from .core import start_run

    def job(q, emit, run_id):
        from aurora import kno_deduce
        out = kno_deduce.round_(pipeline(), cfg, emit, max(1, min(n, 30)))
        emit("rem.end", {"task": "deduce", **out})
        return None
    return {"run_id": start_run("[deduce]", origin="rem", job=job)["id"]}
