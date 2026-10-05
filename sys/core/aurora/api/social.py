# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Social pages: platforms, drafts, publishing (through approvals)."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, pipeline, plugin_host

router = APIRouter()
PICTURE = re.compile(r"[\w.-]{1,120}\.(?:png|jpe?g|webp)")


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
    return {"drafts": [{"plugin": t["plugin"], "label": t["label"], "max_chars": t["max_chars"], "text": drafts[t["plugin"]],
                        "photo": bool(t.get("photo"))} for t in targets]}


@router.post("/v1/aurora/social/check", dependencies=[Depends(auth)])
async def social_check(request: Request) -> dict:
    """{"text"} -> what a post would give away (names of private people, places, contacts, ids) and the text with the
    sure ones replaced (owner, 2026-10-05). Read by the LOCAL model only: the text may hold private data."""
    from aurora import sec_privacy, txt_lang
    text = str((await request.json()).get("text", ""))[:8000]
    lang = txt_lang.detect(text) if text.strip() else "it"
    found = await asyncio.to_thread(sec_privacy.findings, text, cfg, lang, pipeline().llm)
    return {"findings": found, "proposed": sec_privacy.propose(text, [f for f in found if f["sure"]])}


@router.post("/v1/aurora/social/publish", dependencies=[Depends(auth)])
async def social_publish(request: Request) -> dict:
    """The owner clicked "Publish" on a draft he read: that click is the confirmation (recorded as an
    approval, executed at once). The AI disclosure is added if the text lost it while editing."""
    from aurora import sys_disclosure, txt_lang
    from aurora.kno_social import platforms
    from aurora.sys_approvals import Approvals
    body = await request.json()
    plugin, text = str(body.get("plugin", "")), str(body.get("text", "")).strip()
    picture = str(body.get("picture") or "")
    if picture and not PICTURE.fullmatch(picture):        # one of Aurora's pictures, by its file name only
        raise HTTPException(status_code=400, detail="picture: a file name of Aurora's pictures")
    found = await asyncio.to_thread(lambda: platforms(plugin_host()))
    target = next((t for t in found if t["plugin"] == plugin and t["available"]), None)
    if target is None or not text:
        raise HTTPException(status_code=409, detail="platform not connected or empty text")
    text = sys_disclosure.mark_text(text, txt_lang.detect(text), cfg)
    how = target["photo"] if picture and target.get("photo") else target["publish"]
    args = {how["field"]: text, **({how["picture"]: picture} if how is target.get("photo") else {})}
    req = Approvals(cfg).request("tool_call", "external", f"{plugin}.{how['tool']}",
                                 "post shared by the owner from the chat", {"plugin": plugin, "tool": how["tool"],
                                                                            "arguments": args},
                                 {"plugin": plugin, "tool": how["tool"], "arguments": args})
    return decide(req["id"], "approve")


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .activity import reflections  # noqa: E402
from .agents import decide  # noqa: E402
