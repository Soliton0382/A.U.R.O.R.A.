# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own updates and the commands to run by hand: what is new, the check, the update started (split from
api/knowledge (ROADMAP D10): no monoliths)."""
from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time

from aurora import sys_config
from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log, note, start_run

from .users import admin_only  # noqa: E402

router = APIRouter()

@router.get("/v1/aurora/update", dependencies=[Depends(auth)])
def update_info() -> dict:
    from aurora import sys_commands, sys_update
    return {**sys_update.last(cfg), "mode": cfg["AURORA_UPDATE_MODE"], "by_hand": sys_commands.by_hand(cfg)}


@router.get("/v1/aurora/commands", dependencies=[Depends(admin_only)])
def command_cards(request: Request) -> dict:
    """What only the owner can do from a shell, with the command for this system (roadmap 74)."""
    from aurora import sys_commands
    return {"cards": sys_commands.cards(cfg, request.headers.get("accept-language", "it")),
            "by_hand": sys_commands.by_hand(cfg)}


@router.post("/v1/aurora/commands/{card}/verify", dependencies=[Depends(admin_only)])
async def command_verify(card: str) -> dict:
    """The owner says it is done: Aurora checks."""
    from aurora import sys_commands
    try:
        return await asyncio.to_thread(sys_commands.verify, cfg, card)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


def settle_updates(info: dict | None = None) -> int:
    """Up to date (by the WebUI, or by hand: git pull and the installer): the update approvals still open are closed —
    the owner's colleague, 9 Oct: «ho completato l'update ma continua a dirmi che c'è un update da fare». Called at
    every check that finds nothing new and at the API's start (the state checked again without fetching)."""
    from aurora import sys_update
    from aurora.sys_approvals import Approvals
    if info is None:
        info = sys_update.check(cfg, fetch=False)
    if info.get("error") or info.get("commits"):
        return 0
    a = Approvals(cfg)
    open_ = [x for x in a.list("pending") if x["kind"] == "update"]
    for x in open_:
        a.update(x["id"], status="closed", decided=time.time(), note=f"already up to date ({info.get('here', '')})")
    if open_:
        log.info("audit: %d update approvals closed: Aurora is up to date (%s)", len(open_), info.get("here", ""))
    return len(open_)


@router.post("/v1/aurora/update/check", dependencies=[Depends(admin_only)])
async def update_check() -> dict:
    """Fetch and compare; new commits become a notification and an approval (notify), or are applied (auto, when safe)."""
    from aurora import sys_update
    from aurora.sys_approvals import Approvals
    info = await asyncio.to_thread(sys_update.check, cfg)
    if not info.get("error") and not info.get("commits"):
        settle_updates(info)
    if info.get("error") or not info.get("commits"):
        return info
    pending = [a for a in Approvals(cfg).list("pending") if a["kind"] == "update"]
    if pending and pending[-1]["action"].get("to") == info["there"]:
        return {**info, "approval": pending[-1]["id"]}           # already asked for this version
    text = sys_update.changelog(info, "it")
    note("update", "update.available", {"text": f"{info['behind']} novità: " + "; ".join(c["subject"] for c in info["commits"])[:300],
                                         "to": info["there"]})
    if cfg["AURORA_UPDATE_MODE"] == "auto" and info["safe"]:
        from aurora import sys_autonomy
        sys_autonomy.log(cfg, "updates", f"update to {info['there']} ({info['behind']} commits) started by herself")
        return {**info, "run_id": _start_update(info["there"])}
    item = Approvals(cfg).request("update", "code_change", f"Aggiornamento: {info['behind']} commit fino a {info['there']}",
                                  text, {"commits": info["commits"], "files": info["files"], "protected": info["protected"]},
                                  {"to": info["there"]})
    return {**info, "approval": item["id"]}


def _env_add_missing() -> list[str]:
    """Keys a new schema declares and .env lacks get their recommended value (an update must not stop Aurora)."""
    added = sys_config.add_missing()
    if added:
        log.info("audit: update added settings with their recommended value: %s", ", ".join(added))
    return added


def _rewrite_caddyfile() -> str:
    """The Caddyfile written again from the settings before aurora-https restarts: an update can move a setting of
    Caddy's (C450, 29 Oct: the admin on a socket in the .env, the Caddyfile still on 127.0.0.1:2019). In a new
    process: this one still runs the code from before the update."""
    import sys
    code = "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config, net_https; net_https.write(sys_config.get())"
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=str(cfg.root), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        r = None
        why = str(e)
    if r is not None and r.returncode == 0:
        return "written"
    why = (r.stderr or r.stdout).strip()[-300:] if r is not None else why
    log.warning("update: the Caddyfile not written again (Caddy keeps the old one): %s", why)
    return f"kept: {why}"


def _runs_here(unit: str) -> bool:
    """The unit runs this folder's code (its ExecStart names cfg.root): units of the same name may be another copy's."""
    try:
        out = subprocess.run(["systemctl", "show", unit, "-p", "ExecStart"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f"{cfg.root}/" in out


def _start_update(to: str) -> str:
    def job(q, emit, run_id):
        from aurora import sys_update
        from aurora.kno_answer import Answer
        out = sys_update.apply(cfg, emit)
        if out.get("applied"):
            out["settings_added"] = _env_add_missing()
            mine = [u for u in UNITS if _runs_here(u)]          # a second copy never restarts another's services (C140)
            out["restarted"] = mine
            if "aurora-https" in mine:
                out["caddyfile"] = _rewrite_caddyfile()
            if [u for u in mine if u != "aurora-api"]:
                threading.Timer(2.0, lambda: subprocess.run(["systemctl", "restart", "--no-block",
                                                             *[u for u in mine if u != "aurora-api"]], capture_output=True)).start()
            if "aurora-api" in mine:
                threading.Timer(4.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                            capture_output=True)).start()
        note("update", "update.done", {"ok": out.get("applied", False), "text": out.get("reason", f"aggiornata a {to}")})
        return Answer(run_id, q, json.dumps(out, ensure_ascii=False), False, mode="agent")
    return start_run(f"[update] {to}", origin="update", job=job)["id"]


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .agents import UNITS  # noqa: E402
