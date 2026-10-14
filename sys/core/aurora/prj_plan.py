# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Projects carried by Aurora herself, step by step (ROADMAP 97; owner, 2026-10-13: «aurora avrebbe le capacità di
gestire in autonomia progetti, basterebbe avere agenti che lo facciano senza interazioni da parte mia»).

A project's plan: its goal and its steps, each with the command that proves it done (its tests). In the machine's idle
time (aurora-rem, one task at a time: one GPU, one job) the project agent takes the first open step: it writes the
test first when there is none, then the code, inside the project's folder. Then the CODE decides, not the model: the
step's command runs in the cage (prj_run) and the step is done only when it exits 0. Three failures on one step: the
step is blocked and the owner told. Told too: a step done (🤝: it waits for the owner's «go on»), the plan finished,
and once a day what moved. Whatever leaves the machine (a push, a purchase, a device, her own code) still waits for
the owner: the agent's gates are the same as in the chat (ethics code).

    <the user's state>/projects/<project>/plan.json
    {"goal", "active", "waiting", "steps": [{"title", "test", "status": open|done|blocked, "tries", "runs": [...]}],
     "created", "updated", "told_day"}
Level (AURORA_PROJECT_AUTONOMY, the Autonomy panel's «projects»): 0 🔒 never by herself; 1 🤝 one step, then she
waits for the owner; 2 🚀 step after step until done or blocked."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import sys_config, sys_users_layout as L

NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
TRIES = 3                      # failures on one step before it is blocked and told
GAP_S = 20 * 60                # after a failed attempt, before the next: a failing step is not hammered
SYS_PLAN = (
    "You plan a software project as small steps for an agent that works alone. Each step is one small change that a "
    "command can check: the command runs the step's tests (e.g. \"python -m pytest -q tests/test_parser.py\") and exits "
    "0 only when the step is done. The first step writes the tests of the next ones' behaviour when the project has "
    "none. No step needs the network, a password, a purchase or a person. Reply with JSON only: "
    "[{\"title\": \"…\", \"test\": \"…\"}, …], 3 to 8 steps, titles in Italian.")


def _file(cfg: sys_config.Config, project: str) -> Path:
    if not NAME.fullmatch(project or ""):
        raise ValueError("a project's name")
    return L.place(cfg, "state", cfg.user) / "projects" / project / "plan.json"


def load(cfg: sys_config.Config, project: str) -> dict | None:
    try:
        return json.loads(_file(cfg, project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save(cfg: sys_config.Config, project: str, plan: dict) -> dict:
    f = _file(cfg, project)
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    plan["updated"] = time.time()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)
    return plan


def steps_of(raw) -> list[dict]:
    """The steps as kept: a title and a command each, from the owner's list or the model's JSON."""
    out = []
    for s in raw if isinstance(raw, list) else []:
        if isinstance(s, dict) and str(s.get("title", "")).strip() and str(s.get("test", "")).strip():
            out.append({"title": str(s["title"]).strip()[:300], "test": str(s["test"]).strip()[:2000],
                        "status": s.get("status") if s.get("status") in ("open", "done", "blocked") else "open",
                        "tries": int(s.get("tries") or 0), "runs": list(s.get("runs") or [])[-10:]})
    return out


def draft(llm, goal: str, tree: str = "") -> list[dict]:
    """The steps the model proposes for `goal` (the owner reads and changes them before the plan starts)."""
    out = llm.complete(SYS_PLAN, f"GOAL: {goal}\n\nTHE PROJECT'S FILES NOW:\n{tree[:3000] or '(empty)'}", 1200, think=False)
    m = re.search(r"\[.*\]", str(getattr(out, "answer", out)), re.S)
    try:
        return steps_of(json.loads(m.group(0)) if m else [])
    except ValueError:
        return []


def create(cfg: sys_config.Config, project: str, goal: str, steps: list[dict]) -> dict:
    return save(cfg, project, {"goal": goal.strip()[:4000], "active": False, "waiting": False, "steps": steps_of(steps),
                               "created": time.time(), "told_day": ""})


def next_step(plan: dict | None) -> int | None:
    """The first open step of an active plan that is not waiting for the owner, and nothing blocked before it."""
    if not plan or not plan.get("active") or plan.get("waiting"):
        return None
    for i, s in enumerate(plan.get("steps", [])):
        if s["status"] == "blocked":
            return None
        if s["status"] == "open":
            return i
    return None


def due(cfg: sys_config.Config, projects: list[str], now: float | None = None) -> str | None:
    """The project to work on now (its level allows it, a step is open, no failed attempt in the last GAP_S), or None."""
    if int(cfg["AURORA_PROJECT_AUTONOMY"]) <= 0:
        return None
    now = now or time.time()
    for name in sorted(projects):
        plan = load(cfg, name)
        i = next_step(plan)
        if i is None:
            continue
        last = max((r for s in plan["steps"] for r in s.get("runs", [])), key=lambda r: r.get("at", 0), default=None)
        if not last or last["exit"] == 0 or now - last.get("at", 0) >= GAP_S:
            return name
    return None


def goal_for(plan: dict, project: str, i: int, docs: str = "") -> str:
    """The agent's goal for step i; `docs`: the documentation the owner ticked (prj_docs.plan_note)."""
    s, n = plan["steps"][i], len(plan["steps"])
    done = "\n".join(f"- ✓ {x['title']}" for x in plan["steps"][:i] if x["status"] == "done") or "- (none yet)"
    tried = "\n".join(f"- attempt at {time.strftime('%d/%m %H:%M', time.localtime(r['at']))}: exit {r['exit']}; "
                      f"{r.get('tail', '')[-600:]}" for r in s.get("runs", [])[-2:])
    return (f"Project «{project}», worked on by yourself (no one is watching: do not ask questions). GOAL OF THE "
            f"PROJECT: {plan['goal']}\n\nDONE:\n{done}\n\nNOW, step {i + 1} of {n}: {s['title']}\n"
            f"The step is done when this command exits 0 in the project's folder: `{s['test']}`. If the tests it runs "
            "do not exist yet, write them first, then the code. Work only inside the project's folder (the projects "
            "tools); run the command with run_in_project to check, and fix until it passes. Nothing that leaves the "
            "machine. Finish with a short report in Italian: what you changed and the command's last result."
            + (f"\n\nPREVIOUS ATTEMPTS AT THIS STEP (they failed):\n{tried}" if tried else "") + docs)


def record(cfg: sys_config.Config, project: str, i: int, run: dict, run_id: str, report: str) -> dict:
    """The step's command result after the agent's run: done on exit 0, else one more failure (blocked at TRIES).
    Returns {"plan", "event"}: the event to tell the owner (project.step, project.blocked, project.done) or ""."""
    plan = load(cfg, project)
    s = plan["steps"][i]
    s["runs"] = (s.get("runs", []) + [{"at": time.time(), "run_id": run_id, "exit": run["exit"],
                                       "seconds": run.get("seconds"), "tail": run.get("output", "")[-800:],
                                       "report": report[:600]}])[-10:]
    event = ""
    if run["exit"] == 0:
        s["status"], event = "done", "project.step"
        if all(x["status"] == "done" for x in plan["steps"]):
            plan["active"], event = False, "project.done"
        elif int(cfg["AURORA_PROJECT_AUTONOMY"]) < 2:
            plan["waiting"] = True                         # 🤝: one step, then the owner says «go on»
    else:
        s["tries"] = s.get("tries", 0) + 1
        if s["tries"] >= TRIES:
            s["status"], event = "blocked", "project.blocked"
    return {"plan": save(cfg, project, plan), "event": event}


def daily_line(cfg: sys_config.Config, project: str, now: float | None = None) -> str:
    """Once a day, what moved on the project since yesterday (empty when told today or nothing moved)."""
    plan = load(cfg, project)
    now = now or time.time()
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    if not plan or plan.get("told_day") == day:
        return ""
    runs = [r for s in plan["steps"] for r in s.get("runs", []) if now - r.get("at", 0) < 86400]
    if not runs:
        return ""
    plan["told_day"] = day
    save(cfg, project, plan)
    done = sum(s["status"] == "done" for s in plan["steps"])
    return (f"{project}: {done}/{len(plan['steps'])} passi fatti; nelle ultime 24 ore {len(runs)} tentativi, "
            f"{sum(r['exit'] == 0 for r in runs)} riusciti.")
