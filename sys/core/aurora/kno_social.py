# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Social pages: statistics, ideas, drafts. Publishing always goes through the owner.

Platforms are the plugins whose manifest has a "social" section:
  {"label", "publish": {"tool", "field"}, "stats": tool, "max_chars"}
Drafts are plain posts in Aurora's voice (no links), within the platform's length, and end
with the AI disclosure (EU AI Act art. 50). Publishing is an external action: the owner's click
on "Publish" (WebUI) is the confirmation, and it is recorded in the approvals history.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import sys_config, sys_disclosure, sys_log, sys_persona, txt_lang
from .plg_host import PluginHost

SYS_DRAFT = ("\nYou write a social media post for %OWNER%'s {label} page from the content below. A classic post: "
             "no links, no hashtags spam (at most 3 relevant hashtags), engaging first line, in {lang}, at most "
             "{max_chars} characters. Plain text: no markdown (no ** bold, no # headings). Only what the content says: "
             "do not add facts, numbers, quotes, sayings or examples that are not in it. Output only the post.")
SYS_IDEAS = ("\nYou manage %OWNER%'s social pages. From the statistics and from what happened recently (conversations, "
             "new knowledge, thoughts), write in Italian: 1) a short reading of the statistics (what works, what does "
             "not, with the numbers given); 2) three concrete post ideas, each with the platform and a one-line draft. "
             "Only facts from the input.")


def platforms(host: PluginHost) -> list[dict]:
    out = []
    for p in host.plugins():
        social = p.manifest.get("social")
        if social and p.enabled:                       # a platform switched off is not offered anywhere
            out.append({"plugin": p.name, "label": social.get("label", p.name), "available": p.available,
                        "missing": p.missing, "max_chars": social.get("max_chars", 1000),
                        "publish": social.get("publish"), "photo": social.get("photo"), "stats": social.get("stats")})
    return out


def draft(llm, content: str, targets: list[dict], cfg: sys_config.Config | None = None) -> dict[str, str]:
    cfg = cfg or sys_config.get()
    lang = txt_lang.detect(content)
    identity = sys_persona.identity(cfg)
    out = {}
    for t in targets:
        room = t["max_chars"] - len(cfg["AURORA_AI_DISCLOSURE_IT"]) - 10
        text = llm.complete(identity + SYS_DRAFT.format(label=t["label"], lang="Italian" if lang == "it" else "English",
                                                        max_chars=room), content[:6000], 700).answer.strip()
        out[t["plugin"]] = sys_disclosure.mark_text(text[:room], lang, cfg)
    return out


def report(p, host: PluginHost, cfg: sys_config.Config | None = None) -> dict:
    """Statistics of every connected platform, and ideas; returned for a memory (REM)."""
    cfg = cfg or sys_config.get()
    stats = {}
    for t in platforms(host):
        if t["available"] and t["stats"]:
            r = host.call(t["plugin"], t["stats"], {})
            stats[t["label"]] = r["text"] if r["ok"] else f"not measured: {r['text'][:200]}"
    if not stats:
        return {"skipped": "no social platform connected"}
    recent = [s.text[:300] for s in p.reader.recent(8)]
    inner = [s.text[:300] for s in p.reader.recent(6, domain="reflection")] \
        if p.reader.layout.shards("memory", "reflection") else []
    user = json.dumps({"statistics": stats, "recent_conversation": recent, "recent_thoughts": inner}, ensure_ascii=False)
    text = p._for("rem").complete(sys_persona.identity(p.cfg) + SYS_IDEAS, user, 900).answer.strip()
    sys_log.get_logger("social").info("social report: %s", ", ".join(stats))
    return {"text": text, "stats": stats}
