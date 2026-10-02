# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Social pages: platforms, drafts, publishing (through approvals)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, pipeline, plugin_host

router = APIRouter()


# ---- social -------------------------------------------------------------------------------------
@router.get("/v1/aurora/social", dependencies=[Depends(auth)])
def social() -> dict:
    from aurora.kno_social import platforms
    reports = reflections(type="social_report", n=1)
    return {"platforms": platforms(plugin_host()), "last_report": reports[0] if reports else None}


@router.post("/v1/aurora/social/draft", dependencies=[Depends(auth)])
async def social_draft(request: Request) -> dict:
    """{"text": content to share, "plugins": [optional subset]} -> a draft per connected platform."""
    from aurora.kno_social import draft, platforms
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="nothing to share")
    found = await asyncio.to_thread(lambda: platforms(plugin_host()))    # the host runs its own event loop
    targets = [t for t in found if t["available"] and t["publish"]
               and (not body.get("plugins") or t["plugin"] in body["plugins"])]
    if not targets:
        raise HTTPException(status_code=409, detail="no social platform connected (tokens in Settings)")
    drafts = await asyncio.to_thread(draft, pipeline().llm, text, targets, cfg)
    return {"drafts": [{"plugin": t["plugin"], "label": t["label"], "max_chars": t["max_chars"], "text": drafts[t["plugin"]]}
                       for t in targets]}


@router.post("/v1/aurora/social/publish", dependencies=[Depends(auth)])
async def social_publish(request: Request) -> dict:
    """The owner clicked "Publish" on a draft he read: that click is the confirmation (recorded as an
    approval, executed at once). The AI disclosure is added if the text lost it while editing."""
    from aurora import sys_disclosure, txt_lang
    from aurora.kno_social import platforms
    from aurora.sys_approvals import Approvals
    body = await request.json()
    plugin, text = str(body.get("plugin", "")), str(body.get("text", "")).strip()
    found = await asyncio.to_thread(lambda: platforms(plugin_host()))
    target = next((t for t in found if t["plugin"] == plugin and t["available"]), None)
    if target is None or not text:
        raise HTTPException(status_code=409, detail="platform not connected or empty text")
    text = sys_disclosure.mark_text(text, txt_lang.detect(text), cfg)
    args = {target["publish"]["field"]: text}
    req = Approvals(cfg).request("tool_call", "external", f"{plugin}.{target['publish']['tool']}",
                                 "post shared by the owner from the chat", {"plugin": plugin, "tool": target["publish"]["tool"],
                                                                            "arguments": args},
                                 {"plugin": plugin, "tool": target["publish"]["tool"], "arguments": args})
    return decide(req["id"], "approve")


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .activity import reflections  # noqa: E402
from .agents import decide  # noqa: E402
