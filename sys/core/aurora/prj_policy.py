# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How Aurora handles a project, chosen when it is made (owner, 2026-10-21: «questo tipo di configurazione si potrebbe
avere quando si creano i progetti, in questo modo uno crea un progetto decidendo come deve essere gestito»).

    {"models": "cloud" | "local", "publish": true | false}

«local»: an agent run that touches the project (a tool given its name, or a goal that names it) goes on with the local
model only from there — what it reads of the project never reaches a cloud model, masked or not (the masking hides
who, not what: an invention would still be read). «publish: false»: the project is never published nor pushed (a
patent not yet filed, a private work). The default is the old way: the cloud as the Models page says, masked; publish
with the owner's approval. Kept per user, beside the project's plan (state/projects/<name>/policy.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import sys_config
from . import sys_users_layout as L

DEFAULT = {"models": "cloud", "publish": True}
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
PUBLISHING = {"project_publish", "project_push"}


def _file(cfg: sys_config.Config, project: str) -> Path:
    return L.place(cfg, "state", cfg.user) / "projects" / project / "policy.json"


def load(cfg: sys_config.Config, project: str) -> dict:
    if not NAME.fullmatch(project or ""):
        return dict(DEFAULT)
    try:
        d = json.loads(_file(cfg, project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT)
    return {"models": "local" if d.get("models") == "local" else "cloud", "publish": d.get("publish") is not False}


def save(cfg: sys_config.Config, project: str, spec: dict) -> dict:
    if not NAME.fullmatch(project or ""):
        raise ValueError("a project's name")
    d = {"models": "local" if spec.get("models") == "local" else "cloud", "publish": spec.get("publish") is not False}
    f = _file(cfg, project)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d), encoding="utf-8")
    return d


def project_of(plugin: str, tool: str, args: dict) -> str:
    """The project a tool call works on: «project» (cad, circuits, patent, run_in_project), «name» (projects)."""
    if args.get("project"):
        return str(args["project"])
    return str(args.get("name", "")) if plugin == "projects" else ""


def _local(agent, project: str, emit) -> None:
    if not agent.local_only:
        agent.local_only = True
        emit("agent.local", {"plugin": project, "why": "the project is handled with the local model only"})


def at_start(agent, goal: str, emit) -> None:
    """A goal that names a «local» project: the whole run local, from its first step."""
    cfg = agent.cfg
    try:
        base = cfg.path("AURORA_PROJECTS_DIR")
        names = [p.name for p in base.iterdir() if p.is_dir()] if base.is_dir() else []
    except OSError:
        names = []
    for n in names:
        if re.search(rf"(?<![\w.-]){re.escape(n)}(?![\w-])", goal) and load(cfg, n)["models"] == "local":
            _local(agent, n, emit)
            return


def guard(agent, plugin: str, tool: str, args: dict, emit) -> str:
    """Before a tool call: a «local» project makes the run local; a «never publish» one refuses publishing. "" to go on."""
    project = project_of(plugin, tool, args)
    if not project:
        return ""
    policy = load(agent.cfg, project)
    if tool in PUBLISHING and not policy["publish"]:
        return (f"REFUSED: the project {project} is never published (its owner chose so when it was made). Do not "
                "try another way; say it stays local.")
    if policy["models"] == "local":
        _local(agent, project, emit)
    return ""
