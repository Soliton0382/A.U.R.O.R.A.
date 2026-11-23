# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A post that repeats one of the last days' is not published (owner, 2026-10-08: with six posts a day «non ripeterti»
cannot rest on the model reading the page's last posts).

The record is Aurora's own: every post that went out — by herself (status "auto") or approved by the owner — is kept
with its arguments in the approvals' file. A new text is a repeat when it carries the same link, or opens the same
way, or its words are mostly the same (SequenceMatcher on the normalised words ≥ SIMILAR). The AI disclosure added
to every post (sys_disclosure) is left out of the comparison: it is the same in all of them.

C728 (20-23 Nov: one subject proposed 5 times in 10 hours, each with another opening): a post still waiting in the
approvals, or one the owner rejected, counts too — the agent is told which — and two more comparisons see a subject
told again in other words: the same title (the first line, SequenceMatcher ≥ TITLE), or the same content words
(Jaccard ≥ CONTENT on the words of 5 letters or more, stopwords out, cut to their first STEM letters so that a plural
is its singular). Tuned on tests/data/social_posts_c728.json (16 invented subjects, 44 posts, 4 of them near misses):
the old rules missed 40 of the 40 rewordings; the content words miss 1 and take none of the 906 different pairs.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from . import sys_config

SIMILAR = 0.6
DAYS = 7
TITLE = 0.8          # the first lines' words (different subjects of the tuning set: at most 0.46)
CONTENT = 0.2        # Jaccard of the content words (tuning set: rewordings from 0.14, median 0.41; others at most 0.17)
STEM = 6
MIN_CONTENT = 8      # content words a text needs before its words are compared (the tuning set's posts: 13 to 22)
OUT = ("auto", "approved", "executed")
SEEN = OUT + ("pending", "rejected")
STOP = set("""quando sotto sopra questo questa questi queste quello quella quelli quelle anche ancora perché perche
sono essere stato stata hanno avere fatto fatta della delle degli dello nella nelle negli nello sulla sulle sugli
dalla dalle dagli alla alle agli come dove mentre prima dopo molto molti molte poco pochi tutto tutti tutte primo
verso senza oltre secondo grazie stesso stessa stessi stesse nostro nostra nostri nostre loro altro altra altri altre
which there their these those about after before would could should being where while other""".split())
LINK = re.compile(r"https?://\S+")
WORD = re.compile(r"[\wàèéìòù]+", re.I)


def _words(text: str, drop: tuple = ()) -> list[str]:
    for line in drop:                                              # the disclosure line, the same everywhere
        text = text.replace(line, " ")
    return [w.lower() for w in WORD.findall(LINK.sub(" ", text))]


def _content(words: list[str]) -> set[str]:
    return {w[:STEM] for w in words if len(w) >= 5 and w not in STOP}


def _title(text: str, drop: tuple = ()) -> list[str]:
    return _words(next((x for x in text.strip().splitlines() if x.strip()), ""), drop)


def recent(cfg: sys_config.Config, days: int = DAYS, now: float | None = None) -> list[dict]:
    """[{"at", "tool", "text", "status"}]: the posts of the last `days` days that went out (by Aurora or approved),
    wait for the owner (pending) or were rejected by them (C728)."""
    from . import sys_approvals
    since = datetime.fromtimestamp(now or time.time()) - timedelta(days=days)
    out = []
    for a in sys_approvals.Approvals(cfg).list():
        act = a.get("action") or {}
        if a.get("status") not in SEEN or not str(act.get("tool", "")).startswith("publish"):
            continue
        try:
            at = datetime.strptime(str(a.get("created", ""))[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        args = act.get("arguments") or {}
        text = str(args.get("message") or args.get("text") or "")
        if at >= since and text:
            out.append({"at": at.strftime("%d/%m %H:%M"), "tool": f"{act.get('plugin')}.{act.get('tool')}", "text": text,
                        "status": a.get("status")})
    return out


def repeat_of(text: str, earlier: list[dict], drop: tuple = ()) -> dict | None:
    """The earlier post this text repeats, or None. `drop`: lines left out (the disclosure)."""
    words, links = _words(text, drop), set(LINK.findall(text))
    if len(words) < 4:
        return None
    title, content = _title(text, drop), _content(words)
    for e in earlier:
        old = _words(e["text"], drop)
        if links & set(LINK.findall(e["text"])) or words[:12] == old[:12] \
                or SequenceMatcher(None, words, old, autojunk=False).ratio() >= SIMILAR:
            return e
        old_title, old_content = _title(e["text"], drop), _content(old)
        if len(title) >= 3 and len(old_title) >= 3 and SequenceMatcher(None, title, old_title).ratio() >= TITLE:
            return e                                                      # C728: the same title
        if min(len(content), len(old_content)) >= MIN_CONTENT and \
                len(content & old_content) / len(content | old_content) >= CONTENT:
            return e                                                      # C728: the same subject in other words
    return None


def check(cfg: sys_config.Config, text: str) -> str:
    """'' when the text is new; otherwise why it is not published (said to the agent, which chooses another subject)."""
    drop = tuple(x for x in (str(cfg["AURORA_AI_DISCLOSURE_IT"] or ""), str(cfg["AURORA_AI_DISCLOSURE_EN"] or "")) if x)
    hit = repeat_of(text, recent(cfg), drop)
    if not hit:
        return ""
    quoted = f"{hit['at']} ({hit['tool']}: «{hit['text'][:120]}»)"
    if hit.get("status") == "rejected":                                   # C728: the owner's no is about the subject
        return (f"REFUSED: the owner already rejected this subject: the post of {quoted}. "
                "Choose a different subject, or publish nothing today.")
    if hit.get("status") == "pending":
        return (f"REFUSED: a post on this subject already waits for the owner's approval: the one of {quoted}. "
                "Choose a different subject, or publish nothing today.")
    return (f"REFUSED: this post repeats the one of {quoted}. "
            "Choose another subject, or publish nothing today.")
