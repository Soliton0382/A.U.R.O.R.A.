# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The capability forge (agt_forge): requests, and the builds aurora-rem starts."""
from __future__ import annotations

import re
import time

from pathlib import Path
from fastapi import APIRouter, Depends

from .core import auth, cfg, log, note, pipeline, plugin_host, start_run

router = APIRouter()


# ---- the capability forge (agt_forge): Aurora builds the plugin she is missing -----------------------------

def _forge_done(req_id: str, name: str) -> None:
    """A forged plugin is live: tell the owner, and run again the routine that asked for it."""
    from aurora import agt_forge, sys_routines
    req = agt_forge.update(cfg, req_id, status="installed", plugin=name, installed=time.time())
    note("forge", "forge.installed", {"id": req_id, "plugin": name,
                                      "text": f"Mi sono costruita il plugin «{name}»: {req['need'][:160]}"})
    r = sys_routines.get(cfg, req["routine"]) if req.get("routine") else None
    if r:
        _start_routine(r)


def _forge_job(req: dict, cloud: bool = False):
    def job(q, emit, run_id):
        from aurora import agt_forge
        from aurora.kno_answer import Answer
        agt_forge.update(cfg, req["id"], status="building", started=time.time(), attempts=req.get("attempts", 0) + 1)
        emit("forge.start", {"id": req["id"], "need": req["need"], "cloud": cloud})
        host = plugin_host()
        if cloud:                                       # the owner allowed it for this request: masked samples only
            from aurora.mdl_cloud import ClaudeCodeLLM
            res = agt_forge.build(cfg, ClaudeCodeLLM(cfg), host, req, emit, masker=agt_forge.Masker(cfg))
        else:
            res = agt_forge.build(cfg, pipeline()._for("forge_write"), host, req, emit,     # as assigned (local by default)
                                  judge=pipeline()._for("forge_judge"))
        if not res["ok"] and not cloud:                 # ask once whether the cloud may try, showing what would leave
            from aurora.sys_approvals import Approvals
            m = agt_forge.Masker(cfg)
            sample = m(agt_forge.peek(cfg, re.findall(r"[\w./-]+/[\w./-]+", req["need"])[:3] or ["sys/logs"]))
            item = Approvals(cfg).request("forge_cloud", "external", f"Posso farmi aiutare dal cloud per «{req['need'][:80]}»?",
                                          "La forgia locale non ci è riuscita. Il ragionatore cloud (Claude) vedrebbe la "
                                          "richiesta e questi campioni, mascherati (IP, email, token, nomi di dispositivi, "
                                          "i tuoi dati personali). Il plugin girerebbe comunque solo qui, nella gabbia.",
                                          {"need": req["need"], "campioni mascherati": sample[:4000],
                                           "errori locali": res["errors"][:3]}, {"request": req["id"]}, run_id)
            agt_forge.update(cfg, req["id"], status="awaiting_cloud", errors=res["errors"][:5], approval=item["id"])
            note("forge", "approval.pending", {"id": item["id"], "kind": "forge_cloud", "title": item["title"]})
            return Answer(run_id, q, "Forgia locale non riuscita: chiedo il permesso per il cloud.", False, mode="agent")
        if not res["ok"]:
            agt_forge.update(cfg, req["id"], status="failed", errors=res["errors"][:5])
            note("forge", "forge.failed", {"id": req["id"], "text": f"Non sono riuscita a costruire: {req['need'][:120]}"})
            return Answer(run_id, q, "Forgia non riuscita: " + "; ".join(res["errors"])[:1500], False, mode="agent")
        m = res["manifest"]
        if agt_forge.read_only(m):
            agt_forge.install(cfg, res["stage"])
            log.info("audit: forged plugin %s installed (read only, no network)", m["name"])
            from aurora import sys_autonomy
            sys_autonomy.log(cfg, "forge", f"plugin {m['name']} built and installed (read only): {req['need'][:150]}")
            _forge_done(req["id"], m["name"])
            text = f"Plugin «{m['name']}» costruito, provato nella gabbia e acceso (sola lettura, senza rete)."
        else:
            from aurora.sys_approvals import Approvals
            code = (Path(res["stage"]) / "server.py").read_text(encoding="utf-8")
            item = Approvals(cfg).request("plugin_install", "external", f"Installare il plugin «{m['name']}»?",
                                          f"{req['need']}\n\nMotivo: {req['why']}",
                                          {"manifest": m, "server.py": code[:6000]},
                                          {"request": req["id"], "stage": res["stage"], "name": m["name"]}, run_id)
            agt_forge.update(cfg, req["id"], status="proposed", plugin=m["name"], approval=item["id"])
            note("forge", "approval.pending", {"id": item["id"], "kind": "plugin_install", "title": item["title"]})
            text = f"Plugin «{m['name']}» costruito e provato: scrive, invia o usa la rete, quindi aspetta la tua approvazione."
        return Answer(run_id, q, text, False, mode="agent")
    return job


@router.get("/v1/aurora/forge", dependencies=[Depends(auth)])
def forge_list() -> dict:
    from aurora import agt_forge
    return {"requests": list(reversed(agt_forge.requests(cfg)))}


@router.post("/v1/aurora/forge/tick", dependencies=[Depends(auth)])
def forge_tick() -> dict:
    """aurora-rem, every tick: the oldest pending request is built (one at a time)."""
    from aurora import agt_forge
    req = agt_forge.next_pending(cfg)
    if req is None:
        return {"started": None}
    agt_forge.update(cfg, req["id"], status="building", started=time.time())
    return {"started": start_run(f"[forge] {req['need'][:120]}", origin="forge", job=_forge_job(req))["id"]}


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .routines import _start_routine  # noqa: E402
