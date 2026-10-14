# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A project's documentation, ticked by the owner and made by Aurora (ROADMAP 100; owner, 2026-10-14: «delle spunte
da mettere per compatibilità brevetto, blueprint… un bel tasto procedi… sia prima che durante che alla fine posso
sempre renderlo compatibile»).

The ticks are kept with the project (<the user's state>/projects/<project>/docs.json); «Procedi» starts an agent run
with the goal written here; a project carried by Aurora (prj_plan) keeps them in mind at every step. The tools are
the plugins'
  cad      cad_build, cad_drawings (office), cad_blueprint
  patent   patent_document (office), patent_check
and nothing a public office receives carries an AI notice: a filing is signed by its inventor."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import sys_config, sys_users_layout as L

TARGETS = {
    "blueprint": ("Tavole tecniche quotate", "a dimensioned technical drawing (cad_blueprint)"),
    "patent_IT": ("Brevetto Italia (UIBM)", "an Italian patent application (office IT: D.M. 33/2010 art. 22)"),
    "patent_EP": ("Brevetto europeo (EPO)", "a European patent application (office EP: EPC Rules 43, 46, 47, 49)"),
    "patent_US": ("Brevetto USA (provisional)", "a US provisional application (office US: 37 CFR 1.52, 1.72, 1.84)"),
}


def _file(cfg: sys_config.Config, project: str) -> Path:
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", project or ""):
        raise ValueError("a project's name")
    return L.place(cfg, "state", cfg.user) / "projects" / project / "docs.json"


def load(cfg: sys_config.Config, project: str) -> dict:
    try:
        return json.loads(_file(cfg, project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"targets": [], "runs": []}


def save(cfg: sys_config.Config, project: str, targets: list[str], run_id: str = "") -> dict:
    d = load(cfg, project)
    d["targets"] = [t for t in targets if t in TARGETS]
    if run_id:
        d["runs"] = (d.get("runs", []) + [{"at": time.time(), "run_id": run_id, "targets": d["targets"]}])[-20:]
    f = _file(cfg, project)
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def goal(project: str, targets: list[str]) -> str:
    """What the agent is asked when the owner presses «Procedi»."""
    want = [TARGETS[t][1] for t in targets if t in TARGETS]
    offices = [t.split("_")[1] for t in targets if t.startswith("patent_")]
    steps = [f"Project «{project}»: prepare, inside the project, the documentation the owner ticked: " + "; ".join(want) + ".",
             "First read the project (projects tools: tree, README, code, cad/ and patent/ if they exist): an earlier "
             "version is updated, not started again.",
             "If the documents need drawings and the project has no CAD model: design one with cad_build from what the "
             "project is (its parts, each with a reference sign 10, 20, 30…). A software invention may need no CAD "
             "model: then the description refers to no figures."]
    if "blueprint" in targets:
        steps.append("Blueprint: cad_blueprint for the model.")
    for o in offices:
        steps.append(f"Office {o}: cad_drawings(office='{o}') when there is a model; then patent_document(office='{o}', "
                     "drawings=<the model>) — the description recalls every reference sign, the claims are numbered "
                     "and clear (for US a provisional: claims optional), the abstract ≤ 150 words with no other line; "
                     "then patent_check and fix every ❌ it reports, and check again.")
    steps.append("Nothing in these documents may say that an AI made them: they go to a public office, signed by "
                 "the owner. Do not file, pay or send anything: that is the owner's.")
    steps.append("Finish with a report in Italian: the files written, the last check's result, what the owner must "
                 "still do (read, sign, file, fees).")
    return "\n".join(steps)


def plan_note(cfg: sys_config.Config, project: str) -> str:
    """For a project carried by Aurora (prj_plan): the ticks to keep in mind at each step, or nothing."""
    t = load(cfg, project).get("targets", [])
    return ("\nThe owner wants this project's documentation kept compatible with: "
            + ", ".join(TARGETS[x][0] for x in t if x in TARGETS)
            + " — when a step changes the design, say in the report which documents must be made again (they are "
              "made from the project page's «Procedi»).") if t else ""
