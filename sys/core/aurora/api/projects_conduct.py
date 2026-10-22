# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧑‍🔬 The conductor of a project (prj_conduct, ROADMAP N39): the owner's words → a phase's goal → the agent → a reply."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, in_thread, log, note, pipeline, start_run

router = APIRouter()


def _check(name: str) -> None:
    from aurora import prj_conduct
    try:
        prj_conduct._project(cfg, name)
    except (ValueError, KeyError):
        raise HTTPException(status_code=404, detail="no such project") from None


@router.get("/v1/aurora/projects/{name}/conduct", dependencies=[Depends(auth)])
def conduct_list(name: str) -> dict:
    from aurora import prj_conduct
    _check(name)
    return {"items": prj_conduct.history(cfg, name), "local": prj_conduct.local(cfg, name)}


@router.post("/v1/aurora/projects/{name}/conduct", dependencies=[Depends(auth)])
async def conduct_ask(name: str, request: Request) -> dict:
    """The owner's words: the conductor drafts the phase's goal (not started: the owner starts it)."""
    from aurora import prj_conduct
    _check(name)
    words = str((await request.json()).get("text", "")).strip()
    if not words:
        raise HTTPException(status_code=400, detail="empty request")
    p = pipeline()
    return await in_thread(prj_conduct.draft, cfg, name, words, prj_conduct.model(cfg, name, p), p.llm)


@router.post("/v1/aurora/projects/{name}/conduct/{entry}/start", dependencies=[Depends(auth)])
async def conduct_start(name: str, entry: str, request: Request) -> dict:
    """The owner starts a drafted goal, as written or changed; the reply comes when the agent ends."""
    from aurora import prj_conduct
    from .agents import _agent_job
    _check(name)
    body = await request.json()
    goal = next((e for e in prj_conduct.history(cfg, name) if e.get("id") == entry and e["kind"] == "goal"), None)
    if goal is None or goal.get("status") not in ("draft", "failed"):     # a failed phase may start again
        raise HTTPException(status_code=409, detail="no draft to start")
    text = str(body.get("text") or goal["text"]).strip()
    # the worker: the local model by default (owner, 22 Oct: «abbiamo un modello locale sfruttiamolo e un giudice
    # Cloud»), the cloud only when asked and the project allows it; the judge (draft, reply) stays as assigned
    local = prj_conduct.local(cfg, name) or body.get("worker", "local") != "cloud"

    def judge(goal_text, report):
        try:
            return prj_conduct.review(cfg, name, goal_text, report, prj_conduct.model(cfg, name, pipeline()))
        except Exception as e:                          # the cloud judge out (a session limit): the local model judges
            log.warning("conductor judge failed for %s (%s): the local model judges", name, e)
            return prj_conduct.review(cfg, name, goal_text, report, pipeline().llm)

    def after(ans, emit):
        try:
            r = judge(text, ans.text)
            note("agent", "project.update", {"project": name, "text": r["text"][:300]})
        except Exception as e:                          # the run's report stays in the history even so
            log.warning("conductor review failed for %s: %s", name, e)
            prj_conduct.add(cfg, name, "reply", ans.text)
        prj_conduct.update(cfg, name, entry, status="done")

    inner = _agent_job(text, remember=False, asked=True, local=local, after=after)

    def job(q, emit, run_id):
        try:
            return inner(q, emit, run_id)
        except Exception as e:                          # never left «running»: the failure said in the talk (C383)
            prj_conduct.add(cfg, name, "reply", f"⚠️ La fase si è interrotta: {str(e)[:500]}")
            prj_conduct.update(cfg, name, entry, status="failed")
            raise

    run_id = start_run(f"[{name}] {text[:120]}", origin="project", job=job)["id"]
    prj_conduct.update(cfg, name, entry, status="running", text=text, run_id=run_id,
                       worker="local" if local else "cloud")
    log.info("audit: conductor started a phase in project %s (worker: %s)", name, "local" if local else "cloud")
    return {"run_id": run_id}


@router.post("/v1/aurora/projects/{name}/conduct/{entry}/drop", dependencies=[Depends(auth)])
def conduct_drop(name: str, entry: str) -> dict:
    from aurora import prj_conduct
    _check(name)
    if prj_conduct.update(cfg, name, entry, status="dropped") is None:
        raise HTTPException(status_code=404, detail="no such entry")
    return {"dropped": entry}
