# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Social pages: platforms, drafts, publishing (through approvals)."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, pipeline, plugin_host

router = APIRouter()
PICTURE = re.compile(r"[\w.-]{1,120}\.(?:png|jpe?g|webp)")
VIDEO = re.compile(r"[\w.-]{1,120}\.mp4")
STAMP = re.compile(r"\d{8}-\d{6}")


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


def _before_publishing(text: str) -> dict:
    """What the owner should see before a post goes out (owner, 2026-10-08): the private data the check is sure of
    (sec_privacy, the local model) and a repeat of a post of the last 7 days (sys_social_guard). Empty: publish."""
    from aurora import sec_privacy, sys_social_guard, txt_lang
    private = [f for f in sec_privacy.findings(text, cfg, txt_lang.detect(text), pipeline().llm) if f["sure"]]
    out = {}
    if private:
        out["privacy"] = [{"value": f["value"], "kind": f["kind"], "replacement": f.get("replacement", "")} for f in private]
    if (again := sys_social_guard.check(cfg, text)):
        out["repeat"] = again.removeprefix("REFUSED: ").split(". Choose")[0]
    return out


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
    video = str(body.get("video") or "")
    if video and not VIDEO.fullmatch(video):              # one of Aurora's videos (kno_story), by its file name only
        raise HTTPException(status_code=400, detail="video: a file name of Aurora's videos")
    found = await asyncio.to_thread(lambda: platforms(plugin_host()))
    target = next((t for t in found if t["plugin"] == plugin and t["available"]), None)
    if target is None or not text:
        raise HTTPException(status_code=409, detail="platform not connected or empty text")
    if video and not target.get("video"):
        raise HTTPException(status_code=409, detail=f"{plugin} does not publish videos")
    text = sys_disclosure.mark_text(text, txt_lang.detect(text), cfg)
    if video:
        how = target["video"]
        args = {how["field"]: text, how["video"]: video}
        shape = str(body.get("format") or "")             # post / reel / story (Facebook), when the platform has them
        if how.get("format") and shape:
            if shape not in how.get("formats", []):
                raise HTTPException(status_code=400, detail=f"format: one of {how.get('formats')}")
            args[how["format"]] = shape
    else:
        how = target["photo"] if picture and target.get("photo") else target["publish"]
        if not how:
            raise HTTPException(status_code=409, detail=f"{plugin} publishes only pictures or videos")
        args = {how["field"]: text, **({how["picture"]: picture} if how is target.get("photo") else {})}
    if not body.get("confirmed"):                         # 8 Oct: the owner's name went out from here, unchecked
        warn = await asyncio.to_thread(_before_publishing, text)
        if warn:
            return {"confirm": warn}
    req = Approvals(cfg).request("tool_call", "external", f"{plugin}.{how['tool']}",
                                 "post shared by the owner from the chat", {"plugin": plugin, "tool": how["tool"],
                                                                            "arguments": args},
                                 {"plugin": plugin, "tool": how["tool"], "arguments": args})
    return decide(req["id"], "approve")


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .activity import reflections  # noqa: E402
from .agents import decide  # noqa: E402


@router.get("/v1/aurora/social/stories", dependencies=[Depends(auth)])
def social_stories() -> dict:
    """The narrated videos made (newest first) and the platforms that publish videos."""
    from aurora import kno_story
    from aurora.kno_social import platforms
    return {"stories": kno_story.stories(cfg),
            "platforms": [{"plugin": t["plugin"], "label": t["label"], "available": t["available"], "max_chars": t["max_chars"],
                           "formats": t["video"].get("formats", []),
                           "format": str(cfg.values.get(t["video"].get("default", ""), "") or (t["video"].get("formats") or [""])[0])}
                          for t in platforms(plugin_host()) if t.get("video")]}


@router.get("/v1/aurora/social/stories/{stamp}/video", dependencies=[Depends(auth)])
def social_story_video(stamp: str):
    from fastapi.responses import FileResponse
    from aurora import kno_story
    s = next((x for x in kno_story.stories(cfg, 200) if x["stamp"] == stamp), None) if STAMP.fullmatch(stamp) else None
    if s is None:
        raise HTTPException(status_code=404, detail="no such video")
    return FileResponse(cfg.path("AURORA_IMAGE_DIR") / "stories" / stamp / s["video"], media_type="video/mp4")


@router.post("/v1/aurora/social/story", dependencies=[Depends(auth)])
async def social_story(request: Request) -> dict:
    """{"topic"}: a narrated video from the vault, made on this machine (kno_story); the run's events say each step and
    end with the video's address. Published only by the owner, like every post."""
    from .core import start_run
    topic = str((await request.json()).get("topic", "")).strip()
    if not 3 <= len(topic) <= 300:
        raise HTTPException(status_code=400, detail="a topic of 3-300 characters")

    def job(q, emit, run_id):
        from aurora import kno_story, sys_uploads
        out = kno_story.make(pipeline(), cfg, q, emit)
        data = Path(out["video"]).read_bytes()
        url = sys_uploads.public(sys_uploads.save(cfg, run_id, "aurora-story.mp4", "video/mp4", data, role="assistant"))["url"]
        emit("story.ready", {"url": url, "post": out["post"], "folder": out["folder"], "length_s": out["length_s"]})
        return None
    return {"run_id": start_run(topic, origin="story", job=job)["id"]}
