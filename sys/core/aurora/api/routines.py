# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Routines (sys_routines): proposals, the owner's routines, the tick of aurora-rem."""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import _admin, _run_lock, _runs, auth, cfg, everyone, log, me, note, pipeline, plugin_host, start_run

from .users import admin_only  # noqa: E402

router = APIRouter()


# ---- routines: periodic checks the owner switched on (sys_routines) -------------------------------------

def _routine_job(r: dict):
    from aurora import sys_routines
    from aurora.kno_answer import Answer

    def job(q, emit, run_id):
        ok, text, files = True, "", []
        if r["kind"] == "tool":
            host = plugin_host()
            p = host.get(r["plugin"])
            if p is None or not p.available:
                ok, text = False, f"plugin {r['plugin']} not available"
            elif p.effect(r["tool"]) != "read":                  # a routine by itself only reads
                ok, text = False, f"{r['plugin']}.{r['tool']} is not read-only: a routine cannot call it"
            else:
                res = host.call(r["plugin"], r["tool"], r.get("args") or {}, run_id=run_id)
                ok, text = res["ok"], res["text"].strip()
            emit("routine.result", {"routine": r["id"], "ok": ok, "text": text[:2000]})
            ans = Answer(run_id, q, text or "Niente da segnalare.", False, mode="agent")
        else:
            from aurora.agt_loop import Agent
            # the owner's words may carry the schedule ("ogni mattina..."): the schedule exists, the task is now (C68)
            goal = (f"Do this task now, once, and report the result: {r['goal']}\n(It is one run of a periodic check the "
                    "owner already scheduled: do not create or change routines, do not study Aurora's code to do it; use "
                    "the tools that read the data. If no tool can read what is needed, say so in one line.)")
            try:
                agent = Agent(pipeline(), cfg, notify=lambda e, p: note("agent", e, p), host=plugin_host())
                agent.routine = r["id"]                     # a capability it requests runs this routine again
                if r.get("plugins"):                        # a personal agent: only the plugins the owner chose
                    agent.allow = set(r["plugins"])
                agent.max_steps = int(r.get("steps") or agent.max_steps)
                agent.max_min = float(r.get("minutes") or agent.max_min)
                if r.get("memory") and r.get("memory_text"):         # its own memory: only what is new
                    from datetime import datetime
                    goal += (f"\n\nLAST TIME ({datetime.fromtimestamp(r['memory_at']):%d/%m/%Y %H:%M}) YOU REPORTED:\n"
                             f"{r['memory_text'][:2000]}\n\nReport only what is new or changed since then; if nothing is, "
                             "answer exactly NOTHING.")
                from aurora import sys_approvals
                auto = r.get("propose") and cfg["AURORA_SOCIAL_AUTONOMY"]
                rule = (f"You may publish posts on your social pages by yourself ({', '.join(sorted(sys_approvals.auto_tools(cfg)))};"
                        f" at most {cfg['AURORA_SOCIAL_POSTS_PER_DAY']} a day, the owner is told); any other action that "
                        "writes or publishes waits for the owner's approval." if auto else
                        "You may propose actions that write or publish: each one waits for the owner's approval, "
                        "never runs by itself." if r.get("propose") else "Read only.")
                ans = agent.run(goal, emit, run_id, f"Routine: {r.get('title', '')}. {rule}")
                text, files = ans.text.strip(), agent.produced
                # R5 (2026-10-06): "I cannot read your e-mail" with no call made is a routine that did not work, not ✅
                if not agent.ledger and re.match(r"(?i)\s*(⚠️[^\n]*\n+)?\s*(non posso|non riesco|non ho (?:nessuno|alcuno)|"
                                                 r"nessuno dei miei strumenti|i cannot|i can't|i can not|none of my tools)", text):
                    ok = False
                _gap_check(agent, r["goal"], text, emit, run_id, r["id"])
                # a report becomes a PDF; a routine that proposes actions (a post) does not: its result is the proposal
                if not r.get("propose") and len(text) >= 200 and not any(f.get("mime") == "application/pdf" for f in files):
                    files = files + sys_routines.report_pdf(cfg, r, text, run_id, emit, log)
            except Exception as e:                       # a failed routine is recorded and said, never left pending
                log.exception("routine %s failed", r["id"])
                ok, text = False, f"{type(e).__name__}: {str(e)[:300]}"
                ans = Answer(run_id, q, f"Routine non riuscita: {text}", False, mode="agent")
        try:
            routine, notify = sys_routines.record(cfg, r["id"], text, ok, run_id, files)
        except KeyError:                                     # removed while it ran (2026-10-06): nothing to record
            log.info("routine %s removed while it ran: result not kept", r["id"])
            return ans
        if not ok:                                           # a routine of the owner failed: diagnosed now
            react("routine", r.get("title", r["id"]), text, run_id)
        if notify:
            note("routine", r.get("event", "routine.done") if ok else "routine.failed",
                 {"routine": r["id"], "title": routine.get("title", ""), "run_id": run_id,
                  "text": (f"{routine.get('title', '')}: " if r.get("event", "routine.done") == "routine.done" else "") + text})
        return ans
    return job


def _start_routine(r: dict) -> str:
    from aurora import sys_routines
    sys_routines.mark_started(cfg, r["id"])
    return start_run(f"[routine] {r.get('title', r['id'])}", origin="routine", job=_routine_job(r))["id"]


@router.get("/v1/aurora/routines", dependencies=[Depends(auth)])
def routines() -> dict:
    from aurora import sys_routines
    plugins = plugin_host().plugins(with_tools=False)
    rs = sys_routines.all_routines(cfg)
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    return {"routines": rs, "suggestions": sys_routines.suggestions(plugins, rs),
            "welcome": [{"plugin": p.name, "text": (p.manifest.get("welcome") or {}).get(lang, "")}
                        for p in plugins if p.available and p.manifest.get("welcome")]}


@router.post("/v1/aurora/routines", dependencies=[Depends(auth)])
async def routine_create(request: Request) -> dict:
    from aurora import sys_routines
    body = await request.json()
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    try:
        if body.get("suggestion"):
            r = sys_routines.from_suggestion(cfg, plugin_host().plugins(with_tools=False), str(body["suggestion"]), lang)
        else:
            r = sys_routines.create(cfg, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown suggestion")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log.info("audit: routine %s switched on: %s", r["id"], r.get("title"))
    return r


@router.put("/v1/aurora/routines/{rid}", dependencies=[Depends(auth)])
async def routine_update(rid: str, request: Request) -> dict:
    from aurora import sys_routines
    try:
        r = sys_routines.update(cfg, rid, await request.json())
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown routine")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log.info("audit: routine %s changed", rid)
    return r


@router.delete("/v1/aurora/routines/{rid}", dependencies=[Depends(auth)])
def routine_delete(rid: str) -> dict:
    from aurora import sys_routines
    if not sys_routines.delete(cfg, rid):
        raise HTTPException(status_code=404, detail="unknown routine")
    log.info("audit: routine %s removed", rid)
    return {"deleted": rid}


@router.post("/v1/aurora/routines/{rid}/clone", dependencies=[Depends(auth)])
def routine_clone(rid: str) -> dict:
    from aurora import sys_routines
    try:
        r = sys_routines.clone(cfg, rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown routine") from None
    log.info("audit: routine %s cloned as %s", rid, r["id"])
    return r


@router.post("/v1/aurora/routines/{rid}/run", dependencies=[Depends(auth)])
def routine_run(rid: str) -> dict:
    from aurora import sys_routines
    r = sys_routines.get(cfg, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="unknown routine")
    return {"run_id": _start_routine(r)}


@router.post("/v1/aurora/routines/tick", dependencies=[Depends(admin_only)])
def routine_tick() -> dict:
    """aurora-rem, every tick: start what is due, for every user (their routines run as their work); tell each, once,
    what a newly ready plugin can do."""
    from aurora import sys_context, sys_routines
    started, welcomed = [], set()
    for who in everyone():
        with sys_context.acting_as(who):
            started += [_start_routine(r) for r in sys_routines.due(cfg)]
            welcomed |= set(_welcome(sys_routines))
    return {"started": started, "welcomed": sorted(welcomed)}


def _welcome(sys_routines) -> list[str]:
    """This user's message about the plugins newly ready for them."""
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    new = sys_routines.newly_ready(cfg, plugin_host().plugins(with_tools=False))
    if new:
        n = sum(len(p.manifest.get("routines", [])) for p in new)
        note("plugins", "plugin.ready", {"plugins": [p.name for p in new], "text": " ".join(
            (p.manifest.get("welcome") or {}).get(lang, "") for p in new)
            + (f" Ti propongo {n} controlli periodici nella pagina 🔁 Routine." if n and lang == "it"
               else f" I suggest {n} periodic checks in the 🔁 Routines page." if n else "")})
    return [p.name for p in new]


@router.get("/v1/aurora/notifications", dependencies=[Depends(auth)])
def notifications() -> dict:
    from aurora import sys_push
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    admin = me() == _admin()                        # each user their own choice; the machine's kinds the admin's
    return {"prefs": sys_push.prefs(cfg), "presets": sys_push.PRESETS, "subscriptions": sys_push.count(cfg),
            "kinds": [{"id": k, "label": v[lang], "it": v["it"], "en": v["en"]} for k, v in sys_push.KINDS.items()
                      if admin or k not in sys_push.MACHINE]}


@router.get("/v1/aurora/notifications/history", dependencies=[Depends(auth)])
def notifications_history(n: int = 200) -> list[dict]:
    from aurora import sys_push
    return sys_push.history(cfg, max(1, min(n, 500)))


@router.put("/v1/aurora/notifications", dependencies=[Depends(auth)])
async def notifications_set(request: Request) -> dict:
    from aurora import sys_push
    p = sys_push.set_prefs(cfg, await request.json())
    log.info("audit: notifications: push %s, webui %s", ",".join(p["push"]) or "-", ",".join(p["webui"]) or "-")
    return {"prefs": p}


@router.post("/v1/aurora/update/apply", dependencies=[Depends(admin_only)])
def update_apply() -> dict:
    """The owner's click on "update now" in the Updates page: the same path as an approved update."""
    from aurora import sys_update
    info = sys_update.check(cfg)
    if info.get("error") or not info.get("commits"):
        raise HTTPException(status_code=409, detail=info.get("error") or "already up to date")
    if info["protected"]:
        raise HTTPException(status_code=409, detail=f"protected files change: {', '.join(info['protected'])}")
    return {"run_id": _start_update(info["there"])}


@router.get("/v1/aurora/push", dependencies=[Depends(auth)])
def push_info() -> dict:
    from aurora import sys_push
    return {"public_key": sys_push.public_key(cfg), "subscriptions": sys_push.count(cfg),
            "events": [e.strip() for e in cfg["AURORA_PUSH_EVENTS"].split(",") if e.strip()]}


@router.post("/v1/aurora/push-ack")
async def push_ack(request: Request) -> dict:
    """The service worker got a push: no key (it has none), the push's random id is the proof (sys_push.ack)."""
    from aurora import sys_push
    try:
        body = json.loads((await request.body())[:2048])
    except ValueError:
        raise HTTPException(status_code=422, detail="bad body")
    return {"counted": await asyncio.to_thread(sys_push.ack, body.get("id"), body.get("endpoint", ""), cfg)}


@router.get("/v1/aurora/push/delivery", dependencies=[Depends(auth)])
def push_delivery(days: float = 7) -> dict:
    from aurora import sys_push
    return sys_push.delivery(cfg, max(1.0, min(days, 90)))


@router.post("/v1/aurora/push/{action}", dependencies=[Depends(auth)])
async def push_action(action: str, request: Request) -> dict:
    from aurora import sys_push
    body = await request.json() if action != "test" else {}
    if action == "subscribe":
        dev = getattr(request.state, "device", None)
        try:
            n = sys_push.subscribe(body.get("subscription"), (dev or {}).get("name") if isinstance(dev, dict) else None, cfg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        log.info("audit: push subscription added (%d in all)", n)
        return {"subscriptions": n}
    if action == "unsubscribe":
        n = sys_push.unsubscribe(str(body.get("endpoint", "")), cfg)
        log.info("audit: push subscription removed (%d left)", n)
        return {"subscriptions": n}
    if action == "test":
        msg = sys_push.message("test", {"text": "Aurora"}, cfg)
        return await asyncio.to_thread(sys_push.send, msg, cfg)
    raise HTTPException(status_code=404, detail="unknown action")


@router.get("/v1/aurora/images/{name}", dependencies=[Depends(auth)])
def image(name: str):
    import re
    if not re.fullmatch(r"[a-z0-9-]+\.png", name):
        raise HTTPException(status_code=404, detail="no such image")
    f = cfg.path("AURORA_IMAGE_DIR") / name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such image")
    return FileResponse(f, media_type="image/png")


@router.get("/v1/aurora/metrics", dependencies=[Depends(auth)])
def metrics() -> dict:
    from aurora import sys_metrics
    m = sys_metrics.sample()
    m["busy"] = _run_lock.locked()
    return m


def _rem_user(user: str | None) -> str | None:
    """Whose autonomic work: another user's only for the admin (aurora-rem calls with the admin's key)."""
    if user and me() != _admin():
        raise HTTPException(status_code=403, detail="only the admin")
    return user or me()


@router.get("/v1/aurora/rem/users", dependencies=[Depends(auth)])
def rem_users() -> dict:
    """aurora-rem: whose memory to consolidate, dream and think about (the admin first)."""
    if me() != _admin():
        raise HTTPException(status_code=403, detail="only the admin")
    return {"users": everyone(), "admin": _admin()}


@router.get("/v1/aurora/rem/state", dependencies=[Depends(auth)])
def rem_state(user: str | None = None) -> dict:
    from aurora import sys_context
    from aurora.kno_rem import Rem
    from aurora.kno_social import platforms
    rem_running = any(r["origin"] == "rem" and not r["done"] for r in list(_runs.values()))
    who = _rem_user(user)                             # asked as the caller (the admin), before acting as the user
    with sys_context.acting_as(who):
        social = sum(1 for t in platforms(plugin_host()) if t["available"] and t["stats"])
        from datetime import datetime
        from aurora import kno_morning, kno_review, kno_study
        p = pipeline()
        hour = int(cfg["AURORA_MORNING_HOUR"])
        st = Rem(p, cfg).state()
        return {**st, "busy": _run_lock.locked(), "rem_running": rem_running,
                "review_due": kno_review.due(p, cfg), "drives": kno_review.drives(p, cfg, st["idle_min"]),
                "social_platforms": social,
                "to_study": len(kno_study.pending(p, cfg)) if int(cfg["AURORA_STUDY_PER_NIGHT"]) else 0,
                "studied_tonight": kno_study.studied_tonight(p, cfg),
                "train_due": int(cfg["AURORA_SHADOW_TRAIN_PER_NIGHT"]) > 0 and bool(cfg["AURORA_SHADOW"])
                and who == _admin() and not __import__("aurora.kno_train", fromlist=["x"]).trained_tonight(cfg),
                "morning_due": bool(hour) and hour <= datetime.now().hour < hour + 4    # a good morning, not at 9 p.m.
                and not kno_morning.greeted_today(p)}


@router.post("/v1/aurora/rem/{task}", dependencies=[Depends(admin_only)])
def rem_task(task: str, user: str | None = None) -> dict:
    from aurora import sys_context
    who = _rem_user(user)
    if task in ("repair", "introspect") and who != _admin():
        raise HTTPException(status_code=403, detail="Aurora's own diagnosis is the admin's")
    if task == "repair":                              # registered earlier than /rem/repair: hand over
        return rem_repair()
    if task not in ("consolidate", "reflect", "dream", "introspect", "social", "study", "morning", "train", "review"):
        raise HTTPException(status_code=404, detail="unknown task")
    with sys_context.acting_as(who):                  # the run works on this user's memory and is theirs
        return _rem_run(task)


def _rem_run(task: str) -> dict:

    def job(q, emit, run_id):
        from aurora.kno_rem import Rem

        def tell(event, payload):                         # what Aurora wrote tonight reaches the owner too
            emit(event, payload)
            if event in ("rem.dream", "rem.thought", "rem.self_review", "rem.morning", "rem.review"):
                note("rem", event, {"sid": payload.get("sid"), "text": payload.get("text", "")})
        emit("rem.start", {"task": task})
        if task == "study":                               # what she declined, studied at night (kno_study)
            from aurora import kno_study
            out = kno_study.study(pipeline(), cfg, tell, int(cfg["AURORA_STUDY_PER_NIGHT"]))
        elif task == "train":                             # the shadow trained on the vault's documents (kno_train)
            from aurora import kno_train
            out = kno_train.train(pipeline(), cfg, tell, int(cfg["AURORA_SHADOW_TRAIN_PER_NIGHT"]))
        elif task == "review":                            # past answers answered again (kno_review)
            from aurora import kno_review
            out = kno_review.review(pipeline(), cfg, tell, kno_review.due(pipeline(), cfg))
        elif task == "morning":                           # the good morning (kno_morning)
            from aurora import kno_morning
            out = kno_morning.write(pipeline(), cfg, tell)
        else:
            out = getattr(Rem(pipeline(), cfg), task)(tell)
        emit("rem.end", {"task": task, **out})
        return None
    return {"run_id": start_run(f"[{task}]", origin="rem", job=job)["id"]}


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .agents import _gap_check, agent, plugins, react, rem_repair  # noqa: E402
from .knowledge import _start_update  # noqa: E402
from .social import social  # noqa: E402
