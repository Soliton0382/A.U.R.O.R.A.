# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A post that repeats one of the last days' is not published (owner, 2026-10-08: with six posts a day «non ripeterti»
cannot rest on the model reading the page's last posts).

The record is Aurora's own: every post that went out — by herself (status "auto") or approved by the owner — is kept
with its arguments in the approvals' file. A new text is a repeat when it carries the same link, or opens the same
way, or its words are mostly the same (SequenceMatcher on the normalised words ≥ SIMILAR). The AI disclosure added
to every post (sys_disclosure) is left out of the comparison: it is the same in all of them.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from . import sys_config

SIMILAR = 0.6
DAYS = 7
LINK = re.compile(r"https?://\S+")
WORD = re.compile(r"[\wàèéìòù]+", re.I)


def _words(text: str, drop: tuple = ()) -> list[str]:
    for line in drop:                                              # the disclosure line, the same everywhere
        text = text.replace(line, " ")
    return [w.lower() for w in WORD.findall(LINK.sub(" ", text))]


def recent(cfg: sys_config.Config, days: int = DAYS, now: float | None = None) -> list[dict]:
    """[{"at", "tool", "text"}]: the posts that went out in the last `days` days (by Aurora or approved)."""
    from . import sys_approvals
    since = datetime.fromtimestamp(now or time.time()) - timedelta(days=days)
    out = []
    for a in sys_approvals.Approvals(cfg).list():
        act = a.get("action") or {}
        if a.get("status") not in ("auto", "approved", "executed") or not str(act.get("tool", "")).startswith("publish"):
            continue
        try:
            at = datetime.strptime(str(a.get("created", ""))[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        args = act.get("arguments") or {}
        text = str(args.get("message") or args.get("text") or "")
        if at >= since and text:
            out.append({"at": at.strftime("%d/%m %H:%M"), "tool": f"{act.get('plugin')}.{act.get('tool')}", "text": text})
    return out


def repeat_of(text: str, earlier: list[dict], drop: tuple = ()) -> dict | None:
    """The earlier post this text repeats, or None. `drop`: lines left out (the disclosure)."""
    words, links = _words(text, drop), set(LINK.findall(text))
    if len(words) < 4:
        return None
    for e in earlier:
        old = _words(e["text"], drop)
        if links & set(LINK.findall(e["text"])) or words[:12] == old[:12] \
                or SequenceMatcher(None, words, old, autojunk=False).ratio() >= SIMILAR:
            return e
    return None


def check(cfg: sys_config.Config, text: str) -> str:
    """'' when the text is new; otherwise why it is not published (said to the agent, which chooses another subject)."""
    drop = tuple(x for x in (str(cfg["AURORA_AI_DISCLOSURE_IT"] or ""), str(cfg["AURORA_AI_DISCLOSURE_EN"] or "")) if x)
    hit = repeat_of(text, recent(cfg), drop)
    if not hit:
        return ""
    return (f"REFUSED: this post repeats the one of {hit['at']} ({hit['tool']}: «{hit['text'][:120]}»). "
            "Choose another subject, or publish nothing today.")
