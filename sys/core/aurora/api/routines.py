# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Routines (sys_routines): proposals, the owner's routines, the tick of aurora-rem."""
from __future__ import annotations

import asyncio
import json
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import _admin, _run_lock, _runs, auth, cfg, everyone, log, me, note, pipeline, plugin_host, start_run

from .users import admin_only, may_manage  # noqa: E402

router = APIRouter()


# ---- routines: periodic checks the owner switched on (sys_routines) -------------------------------------

def _routine_job(r: dict):
    from aurora import sys_routines
    from aurora.kno_answer import Answer

    def job(q, emit, run_id):
        ok, text, files = True, "", []
        if r["kind"] == "story":                             # Aurora's videos on a schedule (kno_story_auto)
            from aurora import kno_story_auto
            try:
                if r.get("action") == "publish":
                    text = kno_story_auto.publish(cfg, plugin_host(), emit, run_id, str(r.get("format") or ""), pipeline().llm)
                    ok = not text.startswith("Video «")
                else:
                    out = kno_story_auto.make(pipeline(), cfg, plugin_host(), emit)
                    text = f"🎬 Video pronto: «{out['topic']}» ({out['length_s']:.0f} s, {out['video']})" + (
                        "\nScartati: " + " · ".join(out["tried"]) if out["tried"] else "")
            except Exception as e:                       # noqa: BLE001 - a failed video is recorded and said
                log.exception("routine %s (video) failed", r["id"])
                ok, text = False, f"{type(e).__name__}: {str(e)[:300]}"
            ans = Answer(run_id, q, text, False, mode="agent")
        elif r["kind"] == "firewall":                         # the firewall restarted on a schedule (sec_fwpower)
            from aurora import sec_fwpower
            try:
                out = sec_fwpower.restart(cfg)
                ok = out["ok"]
                text = (f"🔥 Firewall riavviato: di nuovo raggiungibile dopo {out['away_s']} s" if ok else
                        f"⚠️ Firewall riavviato ma la sua API non risponde dopo {out['away_s']} s: controllalo")
            except Exception as e:                       # noqa: BLE001 - a restart not sent is recorded and said
                log.exception("routine %s (firewall) failed", r["id"])
                ok, text = False, f"Riavvio del firewall non inviato: {type(e).__name__}: {str(e)[:300]}"
            emit("routine.result", {"routine": r["id"], "ok": ok, "text": text})
            ans = Answer(run_id, q, text, False, mode="agent")
        elif r["kind"] == "tool":
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
                # a report becomes a PDF; a routine that proposes actions (a post) does not: its result is the proposal;
                # nor «NOTHING»: the actions' footer made it 200 characters, a PDF of nothing at every round (C327)
                if (not r.get("propose") and len(text) >= 200 and not sys_routines.NOTHING.match(text)
                        and not any(f.get("mime") == "application/pdf" for f in files)):
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


@router.post("/v1/aurora/routines", dependencies=[Depends(may_manage("routines"))])
async def routine_create(request: Request) -> dict:
    from aurora import sys_routines
    body = await request.json()
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    try:
        if body.get("kind") == "story" and me() != _admin():
            raise HTTPException(status_code=403, detail="the videos on a schedule are the admin's (GPU and the page)")
        if body.get("kind") == "firewall" and me() != _admin():
            raise HTTPException(status_code=403, detail="the firewall's restart is the admin's")
        if body.get("kind") == "tool" and me() != _admin() and body.get("plugin") not in \
                {p.name for p in plugin_host().plugins(with_tools=False) if p.available}:
            raise HTTPException(status_code=403, detail="a routine of a plugin that is not yours")
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


@router.put("/v1/aurora/routines/{rid}", dependencies=[Depends(may_manage("routines"))])
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


@router.delete("/v1/aurora/routines/{rid}", dependencies=[Depends(may_manage("routines"))])
def routine_delete(rid: str) -> dict:
    from aurora import sys_routines
    if not sys_routines.delete(cfg, rid):
        raise HTTPException(status_code=404, detail="unknown routine")
    log.info("audit: routine %s removed", rid)
    return {"deleted": rid}


@router.post("/v1/aurora/routines/{rid}/clone", dependencies=[Depends(may_manage("routines"))])
def routine_clone(rid: str) -> dict:
    from aurora import sys_routines
    try:
        r = sys_routines.clone(cfg, rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown routine") from None
    log.info("audit: routine %s cloned as %s", rid, r["id"])
    return r


@router.post("/v1/aurora/routines/{rid}/run", dependencies=[Depends(may_manage("routines"))])
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
    for who in everyone():                            # the home's automations keep their time, talk or not
        with sys_context.acting_as(who):
            _automations(who)
            _anon_expired(who)
    if (wait := _someone_talking()) is not None:      # a person first: the routines wait (owner, 2026-10-07)
        return {"started": [], "welcomed": [], "deferred": wait}
    started, welcomed = [], set()
    for who in everyone():
        with sys_context.acting_as(who):
            started += [_start_routine(r) for r in sys_routines.due(cfg)]
            welcomed |= set(_welcome(sys_routines))
            _devices_if_due(who)
            _scenes_again(who)
            _local_ticks(who)
            _astro_again(who)
    return {"started": started, "welcomed": sorted(welcomed)}


def _astro_again(who: str | None) -> None:
    """The guiding tuner the person turned on runs again after a restart, without the page open (ast_autoguide)."""
    p = plugin_host().get("astro")
    if p is None or not p.available:
        return
    try:
        from aurora.api.astro import autoguide_again
        autoguide_again()
    except Exception:                                    # noqa: BLE001 — the next tick tries again
        log.exception("astro: the guiding tuner not started again")


_looking: set[str] = set()


def _scenes_again(who: str | None) -> None:
    """A light scene that was running when the API stopped starts again, with the time it had left (hom_scenes)."""
    from aurora import hom_scenes
    p = plugin_host().get("homeassistant")
    if p is None or not p.available:
        return
    try:
        if again := hom_scenes.resume(cfg, who or "", log):
            log.info("scenes started again: %s", again)
    except Exception:                                    # noqa: BLE001 — the next tick tries again
        log.exception("scenes: not started again")


def _anon_expired(who: str | None) -> None:
    """🕶️ An anonymous chat past its 24 hours: emptied, its key deleted, even when nobody opens it (sys_anon)."""
    from aurora import sys_anon
    try:
        if sys_anon.purge_due(cfg, who):
            log.info("anonymous chat emptied after its hours")
    except Exception:                                    # noqa: BLE001 — the next tick tries again
        log.exception("anonymous chat: not emptied")


def _automations(who: str | None) -> None:
    """The home's automations due now (hom_auto), each user's: run."""
    from aurora import hom_auto
    p = plugin_host().get("homeassistant")
    if p is None or not p.available:
        return
    try:
        if ran := hom_auto.tick(cfg, who or "", log):
            log.info("home automations ran: %s", ran)
    except Exception:                                    # noqa: BLE001 — Home Assistant away: the next tick tries again
        log.exception("home automations: not run")


def _local_ticks(who: str | None) -> None:
    """This installation's own extensions (aurora/local), each user's tick; nothing when there are none."""
    import importlib.util
    if not importlib.util.find_spec("aurora.local"):
        return
    from aurora import local
    for tick in local.ticks():
        try:
            tick(who)
        except Exception:                                # noqa: BLE001 — the next tick tries again
            log.exception("local extension: tick failed")


def _devices_if_due(who: str | None) -> None:
    """A new device in this user's Home Assistant gets its agents (hom_devices), in the background."""
    from aurora import hom_devices, sys_context
    p = plugin_host().get("homeassistant")
    if (who or "") in _looking or p is None or not p.available or not hom_devices.due(cfg):
        return

    def work(_who):
        try:
            out = plugin_host().call("homeassistant", "devices", {})
            if not out.get("ok"):
                log.warning("devices: Home Assistant not read: %s", str(out.get("text", ""))[:200])
                hom_devices.tried(cfg)                  # again at the usual interval, not the next minute (C339)
                return
            report = hom_devices.welcome(cfg, pipeline()._for("service"), json.loads(out["text"]))
            if report["new"] or report.get("followed"):
                log.info("devices: new in Home Assistant %s; %d agents proposed, %d created; renamed %s; agents "
                         "following a new entity id: %s", report["new"], report["proposed"], len(report["created"]),
                         report.get("renamed"), report.get("followed"))
                note("home", "devices.new", {"text": hom_devices.message(report)})
            elif report.get("renamed"):
                log.info("devices: renamed in Home Assistant %s (the page and the proposals follow by id)", report["renamed"])
        except Exception:                                # noqa: BLE001 — the next look tries again
            log.exception("devices: the look at Home Assistant failed")
        finally:
            _looking.discard(_who or "")
    _looking.add(who or "")
    sys_context.start(work, who, name="ha-devices")


PEOPLE = ("webui", "openai", "acquire")               # a person's runs; routines, REM, forge… are Aurora's own
_deferred_since: list[float] = []


def _someone_talking(now: float | None = None) -> str | None:
    """Why the routines wait now, or None: a person's question running or asked in the last AURORA_ROUTINE_QUIET_S
    seconds — 7 October: «Che tempo farà domani?» waited 51.7 s behind the daily post that started 1 s before it. Never
    more than 15 minutes in a row: a routine due waits, it is never lost (sys_routines.is_due)."""
    from aurora import sys_routines
    return sys_routines.person_first(list(_runs.values()), now or time.time(), float(cfg["AURORA_ROUTINE_QUIET_S"] or 0),
                                     _deferred_since, PEOPLE)


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
    log.info("audit: notifications: push %s, webui %s, masked %s", ",".join(p["push"]) or "-", ",".join(p["webui"]) or "-",
             ",".join(p["masked"]) or "-")
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
        from aurora import sys_line
        await asyncio.to_thread(sys_line.post, msg, cfg)              # the app's line too (aurora-app F2)
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


from .agents import _gap_check, agent, plugins, react  # noqa: E402
from .updates import _start_update  # noqa: E402
from .social import social  # noqa: E402
