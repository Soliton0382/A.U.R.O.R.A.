# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖥️ What Aurora knows how to do on a desktop, readable from the chat (N157 phase A; the owner, 26 Nov: «se le chiedo
una cosa che dovrebbe passare da azioni sul PC, lo capisca»).

The chat's agent gets `desktop_skills`: the procedures of the general library (sys/core/desk/library, signed with the
code), each with its program, values and steps in plain words. READ ONLY: phase A acts on nothing — doing a procedure
on the owner's desktop is phase C (a root verifier, a code, a brake), not built yet, and the tool says so. The
owner's personal drafts (~/.local/state/aurora-desk, his alone, 0700) are not visible to aurora-api by design: a draft
enters this catalogue when it is promoted to the general library, signed."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import sys_config, sys_context

NAME = "desktop_skills"
LIBRARY = Path(__file__).resolve().parents[1] / "desk" / "library"
WANTS = re.compile(r"desktop|scrivania|\bpc\b|computer|programm|applicazion|\bapp\b|finestr|apri\b|salva|kate|kcalc|"
                   r"calcolatrice|blocco note|notepad|libreoffice|writer|dolphin|terminale|konsole|remmina|clicca|"
                   r"procedur|insegnat|impara|sai (?:usare|fare)|cosa sai", re.I)
LIMIT_NOTE = ("Phase A only: Aurora knows these procedures and can explain them; she does NOT perform them on the "
              "owner's desktop yet (phase C: a root verifier, a code from the phone, a brake — not built). Say so if "
              "asked to do one, and offer the steps instead.")

TOOL = {"name": NAME, "description": (
    "What Aurora knows how to do on a computer's desktop (programs she learned from demonstrations: Kate, KCalc, "
    "Notepad…): without `id`, the list; with `id`, one procedure's values and steps in plain words. Read only. "
    + LIMIT_NOTE),
    "input_schema": {"type": "object", "properties": {
        "id": {"type": "string", "description": "a procedure's id from the list, to see its steps"}}}}


def procedures(root: Path = LIBRARY) -> list[dict]:
    out = []
    for f in sorted(root.rglob("*.json")) if root.is_dir() else []:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append(p)
    return out


def _describe(step: dict) -> str:
    from desk.app import explain                     # plain words, the same as Aurora Desktop's own preview
    return explain.describe(step)


def listing(root: Path = LIBRARY) -> str:
    ps = procedures(root)
    if not ps:
        return "No procedure learned yet.\n" + LIMIT_NOTE
    rows = [f"- {p['id']}: {(p.get('title') or {}).get('it', '')} — {p.get('os')}, {(p.get('program') or {}).get('name')}"
            f" (values: {', '.join(p.get('params', {})) or 'none'})" for p in ps]
    return f"{len(ps)} procedures:\n" + "\n".join(rows) + "\n" + LIMIT_NOTE


def detail(pid: str, root: Path = LIBRARY) -> str:
    p = next((x for x in procedures(root) if x.get("id") == pid), None)
    if p is None:
        return f"ERROR: no procedure «{pid}»; the list has: " + ", ".join(x.get("id", "?") for x in procedures(root))
    prog = p.get("program") or {}
    vals = "; ".join(f"{k} ({v.get('kind')}{', max ' + str(v['max']) if v.get('max') else ''})"
                     for k, v in p.get("params", {}).items()) or "none"
    steps = "\n".join(f"{s['n']}. {_describe(s)} [{s.get('class', '')}]" for s in p.get("steps", []))
    return (f"{p['id']}: {(p.get('title') or {}).get('it', '')}\nprogram: {prog.get('name')} ({p.get('os')}), "
            f"versions {prog.get('versions')}\nvalues: {vals}\nsteps:\n{steps}\n{LIMIT_NOTE}")


def offered(cfg: sys_config.Config, goal: str) -> list[dict]:
    """When the request speaks of the desktop, its programs or what she learned; never in the anonymous chat."""
    if sys_context.anonymous_now() or not WANTS.search(goal or ""):
        return []
    return [TOOL]


def agent_call(agent, a: dict) -> str:
    if sys_context.anonymous_now():
        return f"ERROR: {NAME} is not available in the anonymous chat"
    pid = str(a.get("id") or "").strip()
    return detail(pid) if pid else listing()
