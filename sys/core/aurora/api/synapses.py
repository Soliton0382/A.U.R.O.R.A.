# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Synapses (kno_synapse): the links between passages of different domains — how many, grown at night, faded daily."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends

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
            log.info("synapses: %d passages looked at, %d links made in %.0f s; faded %d, gone %d",
                     out["seen"], out["made"], out["seconds"], faded["weaker"], faded["gone"])
        except Exception as e:                            # noqa: BLE001 — a bad round never stops the next
            log.warning("synapses: growth failed: %s", e)
        finally:
            _growing.clear()
    threading.Thread(target=work, name="synapses", daemon=True).start()
    return {"started": True, "passages": n}
