# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-rem's side of the API: whose autonomic work, her mood, the state it decides on, the task it starts
(split from api/routines: no monoliths)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .core import _admin, _run_lock, _runs, auth, cfg, everyone, log, me, note, pipeline, plugin_host, start_run

from .users import admin_only  # noqa: E402

router = APIRouter()


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


def _mood(st: dict, admin: bool) -> dict:
    """💗 her emotions measured now (kno_mood), with a busy-sample for tiredness; saved for her own prompts."""
    from aurora import kno_mood
    if not cfg["AURORA_MOOD"]:
        return {"on": False, "emotions": {}, "dominant": None}
    active = sum(1 for r in list(_runs.values()) if not r["done"])
    g = kno_mood.gpus()
    kno_mood.record(cfg, _run_lock.locked() or active > 0, g)
    if admin:
        try:
            from .activity import health_all
            st = {**st, "health_problems": health_all()["problems"]}
        except Exception as e:                        # noqa: BLE001 — a health check never stops the REM look
            log.warning("mood: health not read: %s", e)
    m = kno_mood.measure(cfg, st, active, admin)
    try:
        kno_mood.save(cfg, m)
    except OSError as e:
        log.warning("mood: not saved: %s", e)
    return m


@router.get("/v1/aurora/mood", dependencies=[Depends(auth)])
def mood() -> dict:
    """How Aurora feels now, each emotion with its measured causes (the top bar each minute, the Health page): the
    REM's own measure of the last 3 minutes (it looks once a minute), measured now only when there is none."""
    from aurora import kno_mood
    if not cfg["AURORA_MOOD"]:
        return {"on": False, "emotions": {}, "dominant": None}
    return kno_mood.last(cfg, 180) or rem_state()["mood"]


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
        st["drives"] = kno_review.drives(p, cfg, st["idle_min"])
        st["to_study"] = len(kno_study.pending(p, cfg)) if int(cfg["AURORA_STUDY_PER_NIGHT"]) else 0
        st["mood"] = _mood(st, who == _admin())
        return {**st, "busy": _run_lock.locked(), "rem_running": rem_running,
                "review_due": kno_review.due(p, cfg),
                "social_platforms": social,
                "studied_tonight": kno_study.studied_tonight(p, cfg),
                "deduce_due": int(cfg["AURORA_DEDUCE_PER_NIGHT"]) > 0 and who == _admin()
                and not __import__("aurora.kno_deduce", fromlist=["x"]).deduced_tonight(cfg),
                "project_due": __import__("aurora.api.projects_plan", fromlist=["x"]).due(),
                "audit_due": who == _admin() and not __import__("aurora.kno_vault_audit", fromlist=["x"]).done_tonight(cfg),
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
    if task not in ("consolidate", "reflect", "dream", "introspect", "social", "study", "morning", "train", "review",
                    "deduce", "audit", "project"):
        raise HTTPException(status_code=404, detail="unknown task")
    with sys_context.acting_as(who):                  # the run works on this user's memory and is theirs
        if task == "project":                         # a step of a project carried by Aurora (prj_plan, ROADMAP 97)
            from .projects_plan import rem_project
            return rem_project()
        return _rem_run(task)


def _rem_run(task: str) -> dict:

    def job(q, emit, run_id):
        from aurora.kno_rem import Rem

        def tell(event, payload):                         # what Aurora wrote tonight reaches the owner too
            emit(event, payload)
            if event in ("rem.dream", "rem.thought", "rem.self_review", "rem.morning", "rem.review", "vault.audit"):
                note("rem", event, {"sid": payload.get("sid"), "text": payload.get("text", "")})
        emit("rem.start", {"task": task})
        if task == "study":                               # what she declined, studied at night (kno_study)
            from aurora import kno_study
            out = kno_study.study(pipeline(), cfg, tell, int(cfg["AURORA_STUDY_PER_NIGHT"]))
        elif task == "train":                             # the shadow trained on the vault's documents (kno_train)
            from aurora import kno_train
            out = kno_train.train(pipeline(), cfg, tell, int(cfg["AURORA_SHADOW_TRAIN_PER_NIGHT"]))
        elif task == "deduce":                            # bridges between distant fields, verified (kno_deduce)
            from aurora import kno_deduce
            out = kno_deduce.round_(pipeline(), cfg, tell, int(cfg["AURORA_DEDUCE_PER_NIGHT"]))
        elif task == "audit":                             # the vault watched: copies, PDFs, misplaced (kno_vault_audit)
            from aurora import kno_vault_audit
            out = kno_vault_audit.audit(cfg, pipeline()._for("route"), tell)
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


# looked up only when called: imported last, so that modules that use each other load in any order
from .agents import rem_repair  # noqa: E402


@router.get("/v1/aurora/dreams", dependencies=[Depends(auth)])
def dreams(n: int = 24, before: str | None = None, q: str = "") -> dict:
    """Every dream of hers, newest first, with its painting (the Dreams page, owner 15 Oct: «dopo un po' si perdono
    nelle chat»); `before` the created_at of the last one shown, for the next ones; `q` words in the dream."""
    p = pipeline()
    if not p.reader.layout.shards("memory", "reflection"):
        return {"dreams": [], "more": False}
    n = max(1, min(int(n), 60))
    found = p.reader.of_type("reflection", "dream", n + 1, before, q.strip()[:100])
    return {"more": len(found) > n, "dreams": [
        {"sid": s.sid, "text": s.text, "created_at": s.created_at,
         "image": f"/v1/aurora/images/{s.extra['image']}" if s.extra.get("image") else None,
         "image_prompt": s.extra.get("image_prompt", ""), "painting_problem": s.extra.get("painting_problem")}
        for s in found[:n]]}
