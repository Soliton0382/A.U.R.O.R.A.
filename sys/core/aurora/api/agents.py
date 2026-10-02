# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Agents, plugins (list, switch, icons, settings, tools) and approvals."""
from __future__ import annotations

import asyncio
import base64
import httpx
import io
import json
import subprocess
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from .core import auth, cfg, log, note, pipeline, plugin_host, start_run

router = APIRouter()


# ---- agents, plugins, approvals ------------------------------------------------------------------
def _gap_check(agent, goal: str, report: str, emit, run_id: str, routine: str | None = None) -> None:
    """After an agent run, by code: a report saying a tool is missing becomes a forge request (agt_forge.detect_gap)."""
    from aurora import agt_forge
    try:
        need = agt_forge.detect_gap(pipeline()._for("route"), goal, report, getattr(agent, "requested", False))
    except Exception:                                    # the check never breaks the run
        log.exception("gap check")
        return
    if need:
        req = agt_forge.request(cfg, need, f"rilevato dopo il run: {goal[:300]}", run_id, routine)
        emit("forge.request", {"id": req["id"], "need": req["need"], "status": req["status"], "by": "code"})
        note("forge", "forge.request", {"id": req["id"], "title": req["need"][:160]})
        log.info("gap found after run %s: forge request %s (%s)", run_id, req["id"], need[:120])


def _agent_job(goal: str, context: str = "", after=None, remember: bool = False, label: str | None = None):
    """An agent run. `remember`: the owner asked for it, so goal and report become conversation turns
    (with the whole path), like any other answer; the autonomic ones become reflections (`after`)."""
    def job(q, emit, run_id):
        from aurora.agt_loop import Agent
        from aurora.sol_schema import now_iso
        asked_at = now_iso()
        agent = Agent(pipeline(), cfg, notify=lambda e, p: note("agent", e, p), host=plugin_host())
        ans = agent.run(goal, emit, run_id, context)
        _gap_check(agent, goal, ans.text, emit, run_id)
        if agent.produced:                             # the documents it wrote stay with its turn (downloadable)
            from aurora import sys_uploads
            for f in agent.produced:
                if not f["url"].startswith("/v1/aurora/uploads/"):    # a picture it painted is kept already
                    sys_uploads.link(cfg, run_id, f["name"], f["url"], f["mime"])
        if remember:
            pipeline().remember(label or f"/agente {goal}", ans, run_id, emit, agent.trail, asked_at)
        if after:
            after(ans, emit)
        return ans
    return job


@router.post("/v1/aurora/agent", dependencies=[Depends(auth)])
async def agent(request: Request) -> dict:
    body = await request.json()
    goal = str(body.get("goal", "")).strip()
    if not goal:
        raise HTTPException(status_code=400, detail="empty goal")
    job = _agent_job(goal, str(body.get("context", "")), remember=body.get("remember", True) is not False)
    return {"run_id": start_run(goal, origin="agent", job=job)["id"]}


@router.get("/v1/aurora/plugins", dependencies=[Depends(auth)])
def plugins() -> list[dict]:
    return [{"name": p.name, "version": p.manifest.get("version"), "kind": p.manifest.get("kind"),
             "description": p.manifest.get("description", {}), "enabled": p.enabled, "available": p.available,
             "missing": p.missing, "error": p.error, "setup": p.manifest.get("setup", {}),
             "settings": [k for k in dict.fromkeys(p.manifest.get("env", []) + p.manifest.get("requires", [])
                                                   + list(p.manifest.get("env_as", {})) + p.manifest.get("settings", []))],
             "icon": f"/v1/aurora/plugins/{p.name}/icon?v={_icon_version(p)}",
             "tools": [{"name": t["name"], "effect": t["effect"], "description": t["description"],
                        "required": (t.get("input_schema") or {}).get("required", [])} for t in p.tools]}
            for p in plugin_host().plugins()]


@router.post("/v1/aurora/plugins/{name}/{action}", dependencies=[Depends(auth)])
def plugin_switch(name: str, action: str) -> dict:
    if action not in ("enable", "disable"):
        raise HTTPException(status_code=404, detail="unknown action")
    host = plugin_host()
    if name not in {p.name for p in host.plugins(with_tools=False)}:
        raise HTTPException(status_code=404, detail="unknown plugin")
    host.set_enabled(name, action == "enable")
    return {"name": name, "enabled": action == "enable"}


ICON_DEFAULT = {"tool": "🛠️", "connector": "🔌", "service": "🛰️", "trigger": "⚡"}


def _icon_version(p) -> int:
    """Changes only when the icon does: the browser keeps it otherwise (the Plugins page loaded every icon again)."""
    for f in (cfg.path("AURORA_STATUS_DIR") / "plugins" / "icons" / f"{p.name}.png", p.folder / "icon.png"):
        if f.is_file():
            return int(f.stat().st_mtime)
    return 0


@router.get("/v1/aurora/plugins/{name}/icon", dependencies=[Depends(auth)])
def plugin_icon(name: str):
    """The owner's icon (user data, AURORA_STATUS_DIR/plugins/icons), else the plugin's own icon.png, else one for its kind."""
    p = next((x for x in plugin_host().plugins(with_tools=False) if x.name == name), None)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown plugin")
    for f in (cfg.path("AURORA_STATUS_DIR") / "plugins" / "icons" / f"{name}.png", p.folder / "icon.png"):
        if f.is_file():
            return FileResponse(f, media_type="image/png", headers={"Cache-Control": "no-cache"})
    glyph = ICON_DEFAULT.get(p.manifest.get("kind", "tool"), "🧩")
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' rx='14' "
           f"fill='#2a3350'/><text x='32' y='44' font-size='32' text-anchor='middle'>{glyph}</text></svg>")
    return Response(svg, media_type="image/svg+xml")


@router.post("/v1/aurora/plugins/{name}/icon", dependencies=[Depends(auth)])
async def plugin_icon_set(name: str, request: Request) -> dict:
    """The owner changes a plugin's icon: {"data": base64 image} or {"url": "https://..."} (checked,
    made a 64x64 PNG)."""
    import io
    from PIL import Image
    p = next((x for x in plugin_host().plugins(with_tools=False) if x.name == name), None)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown plugin")
    body = await request.json()
    try:
        if body.get("url"):
            url = str(body["url"])
            if not url.startswith("https://"):
                raise ValueError("only https:// links")
            raw = httpx.get(url, timeout=20, follow_redirects=True).content
        else:
            raw = base64.b64decode(body.get("data", ""), validate=True)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("image larger than 5 MB")
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = img.convert("RGBA")
        img.thumbnail((64, 64))
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        canvas.paste(img, ((64 - img.width) // 2, (64 - img.height) // 2))
        mine = cfg.path("AURORA_STATUS_DIR") / "plugins" / "icons"       # user data: the plugin's own icon stays
        mine.mkdir(parents=True, exist_ok=True)
        canvas.save(mine / f"{name}.png")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"not a usable image: {e}")
    log.info("audit: icon of plugin %s changed", name)
    return {"name": name, "icon": f"/v1/aurora/plugins/{name}/icon"}


UNITS = ("aurora-llm", "aurora-models", "aurora-api", "aurora-rem", "aurora-harvester", "aurora-sentinel", "aurora-https")


@router.post("/v1/aurora/services/restart", dependencies=[Depends(auth)])
async def restart_services(request: Request) -> dict:
    """Restart services from the WebUI (after a settings change). aurora-api restarts last, after this
    answer has left: the page reconnects by itself."""
    import subprocess
    wanted = [u for u in (await request.json()).get("services", []) if u in UNITS]
    if not wanted:
        raise HTTPException(status_code=400, detail="no known service")
    others = [u for u in wanted if u != "aurora-api"]
    if others:
        r = await asyncio.to_thread(subprocess.run, ["systemctl", "restart", "--no-block", *others],
                                    capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=r.stderr.strip()[:300] or "systemctl failed")
    if "aurora-api" in wanted:
        threading.Timer(1.5, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                    capture_output=True, timeout=30)).start()
    log.info("audit: restart requested from the WebUI: %s", ", ".join(wanted))
    return {"restarting": wanted}


@router.post("/v1/aurora/plugins/{name}/try/{tool}", dependencies=[Depends(auth)])
async def plugin_try(name: str, tool: str, request: Request) -> dict:
    """The owner tries a read-only tool from the Plugins page (e.g. is the token right?). Read only."""
    args = await request.json() if request.headers.get("content-length", "0") != "0" else {}

    def work():                                   # the host runs its own event loop: not inside this one
        host = plugin_host()
        p = host.get(name)
        if p is None or not p.available:
            raise HTTPException(status_code=409, detail="plugin not available")
        if p.effect(tool) != "read":
            raise HTTPException(status_code=403, detail="only read-only tools can be tried here")
        return host.call(name, tool, args or {})
    return await asyncio.to_thread(work)


@router.get("/v1/aurora/approvals", dependencies=[Depends(auth)])
def approvals(status: str | None = None) -> list[dict]:
    from aurora.sys_approvals import Approvals
    return Approvals(cfg).list(status)


@router.post("/v1/aurora/approvals/{approval_id}/{decision}", dependencies=[Depends(auth)])
def decide(approval_id: str, decision: str) -> dict:
    from aurora.sys_approvals import Approvals
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=404, detail="unknown decision")
    store = Approvals(cfg)
    item = store.get(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="unknown request")
    if item["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"already {item['status']}")
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if decision == "reject":
        store.update(approval_id, status="rejected", decided=now)
        if item["kind"] in ("forge_cloud", "plugin_install"):      # the forge request ends with the owner's no
            from aurora import agt_forge
            try:
                agt_forge.update(cfg, item["action"]["request"], status="declined", decided=time.time())
            except StopIteration:
                pass
        note("owner", "approval.rejected", {"id": approval_id, "title": item["title"]})
        return {"id": approval_id, "status": "rejected"}
    store.update(approval_id, status="approved", decided=now)

    def job(q, emit, run_id):
        emit("approval.execute", {"id": approval_id, "kind": item["kind"], "title": item["title"]})
        try:
            if item["kind"] == "code_change":
                from aurora import agt_change
                out = agt_change.apply(item["action"]["sandbox_id"], emit, cfg)
                ok = out.get("applied", False)
            elif item["kind"] == "forge_cloud":             # the owner allowed the cloud for this request
                from aurora import agt_forge
                req = next(r for r in agt_forge.requests(cfg) if r["id"] == item["action"]["request"])
                rid = start_run(f"[forge, cloud] {req['need'][:100]}", origin="forge", job=_forge_job(req, cloud=True))["id"]
                out, ok = {"forge_run": rid}, True
            elif item["kind"] == "plugin_install":          # a forged plugin the owner approved
                from aurora import agt_forge
                a = item["action"]
                dest = agt_forge.install(cfg, a["stage"])
                _forge_done(a["request"], a["name"])
                out, ok = {"installed": str(dest)}, True
            elif item["kind"] == "update":
                from aurora import sys_update
                out = sys_update.apply(cfg, emit)
                ok = out.get("applied", False)
                if ok:
                    out["settings_added"] = _env_add_missing()
                    threading.Timer(3.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", *UNITS],
                                                                capture_output=True)).start()
            else:
                a = item["action"]
                out = plugin_host().call(a["plugin"], a["tool"], a.get("arguments") or {}, run_id)
                ok = out["ok"]
        except Exception as e:                                # recorded, never lost
            out, ok = {"error": f"{type(e).__name__}: {e}"}, False
        store.update(approval_id, status="executed" if ok else "failed", result=out)
        emit("approval.done", {"id": approval_id, "ok": ok, "result": json.dumps(out, ensure_ascii=False)[:1500]})
        note("owner", "approval.done", {"id": approval_id, "ok": ok, "title": item["title"]})
        if not ok:                                        # an approved action that failed is told, never silent
            why = str(out.get("text") or out.get("error") or out)[:160]
            note("owner", "approval.failed", {"id": approval_id, "title": item["title"],
                                             "text": f"{item['title']}: {why}"})
        from aurora.kno_answer import Answer
        return Answer(run_id, q, ("Fatto: " if ok else "Non riuscito: ") + json.dumps(out, ensure_ascii=False)[:1500],
                      False, mode="agent")
    return {"id": approval_id, "status": "approved", "run_id": start_run(f"[approval] {item['title']}",
                                                                          origin="approval", job=job)["id"]}


@router.post("/v1/aurora/rem/repair", dependencies=[Depends(auth)])
def rem_repair() -> dict:
    """Self-repair: an agent works on the problems of the last self-review; its report becomes a memory."""
    p = pipeline()
    reviews = [s for s in p.reader.recent(40, domain="reflection") if s.extra.get("type") == "self_review"] \
        if p.reader.layout.shards("memory", "reflection") else []
    if not reviews:
        raise HTTPException(status_code=409, detail="no self-review yet")
    review = reviews[-1]
    goal = ("Autoriparazione: esamina i problemi della tua ultima autodiagnosi. Per ognuno verifica prima se è ancora "
            "presente (ultimo orario nei log, riavvii dei servizi, codice attuale): se la causa non c'è più, riportalo "
            "come risolto con la prova. Per ciò che resta, trova la causa nei log e nel codice, correggi nella sandbox "
            "ciò che ha una causa chiara e proponi la modifica; per il resto riporta cosa manca.")

    def after(ans, emit):
        from aurora.kno_rem import Rem
        Rem(p, cfg)._write(ans.text, "repair", f"repair:{int(time.time())}",
                           {"review": review.sid, "run_id": ans.run_id}, emit)
    from aurora import sys_logread
    evidence = sys_logread.problem_evidence(cfg)
    line = lambda e: (f"- {e['component']}: {e['count']} × {e['kind'][:140]} [{e['first'][11:]} → {e['last'][11:]}]; "
                      f"{e['host_service']} last start {(e['host_last_start'] or '-')[11:]}")
    alive = [e for e in evidence if e["seen_after_last_start"]]
    gone = [e for e in evidence if not e["seen_after_last_start"]]
    # Only problems seen again after their service last restarted go to the agent: the others are, by
    # measurement, not recurring (a fix or a restart already happened); the code decides this, not the model.
    if not alive:
        text = ("Autoriparazione: nessun problema dell'ultima autodiagnosi si è ripresentato dopo l'ultimo riavvio del "
                "servizio che lo ospita, quindi non c'è nulla da correggere adesso. Non ricomparsi:\n"
                + "\n".join(line(e) for e in gone[:30]))

        def quick(q, emit, run_id):
            from aurora.kno_answer import Answer
            emit("agent.finish", {"summary": text, "steps": 0, "seconds": 0})
            ans = Answer(run_id, q, text, False, mode="agent")
            after(ans, emit)
            return ans
        return {"run_id": start_run("[repair]", origin="rem", job=quick)["id"]}
    context = (f"SELF-REVIEW:\n{review.text}\n\nPROBLEMS STILL OCCURRING (seen again after their service last "
               f"started; work on these only):\n" + "\n".join(line(e) for e in alive)
               + "\n\nNOT RECURRING (not seen since the restart: do not work on them):\n"
               + "\n".join(line(e) for e in gone[:20]))
    return {"run_id": start_run("[repair]", origin="rem", job=_agent_job(goal, context, after))["id"]}


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .forge import _forge_done, _forge_job  # noqa: E402
from .knowledge import _env_add_missing  # noqa: E402
from .system import status  # noqa: E402
