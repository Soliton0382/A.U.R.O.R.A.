# The owner's own: Evidentia's lead worker (never published: local/). Owner, 10 Nov: «si scatenano agenti investigativi
# che preparano il terreno… routine che procedono in modo indipendente, come le sinapsi». At a routines' tick, when
# nobody is using Aurora and no worker's run is going, it takes the next open lead from Evidentia (a lease and its
# token), runs one of Aurora's agents with the lead's agent prompt and Evidentia's tools only, and lets that agent
# report the lead itself (the evidence is checked by Evidentia, quote by quote). Nothing of it is remembered: Evidentia's
# MCP server has «memory»: false (C551). A lead the worker could not close twice is dropped, with the reason, so the
# queue never turns on itself. On/off and the last runs: <status>/evidentia_worker.json (the 🔁 Routine page).
from __future__ import annotations

import json
import time

import httpx

from aurora import sys_config

SOCK = "/var/lib/evidentia-api/evidentia.sock"   # Evidentia's API (its unit evidentia-api, aurora-root install evidentia)

PLUGIN = "evidentia"
EVERY_S = 10 * 60                 # at most one lead started every ten minutes
TRIES = 2
STEPS, MINUTES = 24, 20


def _file(cfg) -> "object":
    return cfg.path("AURORA_STATUS_DIR") / "evidentia_worker.json"


def state(cfg=None) -> dict:
    cfg = cfg or sys_config.get()
    try:
        return {"on": False, "tries": {}, "last": [], **json.loads(_file(cfg).read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {"on": False, "tries": {}, "last": []}


def save(st: dict, cfg=None) -> None:
    cfg = cfg or sys_config.get()
    f = _file(cfg)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def hand_over(case: str | None, who: str, trail: list) -> None:
    """The run's steps into the case file's audit trail on Evidentia's side (owner, 27 Nov): kept there, not here;
    a run with no case (a lead without one) keeps none. Never raises: a trail not written is logged."""
    if not case or not trail:
        return
    for i in range(0, len(trail), 500):
        try:
            _ask("POST", f"/cases/{case}/trace", {"who": who, "entries": trail[i:i + 500]})
        except Exception:                               # noqa: BLE001 — the answer is given anyway; said in the log
            import logging
            logging.getLogger("aurora.evidentia").warning("a case's audit trail not written (%d steps)", len(trail))
            return


def _whose() -> dict:
    """R15: the archive is the user's whose work this is (the run's, the request's). The admin is always Evidentia's
    owner: said as no user (the archive as it was), whatever the names of their accounts."""
    from aurora import sys_context
    from aurora.api.core import _admin
    u = sys_context.user() or ""
    return {"X-Evidentia-User": "" if not u or u == _admin() else u}


def _ask(method: str, path: str, body: dict | None = None) -> dict:
    with httpx.Client(transport=httpx.HTTPTransport(uds=SOCK), base_url="http://evidentia", timeout=60, headers=_whose()) as c:
        r = c.request(method, path, json=body)
    return r.json()


def tick(who) -> None:
    """One look at a routines' tick: the owner's only, when the worker is on and nothing of it is running."""
    from aurora.api.core import _admin, _runs, start_run
    if who not in (None, _admin()):
        return
    cfg = sys_config.get()
    st = state(cfg)
    if not st.get("on") or time.time() - float(st.get("started_at") or 0) < EVERY_S:
        return
    if any(r.get("origin") == "evidentia" and not r["done"] for r in _runs.values()):
        return
    try:
        got = _ask("POST", "/leads/claim", {"worker": "aurora"})
    except (httpx.HTTPError, ValueError):
        return
    lead, prompt = got.get("lead"), got.get("prompt")
    if not lead or not prompt:
        return
    tries = st["tries"].get(str(lead["id"]), 0)
    if tries >= TRIES:                                 # twice and not closed: dropped, said why, never a loop
        _ask("DELETE", f"/leads/{lead['id']}", {"why": f"Aurora's worker could not close it in {TRIES} tries"})
        st["last"] = ([{"lead": lead["id"], "at": time.time(), "result": "dropped"}] + st["last"])[:20]
        save(st, cfg)
        return
    st["tries"][str(lead["id"])] = tries + 1
    st["started_at"] = time.time()
    save(st, cfg)
    start_run(f"[evidentia] 🧭 #{lead['id']} {lead['what'][:80]}", origin="evidentia", job=_job(lead, prompt))


def _job(lead: dict, prompt: str):
    def job(q, emit, run_id):
        from aurora.agt_loop import Agent
        from aurora.api.core import _runs, give_way, note, pipeline, plugin_host
        cfg = sys_config.get()
        agent = Agent(pipeline(), cfg, notify=lambda e, p: note("evidentia", e, p), host=plugin_host())
        agent.allow = {PLUGIN}                         # Evidentia's tools only: nothing of the house, nothing online
        agent.loop_tools = set()                       # nor Aurora's own (vault, people, forge…): audit A1, 11 Nov
        agent.local_only = True                            # the archive's text never to a cloud model (A2)
        agent.no_trace = True                               # nothing of the archive in Aurora's trace files (review M2)
        trail: list = []
        agent.audit_sink = trail.append                     # the steps, handed to the case file's audit trail below
        agent.between = give_way                       # the owner's question goes first (A4)
        # 🛑 stops it, and so does switching the worker off on the 🔁 page (before: only the next tick)
        agent.cancelled = lambda: bool((_runs.get(run_id) or {}).get("cancel")) or not state(cfg).get("on")
        agent.max_steps, agent.max_min = STEPS, MINUTES
        goal = (f"{prompt}\n\nTHIS LEAD: number {lead['id']}, token {lead['token']}. Work it with the tools of "
                f"Evidentia only, then close it with report_lead(lead={lead['id']}, token=\"{lead['token']}\", status, "
                "summary, evidence). Do not open other leads unless the evidence asks for one (open_lead, parent).")
        try:
            ans = agent.run(goal, emit, run_id, "Evidentia's lead worker: read only on the archive, report the lead.")
        finally:
            hand_over(lead.get("case"), f"lead worker #{lead.get('id')}", trail)
        try:
            now = _ask("GET", f"/leads/{lead['id']}")
        except (httpx.HTTPError, ValueError):
            now = {}
        st = state(cfg)
        st["last"] = ([{"lead": lead["id"], "at": time.time(), "run": run_id, "result": now.get("status", "?"),
                        "steps": len(agent.ledger)}] + st["last"])[:20]
        if now.get("status") in ("done", "cold"):
            st["tries"].pop(str(lead["id"]), None)
        save(st, cfg)
        return ans
    return job
