# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""⏳ The long runs' tool (ROADMAP N145): its answers for a model, the conductor's and the agent's calls, the agent's form;
imported by prj_longrun only (at its end), never first.
prj_longrun re-exports these names; the runs themselves are there."""
from __future__ import annotations

import json

from . import sys_config
from .prj_longrun import GONE, NAME, TOOL, enabled, limits, runs, start, status, stop, sweep


def text(st: dict) -> str:
    lim = st.get("limits") or {}
    out = [f"long run {st['id']} «{st.get('title', '')}»: {str(st.get('status', '')).upper()}"
           + (f" — {st['why']}" if st.get("why") else ""),
           f"attempts {st.get('attempts')}, used {st.get('used_s')} of {lim.get('wall_s')} s; exit {st.get('exit')}"]
    if st.get("progress"):
        out.append(f"progress: {st['progress']}")
    if st.get("finished"):
        out.append(f"outputs: {st.get('outputs_count', 0)} files hashed, manifest SHA-256 {st.get('manifest_sha256')}; "
                   f"report {st.get('report')}" + (f"; frozen entry {st['frozen']} {st.get('integrity')}"
                                                    if st.get("frozen") else ""))
    if st.get("log_tail"):
        out.append("log's end:\n" + st["log_tail"][-1500:])
    if st.get("status") not in GONE:
        out.append("Still going: ask its status later; do not wait for it in a loop.")
    return "\n".join(out)


def act(cfg: sys_config.Config, project: str, a: dict, readonly: bool = False) -> str:
    """The tool's answer (the conductor's and the agent's); a read-only run (the referee) may only look."""
    action = str(a.get("action") or "").strip()
    if not enabled(cfg):                              # C667: off means off — «status» and «list» too (through
        return "REFUSED: long runs are off (AURORA_LONGRUN_ENABLED)"    # sweep they resumed runs)
    if action in ("start", "stop") and readonly:
        return f"REFUSED: {NAME} {action} is not allowed in a read-only run"
    try:
        if action == "start":
            st = start(cfg, project, str(a.get("command") or ""), limits(cfg, a), str(a.get("title") or ""),
                       a.get("outputs") or [], a.get("code_files") or [])
            return text(st) + "\nStarted: follow it with action «status»."
        if action in ("status", "stop"):
            rid = str(a.get("run") or "").strip()
            if action == "stop":
                stop(cfg, project, rid)
            sweep(cfg, project)
            return text(status(cfg, project, rid))
        if action == "list":
            sweep(cfg, project)
            rows = runs(cfg, project)
            return "\n".join(f"{r['id']} {r['status']} «{r.get('title', '')}» {r.get('used_s')} s"
                             for r in rows) or "(no long runs)"
        return "ERROR: action is one of start, status, stop, list"
    except ValueError as e:
        return f"REFUSED: {e}"
    except RuntimeError as e:
        return f"ERROR: {e}"


def offered(cfg: sys_config.Config, goal: str) -> list[dict]:
    """The tool in the agent's form («project» added), in a project's phase when long runs are on."""
    if not enabled(cfg) or not any(w in (goal or "") for w in (NAME, "freeze_predictions")):
        return []
    s = json.loads(json.dumps(TOOL["inputSchema"]))
    s["properties"] = {"project": {"type": "string", "description": "the project's name"}, **s["properties"]}
    s["required"] = ["project", *s["required"]]
    return [{"name": NAME, "description": TOOL["description"], "input_schema": s}]


def agent_call(agent, a: dict) -> str:
    project = str(a.get("project") or a.get("name") or "")
    if not project:
        return f"ERROR: {NAME} needs «project» (the project's name) and «action»."
    out = act(agent.cfg, project, a)
    if isinstance(getattr(agent, "projects", None), set):
        agent.projects.add(project)
    return out
