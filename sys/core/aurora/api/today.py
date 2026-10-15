# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""☀️ Oggi's own tiles (owner, 16 Oct: «le novità della ricerca… nella sezione Oggi, che potrebbe riportare in
scorrimento anche le principali news della giornata aggiornate magari ogni 3 ore»): the day's main headlines from the
news plugin, read again every 3 hours, and the latest report of the research routines (made from the «research»
template, or any routine marked «today»), with its PDF."""
from __future__ import annotations

import time

from aurora.txt_headlines import headlines, key
from fastapi import APIRouter, Depends

from .core import auth, cfg, in_thread, plugin_host

router = APIRouter()
EVERY_S = 3 * 3600
TOPICS = ("italia", "mondo")
_news: dict = {"at": 0.0, "items": []}


def _read_news() -> list[dict]:
    host, out, seen = plugin_host(), [], set()
    for topic in TOPICS:
        r = host.call("news", "news_headlines", {"topic": topic, "hours": 12, "limit": 8})
        for h in headlines(str(r.get("text", ""))) if r.get("ok") else []:
            k = key(h["title"])
            if k not in seen:
                seen.add(k)
                out.append({**h, "topic": topic})
    return out


@router.get("/v1/aurora/today/news", dependencies=[Depends(auth)])
async def today_news() -> dict:
    """The day's main headlines, at most 3 hours old; empty when the news plugin is not on."""
    if time.time() - _news["at"] > EVERY_S or not _news["items"]:
        try:
            items = await in_thread(_read_news)          # the plugins in a thread, never in the event loop (C334)
        except Exception:                                # noqa: BLE001 — the tile stays out, the page stays whole
            items = []
        if items:
            _news.update(at=time.time(), items=items)
    return {"items": _news["items"], "at": _news["at"] or None, "every_s": EVERY_S}


@router.get("/v1/aurora/today/research", dependencies=[Depends(auth)])
def today_research() -> dict:
    """The last report of each research routine, newest first: its title, the first lines, its PDF."""
    from aurora import sys_routines
    out = []
    for r in sys_routines.all_routines(cfg):
        if not (r.get("today") or r.get("by") == "template:research") or not r.get("last_text"):
            continue
        pdf = next((f for f in r.get("last_files") or [] if f.get("mime") == "application/pdf"), None)
        out.append({"id": r["id"], "title": r.get("title", ""), "at": r.get("last_run"), "text": str(r["last_text"])[:1200],
                    "pdf": pdf})
    return {"items": sorted(out, key=lambda x: -(x["at"] or 0))[:2]}
