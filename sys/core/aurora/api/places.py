# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A place by its name (the owner's colleague, 9 Oct: the weather asked for coordinates — «ma che ne so»): the town
searched with Open-Meteo's geocoding (no key, the same source as the weather), its coordinates and region filled in."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from .core import auth, cfg

router = APIRouter()
GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"


def search(q: str, lang: str = "it", get=None) -> list[dict]:
    import httpx
    get = get or (lambda url, params: httpx.get(url, params=params, timeout=15))
    r = get(GEOCODING, {"name": q, "count": 8, "language": lang, "format": "json"})
    r.raise_for_status()
    out = []
    for p in r.json().get("results") or []:
        region, country = p.get("admin1") or "", p.get("country") or ""
        out.append({"name": p.get("name", ""), "lat": round(float(p["latitude"]), 4), "lon": round(float(p["longitude"]), 4),
                    "region": region, "country": country,
                    "label": ", ".join(x for x in (p.get("name", ""), p.get("admin2") or "", region, country) if x)})
    return out


@router.get("/v1/aurora/places", dependencies=[Depends(auth)])
async def places(q: str) -> dict:
    q = q.strip()
    if len(q) < 2:
        return {"places": []}
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    try:
        return {"places": await asyncio.to_thread(search, q[:80], lang)}
    except Exception as e:                               # noqa: BLE001 - offline or refused: said, never a crash
        raise HTTPException(status_code=502, detail=f"geocoding: {str(e)[:160]}") from None
