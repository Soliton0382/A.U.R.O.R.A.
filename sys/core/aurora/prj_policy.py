# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How Aurora handles a project, chosen when it is made (owner, 2026-10-21: «questo tipo di configurazione si potrebbe
avere quando si creano i progetti, in questo modo uno crea un progetto decidendo come deve essere gestito»).

    {"models": "cloud" | "local", "publish": true | false, "riservato": true | false}

«local»: an agent run that touches the project (a tool given its name, or a goal that names it) goes on with the local
model only from there — what it reads of the project never reaches a cloud model, masked or not (the masking hides
who, not what: an invention would still be read). «publish: false»: the project is never published nor pushed (a
patent not yet filed, a private work). The default is the old way: the cloud as the Models page says, masked; publish
with the owner's approval. «riservato: true» (C636, 20 Nov): no query about the project's subject leaves the machine
(the literature check, prj_novelty, says NOT CHECKED); off by default. C690: the built-in project tools (long_run,
discover_law, novelty_check, run_in_project, the predictions, the proofs) pass the same policy (builtin_guard), a run
is bound to its project (bound), and a run that touches a «riservato» project sends no query at all. C699: every key
that names a project counts (projects_named), two naming two projects are refused, «name» is the projects plugin's.
C704: every project a call names, through any plugin, joins the run's projects, and a run touching a «riservato» one
calls no tool reaching the network (net_refusal). Kept per user, beside the project's plan
(state/projects/<name>/policy.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import sys_config
from . import sys_users_layout as L

DEFAULT = {"models": "cloud", "publish": True, "riservato": False}
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
PUBLISHING = {"project_publish", "project_push"}
# C705: the ONE list of the built-in tools that leave the machine, checked by builtin_net_refusal before they run in a
# run touching a «riservato» project. phone_action: the actions that hand text to a service or a person outside (the
# phone searches, opens a page, asks a map, sends a message, writes a synced calendar); None: every call (the forge
# builds the plugin with a cloud reasoner and the network, the need's text with it). The other built-ins stay on the
# machine (create_artifact: no network; search_vault; the house, by its own rules), or are held local in such a run
# (create_picture: the Models page may give pictures to a cloud provider — C711, painted with local_only when the run
# is local_only or touches a «riservato» project, agt_loop_make._picture), or say NOT CHECKED themselves
# (novelty_check, C636); prove's model call is the agent's own kind (the project's «models», local_only).
BUILTIN_NET = {"phone_action": {"open_url", "web_search", "navigate", "message", "calendar"},
               "request_capability": None}
# O2 (C705): plugin tools with a local effect that still ask the network with what the agent chose (pip → PyPI)
LOCAL_BUT_NET = {("projects", "project_install")}


def _file(cfg: sys_config.Config, project: str) -> Path:
    return L.place(cfg, "state", cfg.user) / "projects" / project / "policy.json"


def load(cfg: sys_config.Config, project: str) -> dict:
    if not NAME.fullmatch(project or ""):
        return dict(DEFAULT)
    try:
        d = json.loads(_file(cfg, project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT)
    return {"models": "local" if d.get("models") == "local" else "cloud", "publish": d.get("publish") is not False,
            "riservato": d.get("riservato") is True}


def save(cfg: sys_config.Config, project: str, spec: dict) -> dict:
    if not NAME.fullmatch(project or ""):
        raise ValueError("a project's name")
    keep = load(cfg, project)["riservato"]          # a page that does not show it never clears it
    d = {"models": "local" if spec.get("models") == "local" else "cloud", "publish": spec.get("publish") is not False,
         "riservato": spec.get("riservato") is True if "riservato" in spec else keep}
    f = _file(cfg, project)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d), encoding="utf-8")
    return d


KEYS = ("project", "name")          # the argument keys that name a project (C699): «name» only for the projects plugin


def projects_named(plugin: str, tool: str, args: dict) -> dict[str, str]:
    """C699: every key of the call's arguments that names a project, with the name it gives: «project» for every
    plugin and the built-ins, «name» too for the projects plugin (the key its tools work on)."""
    keys = KEYS if plugin in ("projects", "builtin") else ("project",)
    return {k: str(args[k]).strip() for k in keys if isinstance(args, dict) and args.get(k) not in (None, "")}


def project_of(plugin: str, tool: str, args: dict) -> str:
    """The project a tool call works on: «name» for the projects plugin (C699: the key its tools use — pydantic drops
    an extra «project»), «project» for the others (cad, circuits, patent, vista, run_in_project…); "" for none.
    Two keys naming two projects: ValueError (guard refuses the call)."""
    named = projects_named(plugin, tool, args)
    if len(set(named.values())) > 1:
        raise ValueError(", ".join(f"{k}={v!r}" for k, v in sorted(named.items())))
    if plugin == "projects":
        return named.get("name") or named.get("project", "")
    return named.get("project") or named.get("name", "")


def _seen(agent, plugin: str, tool: str, args: dict) -> None:
    """C704: every project a call names joins the run's projects (scope), whatever plugin it goes through."""
    names = set(projects_named(plugin, tool, args).values())
    if names and isinstance(getattr(agent, "projects", None), set):
        agent.projects.update(n for n in names if NAME.fullmatch(n))


def net_refusal(agent, plugin: str, tool: str, effect: str, manifest: dict | None, project: str = "") -> str:
    """C704: a run that touches a «riservato» project calls no tool that reaches the network — a web search, a page
    fetched, a plugin with a URL, a post — in the same run (the projects plugin's local tools and the house's own
    devices excepted). "" to go on."""
    from . import agt_asked
    m = manifest if isinstance(manifest, dict) else {}
    if not agt_asked.reaches_network(m) or agt_asked._house(m):
        return ""
    if plugin == "projects" and effect in ("read", "write_local") and (plugin, tool) not in LOCAL_BUT_NET:
        return ""
    reserved = reserved_in(agent, project)
    if not reserved:
        return ""
    return (f"REFUSED: this run works on the reserved project {reserved}: no tool that reaches the network ({plugin}."
            f"{tool}) is called in it, so nothing of its subject leaves the machine. Go on without it, or say so.")


def builtin_net_refusal(agent, name: str, args: dict) -> str:
    """C705: a built-in of BUILTIN_NET in a run touching a «riservato» project is refused before it runs. "" to go on."""
    if name not in BUILTIN_NET:
        return ""
    acts = BUILTIN_NET[name]
    if acts is not None and str((args or {}).get("action", "")) not in acts:
        return ""
    reserved = reserved_in(agent)
    if not reserved:
        return ""
    what = f"{name}.{args.get('action')}" if acts is not None else name
    return (f"REFUSED: this run works on the reserved project {reserved}: {what} leaves the machine, so it is not done "
            "in it (nothing of its subject goes out). Go on without it, or tell the owner to do it in another chat.")


def _local(agent, project: str, emit) -> None:
    if not getattr(agent, "local_only", False):
        agent.local_only = True
        emit("agent.local", {"plugin": project, "why": "the project is handled with the local model only"})


def at_start(agent, goal: str, emit) -> None:
    """A goal that names a «local» project: the whole run local, from its first step. The projects the goal names are
    kept (agent.named_projects): a phase's goal names its project (prj_conduct.DRAFT), and the run is bound to them
    (C690, see bound)."""
    cfg = agent.cfg
    try:
        base = cfg.path("AURORA_PROJECTS_DIR")
        names = [p.name for p in base.iterdir() if p.is_dir()] if base.is_dir() else []
    except OSError:
        names = []
    named = {n for n in names if re.search(rf"(?<![\w.-]){re.escape(n)}(?![\w-])", goal or "")}
    agent.named_projects = named
    for n in sorted(named):
        if load(cfg, n)["models"] == "local":
            _local(agent, n, emit)
            return


def bound(agent) -> set[str]:
    """C690: the projects a run is bound to, as prj_act binds a conductor's run to its project: the one the caller
    fixed (agent.bound_project: a project's phase) or else those its goal names. Empty: a run of no project (the
    chat's agent asked about none), free to name one."""
    fixed = str(getattr(agent, "bound_project", "") or "")
    if fixed:
        return {fixed}
    return set(getattr(agent, "named_projects", None) or ())


def scope(agent) -> set[str]:
    """Every project the run has to do with: bound, named by the goal, worked on so far."""
    return bound(agent) | set(getattr(agent, "named_projects", None) or ()) | set(getattr(agent, "projects", None) or ())


def reserved_in(agent, project: str = "") -> str:
    """C690: the first «riservato» project the run touches (the one asked about included), "" when none: a phase of a
    reserved project never sends a query, whatever project its call names."""
    for n in sorted(scope(agent) | ({project} if project else set())):
        if NAME.fullmatch(n) and load(agent.cfg, n)["riservato"]:
            return n
    return ""


def builtin_guard(agent, tool: str, args: dict, emit) -> str:
    """C690: the built-in project tools (long_run, discover_law, novelty_check, run_in_project, the predictions, the
    proofs) under the same policy as the plugin's: bound to the run's project, a «local» project makes the run local
    BEFORE its log or its results come back to the model. "" to go on."""
    try:
        project = project_of("builtin", tool, args)
    except ValueError as e:                          # C699: two keys, two projects
        return f"REFUSED: the call names more than one project ({e}); name one."
    if not project:
        return ""                                    # the tool itself says it needs one
    b = bound(agent)
    if b and project not in b | set(getattr(agent, "created_projects", None) or ()):   # one it made itself: its own
        return (f"REFUSED: this run works on the project {', '.join(sorted(b))}; {tool} on another project ({project}) "
                "is not done here. Work on the run's own project.")
    return guard(agent, "builtin", tool, {"project": project}, emit)


def guard(agent, plugin: str, tool: str, args: dict, emit, effect: str = "", manifest: dict | None = None) -> str:
    """Before a tool call: a «local» project makes the run local; a «never publish» one refuses publishing; two keys
    naming two projects refused (C699); in a run touching a «riservato» project no tool reaching the network (C704,
    with the plugin's manifest). "" to go on."""
    _seen(agent, plugin, tool, args)
    try:
        project = project_of(plugin, tool, args)
    except ValueError as e:
        return (f"REFUSED: the call names more than one project ({e}): a tool works on one project, named once. "
                "Call it again with that project only.")
    if manifest is not None and (refused := net_refusal(agent, plugin, tool, effect, manifest, project)):
        return refused
    if not project:
        return ""
    from . import prj_prereg
    if tool in ("project_write_file", "project_edit_file"):
        path = str(args.get("path", ""))
        if prj_prereg.locked(path):
            return prj_prereg.refusal(path)                  # frozen predictions and reviews: Aurora's (N142)
        if ".venv" in path.replace("\\", "/").split("/"):      # C629: a .pth there ran in project_install
            return f"REFUSED: {path} is in the project's .venv, which only project_install writes"
        from . import prj_provenance                         # C632: a data table the agent writes is never evidence
        try:
            root = agent.cfg.path("AURORA_PROJECTS_DIR") / project
        except Exception:                                # no projects folder here: the path as written
            root = None
        prj_provenance.record_path(agent.cfg, project, path, "write", root)
    policy = load(agent.cfg, project)
    if tool in PUBLISHING and not policy["publish"]:
        return (f"REFUSED: the project {project} is never published (its owner chose so when it was made). Do not "
                "try another way; say it stays local.")
    if policy["models"] == "local":
        _local(agent, project, emit)
    return ""
