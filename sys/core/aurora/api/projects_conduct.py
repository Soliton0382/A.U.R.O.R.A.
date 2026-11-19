# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧑‍🔬 The conductor of a project (prj_conduct, ROADMAP N39): the owner's words → a phase's goal → the agent → a
reply; and 💬 the conversation with it (prj_talk)."""
from __future__ import annotations

import time

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

    from aurora import prj_discover, prj_longrun, prj_novelty, prj_prereg, prj_proof, prj_referee, txt_lang
    lang = txt_lang.detect(text)                      # the verdict in the goal's language (C516)
    since = time.time()                               # the phase's start: its frozen predictions, its changed files

    def judge(goal_text, report, ran, ref):
        try:
            return prj_conduct.review(cfg, name, goal_text, report, prj_conduct.model(cfg, name, pipeline()), lang,
                                      commands=ran, since=since, referee=ref)
        except Exception as e:                          # the cloud judge out (a session limit): the local model judges
            log.warning("conductor judge failed for %s (%s): the local model judges", name, e)
            return prj_conduct.review(cfg, name, goal_text, report, pipeline().llm, lang, commands=ran, since=since,
                                      referee=ref)

    def after(ans, emit):
        prj_conduct.update(cfg, name, entry, status="judging")    # the work is over, the conductor reads it (shown live)
        ran = sum(1 for c in getattr(ans, "commands", []) if c and c[0] == name)
        # 🧑‍⚖️ N142: the severe referee first (automatic), on what the phase left — never on the report
        ref = prj_referee.phase(cfg, name, text, since, pipeline(), lang)
        if ref:
            emit("project.referee", {k: ref.get(k) for k in ("status", "verdict", "file", "cost_usd", "seconds")})
        try:
            r = judge(text, ans.text, ran, ref)
            note("agent", "project.update", {"project": name, "text": r["text"][:300]})
        except Exception as e:                          # the run's report stays in the history even so
            log.warning("conductor review failed for %s: %s", name, e)
            prj_conduct.add(cfg, name, "reply", ans.text)
        prj_conduct.update(cfg, name, entry, status="done")

    rules = "\n\n".join(x for x in (prj_prereg.rule(cfg), prj_proof.rule(cfg), prj_discover.rule(cfg),   # N142, N143, N147
                                      prj_longrun.rule(cfg), prj_novelty.rule(cfg)) if x)                # N145, N146
    inner = _agent_job(text, rules, remember=False, asked=True, local=local, after=after, project=name)

    def job(q, emit, run_id):
        try:
            return inner(q, emit, run_id)
        except Exception as e:                          # never left «running»: the failure said in the talk (C383)
            stop = "La fase si è interrotta" if lang == "it" else "The phase stopped"      # the goal's language (C511)
            prj_conduct.add(cfg, name, "reply", f"⚠️ {stop}: {str(e)[:500]}")
            prj_conduct.update(cfg, name, entry, status="failed")
            raise

    run_id = start_run(f"[{name}] {text[:120]}", origin="project", job=job)["id"]
    prj_conduct.update(cfg, name, entry, status="running", text=text, run_id=run_id, started=since,
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


@router.get("/v1/aurora/projects/{name}/live", dependencies=[Depends(auth)])
def project_live(name: str) -> dict:
    """🖥️ One look at everything that moves in the project (prj_live): the page's activity console compares two."""
    from aurora import prj_live
    _check(name)
    return prj_live.snapshot(cfg, name)


# ---- 💬 the conversation with the conductor (prj_talk, N39 step 2) ------------------------------------------------
@router.get("/v1/aurora/projects/{name}/talk", dependencies=[Depends(auth)])
def talk_list(name: str) -> dict:
    from aurora import prj_talk
    _check(name)
    kind, _ = prj_talk.backend(cfg, name, pipeline())
    s = prj_talk.session(cfg, name)
    from aurora import prj_act
    return {"turns": prj_talk.turns(cfg, name), "backend": kind, "session": bool(s.get("session")),
            "since": s.get("since"), "working": prj_act.working(cfg, name)}


@router.post("/v1/aurora/projects/{name}/talk", dependencies=[Depends(auth)])
async def talk_say(name: str, request: Request) -> dict:
    """The owner's words → the conductor's answer (CLI session resumed, or the local model / an API, masked)."""
    from aurora import prj_talk
    _check(name)
    words = str((await request.json()).get("text", "")).strip()
    if not words:
        raise HTTPException(status_code=400, detail="empty request")
    from aurora import txt_lang
    lang = txt_lang.detect(words)                     # the language of the words (C516), not the installation's
    try:
        out = await in_thread(prj_talk.say, cfg, name, words, pipeline(), lang)
    except RuntimeError as e:                         # already working on this project: said, not a server error
        raise HTTPException(status_code=409, detail=str(e)) from None
    log.info("audit: conductor talk in project %s (%s)", name, out.get("backend"))
    return out


@router.post("/v1/aurora/projects/{name}/talk/stop", dependencies=[Depends(auth)])
def talk_stop(name: str) -> dict:
    """The conductor at work stopped (its CLI run ended; what it changed stays, said in the talk)."""
    from aurora import prj_act
    _check(name)
    return prj_act.stop(cfg, name)


# ---- the conductor's tools, for its relay (prj_act, N39 step 3) -------------------------------------------------
# no user's login: the run's token (X-Aurora-Conductor, 32 random bytes, alive only while that run goes) is the proof,
# and it reaches only that run's project, as that run's user
def _run_of(request: Request):
    from aurora import prj_act
    run = prj_act.lookup(request.headers.get("X-Aurora-Conductor", ""))
    if run is None:
        raise HTTPException(status_code=401, detail="no conductor run with this token")
    return run


@router.post("/v1/aurora/conductor/tools")
def conductor_tools(request: Request) -> dict:
    return {"tools": _run_of(request).tools}           # the conductor's, or the referee's (read only, N142)


@router.post("/v1/aurora/conductor/call")
async def conductor_call(request: Request) -> dict:
    from aurora import prj_act
    run = _run_of(request)
    body = await request.json()
    return await in_thread(prj_act.call, run, str(body.get("name", "")), body.get("arguments") or {})


@router.post("/v1/aurora/projects/{name}/talk/new", dependencies=[Depends(auth)])
def talk_new(name: str) -> dict:
    from aurora import prj_talk
    _check(name)
    return prj_talk.new(cfg, name)


# ---- 🔒 frozen predictions and 🧑‍⚖️ severe reviews (prj_prereg, prj_referee, N142) -----------------------------------
@router.get("/v1/aurora/projects/{name}/prereg", dependencies=[Depends(auth)])
def prereg_list(name: str) -> dict:
    """The ledger as Aurora keeps it: each entry open / closed, its outcomes counted, its integrity."""
    from aurora import prj_prereg
    _check(name)
    return {"entries": prj_prereg.entries(cfg, name), "intact": prj_prereg.ledger_intact(cfg, name),
            "mode": prj_prereg.mode(cfg)}


@router.get("/v1/aurora/projects/{name}/reviews", dependencies=[Depends(auth)])
def reviews_list(name: str) -> dict:
    from aurora import prj_referee
    _check(name)
    return {"items": prj_referee.reviews(cfg, name), "enabled": bool(cfg["AURORA_REFEREE_ENABLED"])}


# ---- 📐 formal proofs (prj_proof, N143) ---------------------------------------------------------------------------
@router.get("/v1/aurora/projects/{name}/proof", dependencies=[Depends(auth)])
def proof_list(name: str) -> dict:
    """The project's last Lean checks (the user's state: the cage cannot reach it), newest first."""
    from aurora import prj_proof
    _check(name)
    return {"items": list(reversed(prj_proof.history(cfg, name))), "enabled": prj_proof.enabled(cfg)}


@router.post("/v1/aurora/projects/{name}/proof", dependencies=[Depends(auth)])
async def proof_check(name: str, request: Request) -> dict:
    """{path}: one .lean file of the project checked by Lean (a read-only cage); the check, kept in the history."""
    from aurora import prj_proof
    _check(name)
    path = str((await request.json()).get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="a .lean file of the project: «path»")
    r = await in_thread(prj_proof.check, cfg, name, path)
    log.info("audit: proof check in project %s: %s, %s s", name, r["status"], r["seconds"])
    return r


# ---- 🔭 the discovery engine (prj_discover, N147) ---------------------------------------------------------------
@router.get("/v1/aurora/projects/{name}/discover", dependencies=[Depends(auth)])
def discover_list(name: str) -> dict:
    """The project's last law searches (the user's state), newest first."""
    from aurora import prj_discover
    _check(name)
    return {"items": list(reversed(prj_discover.history(cfg, name))), "enabled": prj_discover.enabled(cfg)}


@router.post("/v1/aurora/projects/{name}/discover", dependencies=[Depends(auth)])
async def discover_run(name: str, request: Request) -> dict:
    """{data, target, inputs?, baseline?, seed?, holdout?}: a law searched on the training rows of a table of the
    project (a read-only cage), frozen, then tested on the held-out rows; the result, kept in the history."""
    from aurora import prj_discover
    _check(name)
    body = await request.json()
    if not str(body.get("data", "")).strip() or not str(body.get("target", "")).strip():
        raise HTTPException(status_code=400, detail="a table of the project («data») and its column to explain («target»)")
    try:
        a = prj_discover.run_args(body)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="seed: an integer; holdout: a number") from None
    r = await in_thread(lambda: prj_discover.discover(cfg, name, **a))
    log.info("audit: law search in project %s: %s, %s s", name, r["status"], r["seconds"])
    return r


# ---- ⏳ long runs (prj_longrun, N145) -------------------------------------------------------------------------------
@router.get("/v1/aurora/projects/{name}/longruns", dependencies=[Depends(auth)])
def longrun_list(name: str) -> dict:
    """The project's long runs (the user's state), newest first; runs left without a watcher resumed first."""
    from aurora import prj_longrun
    _check(name)
    if prj_longrun.enabled(cfg):
        prj_longrun.sweep(cfg, name)
    return {"items": list(reversed(prj_longrun.runs(cfg, name))), "enabled": prj_longrun.enabled(cfg)}


@router.get("/v1/aurora/projects/{name}/longruns/{rid}", dependencies=[Depends(auth)])
def longrun_status(name: str, rid: str) -> dict:
    """One run: its state, its progress line and its log's end."""
    from aurora import prj_longrun
    _check(name)
    try:
        return prj_longrun.status(cfg, name, rid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/v1/aurora/projects/{name}/longruns", dependencies=[Depends(auth)])
async def longrun_start(name: str, request: Request) -> dict:
    """{command, title?, wall_s, mem_mb, disk_mb, cpu_s?, gpu?, outputs?, code_files?}: a long run started in the
    background, its limits declared first."""
    from aurora import prj_longrun
    _check(name)
    body = await request.json()
    try:
        st = await in_thread(lambda: prj_longrun.start(cfg, name, str(body.get("command") or ""),
                                                        prj_longrun.limits(cfg, body), str(body.get("title") or ""),
                                                        body.get("outputs") or [], body.get("code_files") or []))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    log.info("audit: long run %s started in project %s", st["id"], name)
    return st


@router.post("/v1/aurora/projects/{name}/longruns/{rid}/stop", dependencies=[Depends(auth)])
def longrun_stop(name: str, rid: str) -> dict:
    from aurora import prj_longrun
    _check(name)
    try:
        st = prj_longrun.stop(cfg, name, rid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    log.info("audit: long run %s stop asked in project %s", rid, name)
    return st


# ---- 📚 the literature check (prj_novelty, N146) ---------------------------------------------------------------
@router.get("/v1/aurora/projects/{name}/novelty", dependencies=[Depends(auth)])
def novelty_list(name: str) -> dict:
    from aurora import prj_novelty
    _check(name)
    return {"items": list(reversed(prj_novelty.history(cfg, name))), "enabled": prj_novelty.enabled(cfg)}


@router.post("/v1/aurora/projects/{name}/novelty", dependencies=[Depends(auth)])
async def novelty_check(name: str, request: Request) -> dict:
    """{claim, keywords?}: the literature searched for a statement (one masked query); the verdict, kept."""
    from aurora import prj_novelty
    _check(name)
    body = await request.json()
    if not str(body.get("claim", "")).strip():
        raise HTTPException(status_code=400, detail="the result's statement: «claim»")
    r = await in_thread(lambda: prj_novelty.check(cfg, project=name, **prj_novelty.args(body)))
    log.info("audit: literature check in project %s: %s, %s s", name, r["status"], r["seconds"])
    return r


@router.post("/v1/aurora/projects/{name}/referee", dependencies=[Depends(auth)])
async def referee_start(name: str, request: Request) -> dict:
    """A severe review started by hand: on the last phase done (its goal, from its start), else the whole project; its
    verdict comes into the conductor's conversation."""
    from aurora import prj_conduct, prj_referee, txt_lang
    _check(name)
    body = await request.json() if (await request.body()) else {}
    done = [e for e in prj_conduct.history(cfg, name) if e.get("kind") == "goal" and e.get("status") == "done"]
    last = done[-1] if done else {}
    goal = str(body.get("text") or last.get("text") or "").strip()
    since = last.get("started", last.get("t")) if last and not body.get("text") else None
    lang = txt_lang.detect(goal) if goal else "it"

    def job(q, emit, run_id):
        ref = prj_referee.phase(cfg, name, goal, since, pipeline(), lang)
        if ref is None:
            raise RuntimeError("the severe referee is off (AURORA_REFEREE_ENABLED)")
        prj_conduct.add(cfg, name, "reply", ref["summary"], **({"review": ref["file"]} if ref.get("file") else {}))
        emit("answer.final", {"text": ref["summary"], "abstained": False, "sources": [],
                              "seconds": ref.get("seconds") or 0.0, "mode": "agent"})
        from aurora.kno_answer import Answer
        return Answer(run_id, goal, ref["summary"], False, mode="agent")

    log.info("audit: severe review started by hand in project %s", name)
    return {"run_id": start_run(f"[{name}] revisione severa", origin="project", job=job)["id"]}
