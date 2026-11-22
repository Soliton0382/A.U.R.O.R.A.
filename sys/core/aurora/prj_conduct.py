# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧑‍🔬 A conductor inside every project (ROADMAP N39; owner, 21 Oct: «avere la stessa possibilità dentro ogni
progetto sarebbe fantastico»).

The owner writes in plain words on the project's page. The conductor turns them into one phase's goal, after reading
the project's open items, its documents and the conversation so far; the owner sees the goal, may change it, and starts
it with one click (owner, 22 Oct: «mostra e poi un clic»). The agent runs the phase; when it ends, the conductor reads
its report and answers: what was done, what does not hold, and the questions only the owner can decide, as choices
(a / b / c, one recommended). The conversation is kept per user beside the project's policy
(state/projects/<name>/conduct.jsonl), each entry one line sealed with the user's key (N64: the owner's words, the
drafted goals and the replies; a line of before is read as it is, and sealed when update() writes the file again). A
«local» project is conducted by the local model only, like its runs.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from . import (prj_browse, prj_discover, prj_longrun, prj_novelty, prj_policy, prj_prereg, prj_proof, sys_config,
               sys_seal)
from . import sys_users_layout as L

OPEN_ITEMS = ("docs/DA_FARE.md", "DA_FARE.md")
KEEP = 12                       # turns of the conversation the conductor reads again
ITEMS_CHARS = 6000              # the open items it reads: the end of the file, where the newest phases are

DRAFT = """You conduct a project for its owner, like a lead engineer who drives an autonomous agent.
The owner wrote a request in plain words. Turn it into ONE phase's goal for the agent, in the owner's language.
The goal must: name the project «{name}» and its policy ({policy}); say which files to read first (from the open
items and documents below); state the request precisely, as numbered points, keeping the owner's own terms and
constraints; ask the agent to search Aurora's vault first (tool search_vault: its documents are newer than
the models' training) for findings that bear on the request, to apply those that fit and cite them, and to say when the
vault has nothing; ask the agent to verify every result (a check against a known case, convergence, a second method),
never to give a number it did not compute or did not declare as an assumption, to keep each run under 100 s; say which
document to write (a new one takes the next number in docs/; a document the request names is changed in place, never
copied to a new file), to update the open-items file, and to end with a summary
that lists what it did, what does not hold and what is still open. Never ask the agent to commit or to run git: the
commits are the owner's («📦 Pubblica», «💾 Salva»; C718), the agent's .git is read only. Do not invent results, do not answer the request
yourself. Reply with the goal text only."""

REVIEW = """You conduct a project for its owner. The agent just finished a phase; below are the goal and its report.
Answer the owner in their language ({lang}), short and plain, with these parts:
1. What was done: the results, with the numbers exactly as the report gives them (none of your own).
2. What does not hold: errors the agent found, assumptions, limits, anything the report says was not verified.
3. Decisions for the owner: only those the owner alone can make, each as choices a / b / c with one recommended and
   why. If there is nothing to decide, say what the next phase should be.
Never claim more than the report says. Below the report is what the project's folder shows now, read by Aurora and
not by the agent: where the report claims a file, a section or a commit the folder does not show, say so first, under
part 2, plainly («the report says X, the folder shows Y») — the folder is right. The frozen predictions' balance there
is Aurora's own reading of prereg/: report it as it is (failed predictions and entries «changed after freeze» under
part 2), never the agent's version of it."""

# N142, «avviso»: the draft asks the agent to freeze its predictions before an experiment (prj_prereg)
DRAFT_RULE = ("\nThe goal must also say, as its own numbered point: before running any experiment whose result you will "
              "report, freeze its predictions with freeze_predictions; close them afterwards with close_predictions; "
              "report every failed prediction.")
# N143: a theorem is claimed proved only through Aurora's Lean check
PROOF_RULE = ("\nIf the request asks for a theorem or a proof, the goal must also say: a theorem is claimed proved only "
              "when proof_check says PROVED for its .lean file.")
# N147: a law found in data is claimed discovered only through Aurora's discovery engine
DISCOVER_RULE = ("\nIf the request asks to find a law or a formula in data, the goal must also say: a law is claimed "
                 "discovered only when discover_law says DISCOVERED.")
# N145, N146: experiments of hours through long_run; a result called new only after novelty_check
LONGRUN_RULE = ("\nIf an experiment may run longer than a command's limit, the goal must also say: start it with long_run "
                "with its limits declared and report it only from its status once it has ended.")
NOVELTY_RULE = ("\nIf the request may produce a result called new, the goal must also say: run novelty_check on it first, and "
                "say «not found in the literature checked» rather than «new».")


def draft_system(cfg: sys_config.Config, project: str, policy: str) -> str:
    """The drafting prompt, with the frozen-predictions rule unless AURORA_PREREG_MODE is off."""
    return (DRAFT.format(name=project, policy=policy) + (DRAFT_RULE if prj_prereg.rule(cfg) else "")
            + (PROOF_RULE if prj_proof.rule(cfg) else "") + (DISCOVER_RULE if prj_discover.rule(cfg) else "")
            + (LONGRUN_RULE if prj_longrun.rule(cfg) else "") + (NOVELTY_RULE if prj_novelty.rule(cfg) else ""))


def _file(cfg: sys_config.Config, project: str) -> Path:
    return L.place(cfg, "state", cfg.user) / "projects" / project / "conduct.jsonl"


def _label(project: str) -> str:
    """What an entry's line is bound to: this project's conversation with the conductor."""
    return f"projects/{project}/conduct.jsonl"


def _line(cfg: sys_config.Config, project: str, e: dict) -> str:
    return sys_seal.seal_text(cfg, json.dumps(e, ensure_ascii=False), _label(project), cfg.user) + "\n"


def _project(cfg: sys_config.Config, project: str) -> Path:
    if not prj_policy.NAME.fullmatch(project or ""):
        raise ValueError("bad project name")
    p = cfg.path("AURORA_PROJECTS_DIR") / project
    if not p.is_dir():
        raise ValueError("no such project")
    return p


def history(cfg: sys_config.Config, project: str) -> list[dict]:
    try:
        lines = _file(cfg, project).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(sys_seal.open_text(cfg, line, _label(project), cfg.user)))   # a line of before: as it is
        except ValueError:
            pass
    return out


def add(cfg: sys_config.Config, project: str, kind: str, text: str, **extra) -> dict:
    """One entry: kind «ask» (the owner), «goal» (a draft), «run» (started), «reply» (the conductor's answer)."""
    f = _file(cfg, project)
    f.parent.mkdir(parents=True, exist_ok=True)
    e = {"id": uuid.uuid4().hex[:10], "t": time.time(), "kind": kind, "text": text, **extra}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(_line(cfg, project, e))
    return e


def update(cfg: sys_config.Config, project: str, entry_id: str, **changes) -> dict | None:
    items, hit = history(cfg, project), None
    for e in items:
        if e.get("id") == entry_id:
            e.update(changes)
            hit = e
    if hit is not None:
        _file(cfg, project).write_text("".join(_line(cfg, project, e) for e in items), encoding="utf-8")
    return hit


def context(cfg: sys_config.Config, project: str) -> str:
    """What the conductor reads before drafting: open items (their end), the documents' names, the last turns."""
    p = _project(cfg, project)
    parts = []
    for rel in OPEN_ITEMS:
        try:
            parts.append(f"## {rel} (end)\n" + (p / rel).read_text(encoding="utf-8", errors="replace")[-ITEMS_CHARS:])
            break
        except OSError:
            continue
    docs = sorted(x.name for x in (p / "docs").iterdir() if x.is_file()) if (p / "docs").is_dir() else []
    parts.append("## docs/\n" + ", ".join(docs[-60:]))
    turns = [f"[{e['kind']}] {e['text'][:1500]}" for e in history(cfg, project)[-KEEP:]]
    if turns:
        parts.append("## conversation so far\n" + "\n\n".join(turns))
    return "\n\n".join(parts)


def local(cfg: sys_config.Config, project: str) -> bool:
    return prj_policy.load(cfg, project)["models"] == "local"


def model(cfg: sys_config.Config, project: str, pipeline):
    """The local model for a «local» project, else the agent's model as the owner assigned it (masked)."""
    return pipeline.llm if local(cfg, project) else pipeline._for("agent")


def draft(cfg: sys_config.Config, project: str, words: str, llm, fallback=None) -> dict:
    """The owner's words → a phase goal, kept as a draft until the owner starts it. `fallback`: the model that drafts
    when `llm` fails (the cloud judge out of its session: the local model)."""
    ctx = context(cfg, project)
    pol = prj_policy.load(cfg, project)
    policy = ("local model only" if pol["models"] == "local" else "masked cloud allowed") + \
        ("" if pol["publish"] else ", never published nor pushed")
    add(cfg, project, "ask", words)
    system, user = draft_system(cfg, project, policy), f"{ctx}\n\n## the owner's request\n{words}"
    try:
        out = llm.complete(system, user, 2500)
    except Exception:
        if fallback is None:
            raise
        out = fallback.complete(system, user, 2500)
    return add(cfg, project, "goal", out.answer.strip(), status="draft")


FILES = re.compile(r"`([\w./-]+\.(?:md|py|json|csv|txt|scad|stl|tex))`")


def folder_facts(cfg: sys_config.Config, project: str, goal: str, since: float | None = None) -> str:
    """C608: what the folder shows, beside the agent's own report — each file the goal names (there or not, its size,
    its section headings), the work not committed and the last commits. The judge read the report alone: on 17 Nov a
    local phase reported «table copied, reading written, committed» over a document holding three lines of model and
    no commit, and the verdict repeated it."""
    try:
        p = _project(cfg, project)
    except ValueError:
        return "(the project's folder could not be read)"
    out = []
    from . import prj_safeio
    root = p.resolve()
    for rel in dict.fromkeys(FILES.findall(goal or "")):
        try:                                              # C665: lexical, opened without links, a regular file
            r = prj_safeio.norm(rel, root)
            ok = r != "." and prj_safeio.is_file(root, r)
        except ValueError:
            continue
        if not ok:
            out.append(f"- {rel}: NOT in the folder")
            continue
        f = root / r
        text = prj_safeio.read_small(root, r, 2_000_000) if f.suffix in (".md", ".txt", ".py") else ""
        heads = [ln.strip()[:60] for ln in text.splitlines() if ln.startswith("#") or re.match(r"\*\*[^*]{2,40}\.?\*\*", ln)]
        out.append(f"- {rel}: {f.lstat().st_size} bytes" + (f"; sections: {' | '.join(heads[:12])}" if heads else ""))

    def git(*a: str) -> str:                             # C658: caged and hardened (a planted .git ran here)
        return prj_browse.git_read(p, *a, cfg=cfg, timeout=20).strip()
    pending = git("status", "--short")
    out.append("- not committed: " + (", ".join(pending.splitlines()[:15]) if pending else "nothing"))
    out.append("- last commits: " + (" · ".join(git("log", "--format=%cr %s", "-3").splitlines()) or "none"))
    out.append("- " + prj_prereg.balance(cfg, project, since))         # N142: the ledger, read by Aurora
    if prj_novelty.enabled(cfg):                                         # N146: the literature checks and their sources
        out.append("- " + prj_novelty.balance(cfg, project, since))
    lr = [r for r in prj_longrun.runs(cfg, project) if since is None or float(r.get("t") or 0) >= since]
    if lr:                                                               # N145: the long runs of the phase
        out.append("- long runs: " + "; ".join(f"{r['id']} {r['status']} «{r.get('title', '')[:50]}»" for r in lr[-6:]))
    return "\n".join(out)


def review(cfg: sys_config.Config, project: str, goal: str, report: str, llm, lang: str = "it", commands: int = 0,
           since: float | None = None, referee: dict | None = None) -> dict:
    """The conductor's reply. `commands`, `since`: what the phase ran and when it began (a phase that ran commands and
    froze nothing is said by Aurora, N142); `referee`: the severe review (prj_referee), its verdict first."""
    missing = prj_prereg.missing_note(cfg, project, commands, since or 0.0, lang) if since is not None else ""
    ref = referee or {}
    extra = (f"\n\n## Aurora's own note\n{missing}" if missing else "") + (
        f"\n\n## the severe referee's review (an AI reviewer; it did not read the report)\n{ref['text'][:6000]}"
        if ref.get("text") else "")
    out = llm.complete(REVIEW.format(lang=lang), f"## goal\n{goal}\n\n## the agent's report\n{report}\n\n"
                       f"## what the project's folder shows now (read by Aurora)\n{folder_facts(cfg, project, goal, since)}"
                       + extra, 2500)
    text = "\n\n".join(x for x in (ref.get("summary", ""), missing, out.answer.strip()) if x)
    return add(cfg, project, "reply", text, **({"review": ref["file"]} if ref.get("file") else {}))
