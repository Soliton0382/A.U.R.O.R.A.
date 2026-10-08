# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora speaking of herself (the route «self» of kno_answer): small talk and questions about her, answered from her
state measured now and her memories, never from the vault's knowledge. A mixin of Pipeline (moved from kno_answer,
7 October 2026: one module per part)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import sns_clock, sns_weather, sys_persona, txt_lang
from .sol_schema import Soliton

Emit = Callable[[str, dict], None]

SYS_ROUTE = ("Classify the owner's last message to the assistant Aurora. Reply SELF if it is a greeting, small talk, "
             "thanks, a comment, or a question about Aurora herself (how she is, who or what she is, what she can do, "
             "her state, her memory, her knowledge base, the time now, the weather or anything around her home) or "
             "about the conversation itself. Reply KNOWLEDGE if it asks "
             "for facts about the world: a subject, a document, a law, a person, an event, a definition, a procedure. "
             "Examples: 'come stai?' SELF; 'che ore sono?' SELF; 'piove lì da te?' SELF; 'quanti solitoni hai nel "
             "vault?' SELF; 'cosa sai fare?' SELF; 'grazie!' SELF; 'cos'è l'entanglement?' KNOWLEDGE; 'cosa dice "
             "l'articolo 1571?' KNOWLEDGE; 'e nel caso di un affitto breve?' KNOWLEDGE. "
             "Reply with exactly one word.")
# a reply to a quoted message (↩️): working on the message itself is hers to do, with the message in front of her
SYS_ROUTE_QUOTE = ("The owner replies to a MESSAGE of the assistant Aurora, quoted below. Reply ON if the reply asks her "
                   "to work on that message itself: explain it, summarise or shorten it, translate it, say it in other "
                   "words, comment on it, doubt it, say what she meant, go through a part of it. Reply NEW if it asks "
                   "for facts the message does not contain (more about its subject, a related question). "
                   "Examples: 'spiegamelo in due righe' ON; 'traducilo in inglese' ON; 'perché dici così?' ON; "
                   "'chi l'ha scoperto?' NEW; 'e come si misura?' NEW. Reply with exactly one word.")


class SelfTalk:
    def _turns(self, recent: list[Soliton], n: int, cut: int | None = 500) -> str:
        """The last n turns with their local time and day: '[mercoledì 2026-09-30 10:31 (ieri)] Owner: ...'."""
        return "\n".join(f"[{sns_clock.when(s.created_at, self.cfg)}] {'Owner' if s.extra.get('role') == 'user' else 'Aurora'}: "
                         f"{s.text[:cut] if cut else s.text}" for s in recent[-n:])

    def _route(self, question: str, recent: list[Soliton], quote: Soliton | None = None) -> str:
        """'self' for small talk and questions about Aurora, 'knowledge' for everything else; a reply that works on
        the quoted message itself is hers too (it is answered with the message in front of her)."""
        if quote is not None:
            out = self._for("route").complete(SYS_ROUTE_QUOTE, f"MESSAGE: {quote.text[:1500]}\n\nREPLY: {question}",
                                              4).answer.strip().upper()
            if out.startswith("ON"):
                return "self"
        user = (f"PREVIOUS TURNS:\n{self._turns(recent, 2)}\n\n" if recent else "") + f"LAST MESSAGE: {question}"
        out = self._for("route").complete(SYS_ROUTE, user, 4).answer.strip().upper()
        return "self" if out.startswith("SELF") else "knowledge"

    def self_state(self) -> dict:
        """What Aurora can say about herself: measured now, never invented."""
        counts = self.reader.count()
        memory = {d for d, spec in self.reader.layout.taxonomy.items() if spec.get("memory")}
        state = {"time": sns_clock.now_text(self.cfg),
                 "weather_at_home": sns_weather.read(self.cfg) or "not measured (no coordinates or provider down)",
                 "knowledge_solitons": sum(n for d, n in counts.items() if d not in memory),
                 "knowledge_domains": {d: n for d, n in sorted(counts.items(), key=lambda x: -x[1]) if d not in memory},
                 "memory_solitons": sum(n for d, n in counts.items() if d in memory),
                 "reasoner_model": Path(str(self.cfg["AURORA_LLM_MODEL"])).stem,
                 "embedder_model": Path(str(self.cfg["AURORA_EMBEDDER_DIR"])).name,
                 "reranker_model": Path(str(self.cfg["AURORA_RERANKER_DIR"])).name}
        # her own logs: where they are and what went wrong in the last 24 hours
        from . import sys_logread
        inv = sys_logread.inventory(self.cfg, hours=24)
        state["my_logs"] = {"folder": inv["log_dir"], "format": inv["format"],
                            "problems_last_24h": {n: {"warnings": c["warnings"], "errors": c["errors"],
                                                      "last": c["last_problems"][-2:]}
                                                  for n, c in inv["components"].items() if c["warnings"] or c["errors"]}
                            or "none",
                            "answers_last_24h": sys_logread.answer_stats(24, self.cfg)}
        # her own inner life: the latest memory of a conversation, thought and dream, with their time
        if self.reader.layout.shards("memory", "reflection"):
            inner = self.reader.recent(30, domain="reflection")
            for kind in ("session_memory", "thought", "dream", "self_review"):
                last = next((x for x in reversed(inner) if x.extra.get("type") == kind), None)
                state[f"last_{kind}"] = ({"when": sns_clock.when(last.created_at, self.cfg), "text": last.text}
                                         if last else "none yet")
        if self.state_fn:
            state.update(self.state_fn())
        return state

    def _memories(self, question: str, recent: list[Soliton], ev: Emit) -> list[Soliton]:
        """What she remembers that bears on the question: semantic recall over the memory section
        (past turns, session memories, thoughts, dreams) plus every session memory of the last days.
        The recent turns are already in context and are not repeated."""
        seen = {t.sid for t in recent}
        horizon = sns_clock.now(self.cfg) - timedelta(days=self.cfg["AURORA_MEMORY_RECALL_DAYS"])
        hits = self.search.search(question, None, top_k=self.cfg["AURORA_MEMORY_RECALL_K"], sections={"memory"})
        found = {h.sid: h.soliton for h in hits
                 if h.sid not in seen and datetime.fromisoformat(h.soliton.created_at) >= horizon}
        days = self.cfg["AURORA_MEMORY_SELF_DAYS"]
        if days and self.reader.layout.shards("memory", "reflection"):
            since = sns_clock.now(self.cfg) - timedelta(days=days)
            for s in self.reader.recent(200, domain="reflection"):
                if s.extra.get("type") == "session_memory" and datetime.fromisoformat(s.created_at) >= since:
                    found.setdefault(s.sid, s)
        out = sorted(found.values(), key=lambda s: s.created_at)
        ev("memory.recall", {"semantic": len(hits), "kept": len(out),
                             "items": [{"sid": s.sid, "when": sns_clock.when(s.created_at, self.cfg),
                                        "kind": s.extra.get("type") or s.extra.get("role")} for s in out]})
        return out

    def _memory_block(self, mems: list[Soliton]) -> str:
        """Newest memories win when the block is over AURORA_MEMORY_RECALL_CHARS (the context is finite)."""
        lines, used = [], 0
        for s in reversed(mems):
            kind = s.extra.get("type") or (self.cfg["AURORA_OWNER_NAME"] if s.extra.get("role") == "user" else f"tu ({sys_persona.name(self.cfg)})")
            line = f"- [{sns_clock.when(s.created_at, self.cfg)} · {kind}] {s.text[:700]}"
            if used + len(line) > self.cfg["AURORA_MEMORY_RECALL_CHARS"]:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(reversed(lines))

    def _self_answer(self, question: str, recent: list[Soliton], ev: Emit, quote: Soliton | None = None) -> str:
        state = self.self_state()
        ev("self.state", state)
        mems = self._memories(question, recent, ev)
        today = sns_clock.now(self.cfg)
        days = "; ".join(f"{label} = {sns_clock.DAYS_IT[d.weekday()]} {d:%Y-%m-%d}" for label, d in
                         (("oggi", today), ("ieri", today - timedelta(days=1)), ("l'altro ieri", today - timedelta(days=2))))
        system = (sys_persona.identity(self.cfg)
                  + "\nFACTS ABOUT YOURSELF, MEASURED NOW:\n" + json.dumps(state, ensure_ascii=False, indent=1)
                  + f"\n\nCALENDAR: {days}. Use these dates for 'oggi', 'ieri', 'stamattina'; never compute them yourself."
                  + (f"\n\nYOUR MEMORIES RELEVANT TO THE QUESTION (oldest first; each with its date and how long ago). "
                     f"If what is asked is not here, say you do not remember it, do not invent:\n{self._memory_block(mems)}"
                     if mems else "\n\nYOUR MEMORIES: none found for this question; do not invent any.")
                  + (f"\n\nRECENT CONVERSATION:\n{self._turns(recent, len(recent))}" if recent else "")
                  + (f"\n\nTHE OWNER REPLIES TO THIS MESSAGE OF YOURS (work on it as asked, adding no facts it does "
                     f"not contain):\n{quote.text}" if quote is not None else ""))
        model, parts = self._for("self"), []
        # who speaks is said in the message itself: "Come mi chiamo?" alone made her answer as the owner
        # the prefix must not pull the language: the Italian identity made English questions get Italian answers
        o = self.cfg["AURORA_OWNER_NAME"]
        said = (f"[{o} writes to you; reply in English; 'I', 'me', 'my' mean {o}, not you] {question}"
                if txt_lang.detect(question) == "en"
                else f"[{o} ti scrive; «io», «mi», «me», «mio» indicano {o}, non te] {question}")
        think = self.cfg["AURORA_PIPELINE_SELF_THINKING"]    # A17: without it "Come mi chiamo?" was answered as the owner
        budget = self.cfg["AURORA_PIPELINE_THINK_TOKENS"] if think else 600
        for kind, piece in model.stream(system, said, budget, think=think):
            if kind == "answer":
                parts.append(piece)
            if self.cfg["AURORA_CHAT_STREAMING"]:
                ev("synthesis.delta", {"kind": kind, "text": piece})
        self.speed = getattr(model, "last_speed", None)
        return "".join(parts).strip()
