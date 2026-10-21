# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugins whose tools come on request (16 Oct, measured: the agent's catalog was ~39,700 tokens from 35 plugins, and
GitHub's official server alone 17,750 — 45 tools, 90 calls in two weeks). A plugin whose manifest says

    "on_demand": {"words": ["github", "repository", "pull request", …]}

is in the catalog only when the goal (or its context) names one of its words; otherwise the system prompt says it in
one line, and the agent may ask for it with `more_tools`: its tools come back in the tool's answer (not in the system
prompt, which stays the same run after run and is read from the prompt cache — C332) and can be called at once."""
from __future__ import annotations

import json
import re

MORE = {"name": "more_tools", "description": "Bring the tools of a plugin listed under «On request» (its name), when "
        "the goal needs it: its functions come back in the answer and can be called right after.",
        "input_schema": {"type": "object", "properties": {"plugin": {"type": "string"}}, "required": ["plugin"]}}


def words(manifest: dict) -> list[str]:
    return [str(w).lower() for w in ((manifest.get("on_demand") or {}).get("words") or []) if str(w).strip()]


def wanted(manifest: dict, text: str) -> bool:
    """True for a plugin of every run, or one whose words the text names (whole words, any case)."""
    ws = words(manifest)
    if not manifest.get("on_demand"):
        return True
    low = text.lower()
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", low) for w in ws)


def line(plugin) -> str:
    d = (getattr(plugin, "manifest", None) or {}).get("description")
    d = (d.get("en") or next(iter(d.values()), "")) if isinstance(d, dict) else str(d or "")
    return f"- {plugin.name}: {d[:140]} ({len(plugin.tools)} tools)"


def section(deferred: list) -> str:
    if not deferred:
        return ""
    return ("\n\n# On request\nThese plugins' tools are not listed above, to keep this prompt short. If the goal needs "
            "one, call more_tools with its name first.\n" + "\n".join(line(p) for p in deferred))


def specs_of(plugin, sep: str) -> tuple[list[dict], dict]:
    specs, index = [], {}
    for t in plugin.tools:
        name = f"{plugin.name}{sep}{t['name']}"
        index[name] = (plugin.name, t["name"], t["effect"])
        specs.append({"type": "function", "function": {
            "name": name, "description": f"[{t['effect']}] {t['description']}",
            "parameters": t["input_schema"] or {"type": "object", "properties": {}}}})
    return specs, index


def more(deferred: list, name: str, index: dict, sep: str) -> str:
    """more_tools: the plugin's specs as text, its tools added to the run's index."""
    p = next((x for x in deferred if x.name == name.strip()), None)
    if p is None:
        return f"ERROR: {name!r} is not among the plugins on request: {', '.join(x.name for x in deferred) or 'none'}"
    specs, idx = specs_of(p, sep)
    index.update(idx)
    return (f"The tools of {p.name}, callable now:\n<tools>\n"
            + "\n".join(json.dumps(s, ensure_ascii=False) for s in specs) + "\n</tools>")


RESULT_CHARS = 12000


def clip(result: str) -> str:
    """A tool's result as the agent reads it: at most RESULT_CHARS, and a longer one says so (C381: every result was
    cut at 6,000 characters without a word — a patent page asked with max_chars 60,000 ended at its «Definitions» and
    the agent believed it had read it all)."""
    over = len(result) - RESULT_CHARS
    if over <= 0:
        return result
    return (result[:RESULT_CHARS] + f"\n[cut here: {over} more characters not shown. Read the rest in parts — the "
            "tool's offset, a smaller max_chars, or save it to a project file and read that by offset]")
