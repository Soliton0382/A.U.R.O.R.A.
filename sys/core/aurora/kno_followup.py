# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What comes after an answer: follow-up questions understood, and suggested.

- `standalone`: a follow-up typed by the owner ("e chi l'ha scoperto?") rewritten as a complete question with the
  conversation and the whole previous answer with its sources' titles (C104, A22); when it was a follow-up, the
  previous answer's sources are put in focus.
- `with_focus`: the passages of sources in focus compete with the search's hits on the same re-ranker score: they
  win only where they are more relevant, nothing is forced (an answer about the paper the conversation was about,
  not about another one).
- `suggest`: 3-4 complete questions under a knowledge answer, drawn from the passages found (those not used first),
  each carrying its sources: a click starts a search that is right by construction.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING

from . import sns_clock
from .sol_schema import Soliton
from .sol_search import Hit

if TYPE_CHECKING:
    from .kno_answer import Pipeline

SYS_STANDALONE = ("You get the last turns of a conversation, Aurora's LAST ANSWER with its sources, and the owner's "
                  "LAST MESSAGE. If the last message can be understood only with what came before (it points to "
                  "something said there: 'it', 'he', 'that one', 'the author', 'and what about…', 'why?'), rewrite it "
                  "as ONE complete question that names what it points to (the subject, and the work or source when "
                  "the conversation was about one), in the language of the last message, adding nothing else. If it "
                  "is already complete on its own, copy it EXACTLY as it is. Output only the question.")
SYS_SUGGEST = ("You get the owner's QUESTION, Aurora's ANSWER and numbered PASSAGES of the library. Write 3 or 4 "
               "questions the owner may want to ask next to go deeper. Each one: answerable from the PASSAGES (prefer "
               "those marked 'not used'), COMPLETE on its own (it names its subject and, when it matters, the work: "
               "never 'it', 'this', 'the author'), not already answered by the ANSWER, at most 20 words, in the "
               "language of the QUESTION; all different. Output only JSON: [{\"q\": \"...\", \"p\": [passage numbers]}]")
MAX_FOCUS = 4                 # sources in focus
PER_SOURCE = 120              # passages of one source scored at most (a paper is 20-60)
ANSWER_CUT = 3000             # characters of the previous answer given to the rewrite
QUOTE_CUT = 3000              # characters of a quoted message taken from the page


def _last_answer(recent: list[Soliton]) -> Soliton | None:
    return next((t for t in reversed(recent) if t.extra.get("role") == "assistant"), None)


def focus_of(turn: Soliton | None) -> list[dict]:
    """The sources an answer cited, as focus entries."""
    if turn is None:
        return []
    out = []
    for s in turn.extra.get("source_list") or []:
        f = {"source": s.get("source"), "domain": s.get("domain")}
        if f["source"] and f["domain"] and f not in out:
            out.append(f)
    return out[:MAX_FOCUS]


def quoted(reader, raw) -> Soliton | None:
    """The message the owner replies to (↩️ in the chat, owner 2026-10-08: «si può saltare direttamente la ricerca sulla
    STM»): Aurora's answer of that run as she kept it, with its sources; a message that is not a run (a good morning, a
    dream) or no longer kept, as the page quoted it. None when nothing usable came."""
    if not isinstance(raw, dict):
        return None
    run_id = str(raw.get("run_id") or "")
    if re.fullmatch(r"[0-9a-f]{6,32}", run_id):
        kept = [t for t in reader.by_source("conversation", f"run:{run_id}", 8) if t.extra.get("role") == "assistant"]
        if kept:
            return kept[-1]
    text = str(raw.get("text") or "").strip()[:QUOTE_CUT]
    if not text:
        return None
    return Soliton.new(text, "conversation", "conversation", "", "quote", extra={"role": "assistant", "quoted": True})


def with_quote(recent: list[Soliton], quote: Soliton | None) -> list[Soliton]:
    """The turns with the quoted message last: what the owner answers is the last thing said, however old."""
    if quote is None:
        return recent
    return [t for t in recent if t.sid != quote.sid] + [quote]


def standalone(p: "Pipeline", question: str, recent: list[Soliton], ev, quote: Soliton | None = None) -> tuple[str, list[dict]]:
    """(the question to search, the sources to put in focus). A reply to a quoted message is read against it, at any age."""
    if not p.cfg["AURORA_PIPELINE_STANDALONE"] or not recent:
        return question, []
    try:
        last = datetime.fromisoformat(recent[-1].created_at)
    except ValueError:
        return question, []
    if quote is None and (sns_clock.now(p.cfg) - last).total_seconds() > p.cfg["AURORA_REM_SESSION_GAP_MIN"] * 60:
        return question, []                                     # an old conversation: a new topic
    prev = quote or _last_answer(recent)
    focus = focus_of(prev)
    context = f"TURNS:\n{p._turns(recent, 4, 400)}"
    if prev is not None:
        titles = "; ".join(s.get("title") or s.get("source", "") for s in prev.extra.get("source_list") or [])
        context += f"\n\nLAST ANSWER (whole):\n{prev.text[:ANSWER_CUT]}" + (f"\nITS SOURCES: {titles}" if titles else "")
    out = p._for("translate").complete(SYS_STANDALONE, f"{context}\n\nLAST MESSAGE: {question}",
                                       200).answer.strip().strip('"«»').strip()
    if not out or len(out) > 3 * len(question) + 200 or "\n" in out:          # not a question: keep the owner's
        return question, []
    if out == question:
        return question, []
    ev("question.standalone", {"question": out, "focus": len(focus)})
    return out, focus


def clean_focus(raw, taxonomy: dict) -> list[dict]:
    """Focus entries from a client: known domains, short ids, at most MAX_FOCUS."""
    out = []
    for f in raw if isinstance(raw, list) else []:
        if not isinstance(f, dict):
            continue
        src, dom = str(f.get("source", ""))[:300], str(f.get("domain", ""))
        if src and dom in taxonomy and {"source": src, "domain": dom} not in out:
            out.append({"source": src, "domain": dom})
    return out[:MAX_FOCUS]


def with_focus(p: "Pipeline", question: str, translation: str | None, hits: list[Hit], focus: list[dict], ev) -> list[Hit]:
    have = {h.sid for h in hits}
    cands = []
    for f in focus[:MAX_FOCUS]:
        cands += [s for s in p.reader.by_source(f["domain"], f["source"], PER_SOURCE)
                  if s.sid not in have and s.kind != "conversation"]
    if not cands:
        return hits
    queries = [translation if (translation and s.lang == "en") else question for s in cands]
    scores = p.search.reranker.score(list(zip(queries, [s.text for s in cands])))
    extra = [Hit(s.sid, s, 0.0, float(sc), "focus") for s, sc in zip(cands, scores)]
    merged = sorted(hits + extra, key=lambda h: -h.rerank)[:max(p.cfg["AURORA_SEARCH_TOPK"], len(hits))]
    ev("retrieval.focus", {"sources": len(focus), "scored": len(cands),
                           "kept": sum(1 for h in merged if h.query_used == "focus")})
    return merged


def suggest(p: "Pipeline", question: str, answer_text: str, sources: list[dict], hits: list[Hit], ev) -> list[dict]:
    cited = {s.get("sid") for s in sources}
    pool = [h for h in hits if h.soliton.kind != "conversation"][:8]
    if not pool:
        return []
    passages = "\n\n".join(f"[{i}] ({h.soliton.title or h.soliton.source_id}; {'used' if h.sid in cited else 'not used'})"
                           f"\n{h.soliton.text[:700]}" for i, h in enumerate(pool, 1))
    raw = p._for("translate").complete(SYS_SUGGEST, f"QUESTION: {question}\n\nANSWER:\n{answer_text[:2500]}\n\n"
                                                    f"PASSAGES:\n\n{passages}", 500).answer
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        q = str(it.get("q", "") if isinstance(it, dict) else "").strip()
        if not (10 <= len(q) <= 220) or "\n" in q or q.lower() in seen:
            continue
        seen.add(q.lower())
        ids = [n for n in (it.get("p") or []) if isinstance(n, int) and 1 <= n <= len(pool)]
        focus = []
        for n in ids:
            f = {"source": pool[n - 1].soliton.source_id, "domain": pool[n - 1].soliton.domain}
            if f not in focus:
                focus.append(f)
        out.append({"question": q, "focus": focus[:MAX_FOCUS]})
        if len(out) == 4:
            break
    if out:
        ev("answer.suggestions", {"items": out})
    return out
