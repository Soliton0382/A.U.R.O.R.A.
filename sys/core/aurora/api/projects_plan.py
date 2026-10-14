# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A project's plan, carried by Aurora herself (prj_plan, ROADMAP 97): drafted, changed and started by the owner;
worked on step by step by aurora-rem's task «project» in the machine's idle time."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, in_thread, log, note, pipeline, start_run

router = APIRouter()


def _plan(name: str) -> dict:
    from aurora import prj_plan
    try:
        plan = prj_plan.load(cfg, name)
    except ValueError:
        raise HTTPException(status_code=404, detail="no such project") from None
    if plan is None:
        raise HTTPException(status_code=404, detail="no plan yet")
    return plan


def _project(name: str) -> None:
    from aurora import prj_run
    try:
        prj_run.project_dir(cfg, name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/v1/aurora/projects/{name}/plan", dependencies=[Depends(auth)])
def plan_get(name: str) -> dict:
    from aurora import prj_plan
    plan = _plan(name)
    return {**plan, "next": prj_plan.next_step(plan), "level": int(cfg["AURORA_PROJECT_AUTONOMY"])}


@router.post("/v1/aurora/projects/{name}/plan", dependencies=[Depends(auth)])
async def plan_create(name: str, request: Request) -> dict:
    """{"goal", "steps"?}: the plan written (not started). Without steps the model drafts them from the goal and the
    project's files; the owner reads them and starts the plan (PUT active)."""
    from aurora import prj_browse, prj_plan
    _project(name)
    body = await request.json()
    goal = str(body.get("goal", "")).strip()
    if not goal:
        raise HTTPException(status_code=400, detail="a goal")
    steps = prj_plan.steps_of(body.get("steps"))
    if not steps:
        files = "\n".join(f["path"] for f in prj_browse.tree(cfg, name))
        steps = await in_thread(lambda: prj_plan.draft(pipeline()._for("agent"), goal, files))
    if not steps:
        raise HTTPException(status_code=422, detail="the model proposed no step: write them yourself")
    return prj_plan.create(cfg, name, goal, steps)


@router.put("/v1/aurora/projects/{name}/plan", dependencies=[Depends(auth)])
async def plan_change(name: str, request: Request) -> dict:
    """{"active"?, "go_on"?, "steps"?, "goal"?, "retry"?: i}: started or paused, the owner's «go on» after a step (🤝),
    the steps rewritten, a blocked step opened again with its failures forgotten."""
    from aurora import prj_plan
    plan, body = _plan(name), await request.json()
    if "goal" in body and str(body["goal"]).strip():
        plan["goal"] = str(body["goal"]).strip()[:4000]
    if "steps" in body:
        steps = prj_plan.steps_of(body["steps"])
        if not steps:
            raise HTTPException(status_code=400, detail="steps: a title and a command each")
        plan["steps"] = steps
    if isinstance(body.get("retry"), int) and 0 <= body["retry"] < len(plan["steps"]):
        plan["steps"][body["retry"]].update(status="open", tries=0)
    if "active" in body:
        plan["active"] = bool(body["active"])
    if body.get("go_on"):
        plan["waiting"] = False
    return prj_plan.save(cfg, name, plan)


@router.get("/v1/aurora/projects/{name}/docs", dependencies=[Depends(auth)])
def docs_get(name: str) -> dict:
    """The documentation ticked for this project (prj_docs) and the choices there are."""
    from aurora import prj_docs
    _project(name)
    return {**prj_docs.load(cfg, name), "choices": {k: v[0] for k, v in prj_docs.TARGETS.items()}}


@router.post("/v1/aurora/projects/{name}/docs", dependencies=[Depends(auth)])
async def docs_go(name: str, request: Request) -> dict:
    """{"targets": [...], "go": true}: the ticks kept; with go, Aurora prepares them now (an agent run: «Procedi»)."""
    from aurora import prj_docs
    from .agents import _agent_job
    _project(name)
    body = await request.json()
    targets = [str(t) for t in body.get("targets", [])]
    if not body.get("go"):
        return prj_docs.save(cfg, name, targets)
    if not targets:
        raise HTTPException(status_code=400, detail="tick at least one document")
    job = _agent_job(prj_docs.goal(name, targets), label=f"[documenti] {name}",
                     quiet=("project.update", "project.progress"))
    run = start_run(f"[docs] {name}", origin="webui", job=job)
    prj_docs.save(cfg, name, targets, run["id"])
    log.info("audit: project %s: documentation asked (%s), run %s", name, ", ".join(targets), run["id"])
    return {"run_id": run["id"], "targets": targets}


@router.get("/v1/aurora/projects/{name}/pdf", dependencies=[Depends(auth)])
def project_pdf_page(name: str, path: str, page: int = 1):
    """One page of a PDF in the project, as a picture (doc_preview): the drawings and the filings seen on the page."""
    from fastapi.responses import FileResponse
    from aurora import doc_preview, prj_browse
    try:
        f = prj_browse.inside(prj_browse.project(cfg, name), path)
        return FileResponse(doc_preview.page_png(cfg, f, max(1, int(page))), media_type="image/png")
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


def due() -> str | None:
    """The project the idle task works on now (aurora-rem's state), or None."""
    from aurora import prj_browse, prj_plan
    try:
        return prj_plan.due(cfg, [p["name"] for p in prj_browse.list_projects(cfg)])
    except (OSError, ValueError, KeyError):
        return None


def rem_project() -> dict:
    """One step of the due project: the agent works, then the step's command decides (prj_plan.record)."""
    from aurora import prj_plan, prj_run
    from .agents import _agent_job
    name = due()
    if not name:
        raise HTTPException(status_code=409, detail="no project step due")
    plan = prj_plan.load(cfg, name)
    i = prj_plan.next_step(plan)
    step = plan["steps"][i]

    def after(ans, emit):
        try:
            run = prj_run.run(cfg, name, step["test"])
        except (ValueError, RuntimeError) as e:
            run = {"exit": -2, "seconds": 0, "output": f"not run: {e}"}
        out = prj_plan.record(cfg, name, i, run, ans.run_id, ans.text)
        emit("project.step", {"project": name, "step": i + 1, "exit": run["exit"], "event": out["event"]})
        n = len(out["plan"]["steps"])
        # told: a step only when it waits for the owner (🤝), a block, the end; the rest once a day (ROADMAP 97)
        ev, waiting = out["event"], out["plan"].get("waiting")
        text = "" if ev == "project.step" and not waiting else {
            "project.step": f"{name}: passo {i + 1}/{n} fatto — {step['title']} (aspetto il tuo «vai avanti»)",
            "project.blocked": f"{name}: passo {i + 1}/{n} bloccato dopo {prj_plan.TRIES} tentativi — "
                               f"{step['title']}. Serve il tuo aiuto.",
            "project.done": f"{name}: progetto completato, {n}/{n} passi."}.get(ev, "")
        if text:
            note("agent", ev, {"project": name, "step": i + 1, "text": text})
        line = prj_plan.daily_line(cfg, name)
        if line and out["event"] != "project.done":
            note("agent", "project.daily", {"project": name, "text": line})
        log.info("project %s step %d: exit %s %s", name, i + 1, run["exit"], out["event"])

    from aurora import prj_docs
    goal = prj_plan.goal_for(plan, name, i, prj_docs.plan_note(cfg, name))
    job = _agent_job(goal, after=after, quiet=("project.update", "project.progress"))
    return {"run_id": start_run(f"[project] {name} {i + 1}", origin="rem", job=job)["id"]}
