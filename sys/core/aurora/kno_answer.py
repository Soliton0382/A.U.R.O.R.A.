# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The answer pipeline: from a question to a verified answer, or an honest abstention.

Stages, each decided by a measurement (KNOWLEDGE_PIPELINE.md, M20-M24):

 1. translate   the question to English when it is not English (M14)
 2. search      knowledge and memory, question + translation, re-ranked (sol_search)
 3. context     the latest conversation turns by time, always (short follow-ups)
 4. gate        do these passages answer *this* question? if not: abstain (M24)
 5. extract     per domain, what is relevant, with citations
 6. synthesize  one answer across domains from the extractions, with thinking (M22)
 7. verify      every sentence against the passages it cites; unsupported ones go (M22)
 8. remember    the question and the answer become STM solitons, indexed at once

Every stage emits an event through `emit(event, payload)`; the API streams them
and sys_log keeps them in the trace. The draft of stage 6 is streamed as
reasoning; the answer shown is the verified one, because a sentence already
shown cannot be taken back.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from . import mdl_cloud, sns_clock, sns_weather, sys_config, sys_log, txt_compress, txt_lang
from .mdl_llm import LLM
from .sol_index import Indexer
from .sol_reader import VaultReader
from .sol_schema import Soliton, now_iso
from .sol_search import Hit, Searcher
from .sol_writer import VaultWriter

ABSTAIN_MARK = "NONE"
IDENTITY_FILE = Path(__file__).resolve().parents[1] / "prompts" / "identity.md"
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
SYS_TRANSLATE = "Translate the user's question into English. Output only the translation."
SYS_GATE = ("You decide whether numbered passages answer a question. List the numbers of the passages that "
            "DIRECTLY answer the question asked (not the topic in general, not a related question), separated by "
            "commas. If none of them answers it, reply exactly NONE. Output nothing else.")
SYS_EXTRACT = ("You extract, from the numbered passages, everything that is relevant to the question. Keep numbers, "
               "names, formulas, conditions and results exactly as written. Cite the passage of every item, like [3]. "
               "Write as a compact list. If nothing is relevant, reply NONE.")
SYS_SYNTH = ("You are Aurora. You answer ONLY from the extractions below, which come from Aurora's verified "
             "knowledge; never from your own training. Keep the citations [n] after every sentence. Answer in the "
             "language of the question. If the extractions do not answer the question, say so plainly.")
SYS_VERIFY = ("You verify one sentence against passages. Reply with exactly one word: YES if every factual claim of "
              "the sentence is stated in the passages, NO otherwise.")


class Trail:
    """The path of a run, kept with the answer: every event but the streamed text; the reasoning apart."""
    MAX_TEXT = 2000          # characters per string field of an event
    MAX_THOUGHT = 30000      # characters of reasoning kept

    def __init__(self):
        self.steps: list[list] = []
        self.thought = ""

    def add(self, event: str, payload: dict) -> None:
        if event == "synthesis.delta":
            if payload.get("kind") == "thought" and len(self.thought) < self.MAX_THOUGHT:
                self.thought += payload.get("text", "")
            return
        self.steps.append([event, self._cut(payload)])

    def _cut(self, v):
        if isinstance(v, str):
            return v if len(v) <= self.MAX_TEXT else v[:self.MAX_TEXT] + "…"
        if isinstance(v, dict):
            return {k: self._cut(x) for k, x in v.items()}
        if isinstance(v, list):
            return [self._cut(x) for x in v]
        return v

    def export(self) -> dict:
        return {"trace": self.steps, "thought": self.thought[:self.MAX_THOUGHT]}


@dataclass
class Answer:
    run_id: str
    question: str
    text: str
    abstained: bool
    sources: list[dict] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    seconds: float = 0.0
    mode: str = "knowledge"                        # knowledge | self
    speed: dict | None = None                      # {"tokens", "per_second"} of the writing call, as measured


def _passages(hits: list[Hit], ids: list[int]) -> str:
    return "\n\n".join(f"[{n}] ({hits[n - 1].soliton.domain}, {hits[n - 1].soliton.title or hits[n - 1].soliton.source_id})\n"
                       f"{hits[n - 1].soliton.text}" for n in ids)


class Pipeline:
    def __init__(self, embedder, reranker, cfg: sys_config.Config | None = None, llm: LLM | None = None,
                 state_fn: Callable[[], dict] | None = None):
        self.cfg = cfg or sys_config.get()
        self.state_fn = state_fn                   # facts about Aurora measured by the caller (services, uptime)
        self.llm = llm or LLM(self.cfg)
        self.reasoner = mdl_cloud.make_reasoner(self.cfg, self.llm)   # reasoning roles; service calls stay local
        self.cloud_roles = {r.strip() for r in self.cfg["AURORA_CLOUD_ROLES"].split(",") if r.strip()}
        self.search = Searcher(embedder, reranker, self.cfg)
        self.reader = VaultReader(self.cfg)
        self.writer = VaultWriter(self.cfg, component="api")
        self.indexer = Indexer(embedder, self.cfg, component="api")
        self.log = sys_log.get_logger("api")

    def run(self, question: str, emit: Emit | None = None, run_id: str | None = None,
            remember: bool = True, attached: list | None = None) -> Answer:
        """`remember=False` leaves the memory untouched (a caller that retries remembers only the outcome).
        `attached`: kno_attach.Attached items; their passages come first for this question."""
        attached = attached or []
        run_id = run_id or uuid.uuid4().hex[:12]
        t0 = time.time()
        self.speed = None                          # measured by the writing call of this run

        trail = Trail()

        def ev(event: str, payload: dict) -> None:
            sys_log.trace("api", event, payload, run_id=run_id)
            trail.add(event, payload)
            if emit:
                emit(event, payload)

        asked_at = now_iso()                        # the question's own time, not the answer's
        ev("run.start", {"question": question})
        lang = txt_lang.detect(question)
        recent = self.reader.recent(self.cfg["AURORA_MEMORY_RECENT_TURNS"])
        if not attached and self._route(question, recent) == "self":
            ev("route", {"mode": "self"})
            result = Answer(run_id, question, self._self_answer(question, recent, ev), False, mode="self")
            result.seconds = time.time() - t0
            result.speed = self.speed
            ev("answer.final", {"text": result.text, "abstained": False, "sources": [], "dropped": [],
                                "seconds": round(result.seconds, 1), "mode": "self", "speed": result.speed})
            if remember:
                self.remember(question, result, run_id, ev, trail, asked_at)
            ev("run.end", {"seconds": round(result.seconds, 1)})
            return result
        ev("route", {"mode": "attachments" if attached else "knowledge"})
        translation = None
        if lang != "en":
            translation = self.llm.complete(SYS_TRANSLATE, question, 200).answer
            ev("translate", {"from": lang, "translation": translation})

        hits = self.search.search(question, translation, run_id=run_id)
        # Aurora's own past answers are never a source: their sources are already in the vault, and
        # letting them cite each other is how the previous installation turned its diary into "philosophy".
        # The owner's messages stay citable: they are facts about the owner.
        # Aurora's reflections and dreams are hers, not facts about the world: never sources either.
        own = [h for h in hits if (h.soliton.kind == "conversation" and h.soliton.extra.get("role") == "assistant")
               or h.soliton.kind == "reflection"]
        if own:
            hits = [h for h in hits if h not in own]
            ev("retrieval.filter", {"dropped_own_answers": len(own)})
        if attached:
            hits = self._with_attached(question, translation, hits, attached)
        ev("retrieval.hits", {"hits": [{"n": i, "sid": h.sid, "domain": h.soliton.domain, "title": h.soliton.title,
                                        "source": h.soliton.source_id, "rerank": round(h.rerank, 3)}
                                       for i, h in enumerate(hits, 1)]})
        recent_block = self._turns(recent, len(recent), cut=None)
        if recent:
            ev("memory.recent", {"turns": len(recent)})

        answer = self._answer(question, hits, recent_block, ev) if hits else None
        if answer is None:
            text = self._abstention(question, lang)
            result = Answer(run_id, question, text, True)
        else:
            result = Answer(run_id, question, answer[0], False, answer[1], answer[2])
        result.seconds = time.time() - t0
        result.speed = None if result.abstained else self.speed
        ev("answer.final", {"text": result.text, "abstained": result.abstained, "sources": result.sources,
                            "dropped": result.dropped, "seconds": round(result.seconds, 1), "mode": "knowledge",
                            "speed": result.speed})
        if remember:
            names = f" [{', '.join(a.name for a in attached)}]" if attached else ""
            self.remember(question + names, result, run_id, ev, trail, asked_at)
        ev("run.end", {"seconds": round(result.seconds, 1)})
        return result

    def _with_attached(self, question: str, translation: str | None, hits: list[Hit], attached: list) -> list[Hit]:
        """Attached passages first: images always, documents their best chunks for this question."""
        top_k = self.cfg["AURORA_SEARCH_TOPK"]
        first: list[Hit] = []
        for a in attached:
            sols = a.solitons
            if not sols:
                continue
            queries = [translation if (translation and s.lang == "en") else question for s in sols]
            scores = self.search.reranker.score(list(zip(queries, [s.text for s in sols])))
            ranked = sorted(zip(sols, scores), key=lambda x: -float(x[1]))
            keep = ranked if a.kind == "image" else ranked[:top_k]
            first += [Hit(s.sid, s, 1.0, float(sc), "attachment") for s, sc in keep]
        seen = {h.sid for h in first}
        return (first + [h for h in hits if h.sid not in seen])[:max(top_k, len(first))]

    # ---- stages 4-7 -------------------------------------------------------------
    def _answer(self, question: str, hits: list[Hit], recent: str, ev: Emit):
        ids = list(range(1, len(hits) + 1))
        if self.cfg["AURORA_PIPELINE_GATE"]:
            g = self.llm.complete(SYS_GATE, f"PASSAGES:\n\n{_passages(hits, ids)}\n\nQUESTION: {question}", 32)
            opened = [int(x) for x in re.findall(r"\d+", g.answer) if 1 <= int(x) <= len(hits)]
            ev("gate", {"open": bool(opened) and ABSTAIN_MARK not in g.answer.upper(), "passages": opened})
            if not opened or ABSTAIN_MARK in g.answer.upper():
                return None

        by_domain: dict[str, list[int]] = defaultdict(list)
        for n, h in enumerate(hits, 1):
            by_domain[h.soliton.domain].append(n)
        extracts = {}
        for domain, dom_ids in by_domain.items():
            x = self.llm.complete(SYS_EXTRACT, f"QUESTION: {question}\n\nPASSAGES:\n\n{_passages(hits, dom_ids)}", 700)
            keep = x.answer.strip().upper() != ABSTAIN_MARK
            ev("synthesis.domain", {"domain": domain, "passages": dom_ids, "kept": keep, "text": x.answer if keep else ""})
            if keep:
                extracts[domain] = x.answer
        if not extracts:
            return None

        think = self.cfg["AURORA_PIPELINE_THINKING"]
        if self._for("synthesis") is not self.llm and self.cfg["AURORA_CLOUD_COMPRESSION"]:
            extracts = {d: self._compress(question, t, ev) for d, t in extracts.items()}
        user = ("EXTRACTIONS BY DOMAIN:\n\n" + "\n\n".join(f"## {d}\n{t}" for d, t in extracts.items())
                + (f"\n\nRECENT CONVERSATION (context only, not a source):\n{recent}" if recent else "")
                + f"\n\nQUESTION: {question}")
        draft = []
        system = f"{SYS_SYNTH}\nNOW: {sns_clock.now_text(self.cfg)}."
        model = self._for("synthesis")
        for kind, piece in model.stream(system, user, self.cfg["AURORA_PIPELINE_THINK_TOKENS"], think=think):
            if kind == "answer":
                draft.append(piece)
            if self.cfg["AURORA_CHAT_STREAMING"]:
                ev("synthesis.delta", {"kind": kind, "text": piece})
        self.speed = getattr(model, "last_speed", None)
        text = "".join(draft).strip()
        if not text:
            return None

        dropped = []
        if self.cfg["AURORA_PIPELINE_VERIFY"]:
            text, dropped = self._verify(text, hits, ev)
            if not text:
                return None
        cited = sorted({int(x) for x in re.findall(r"\[(\d+)\]", text) if 1 <= int(x) <= len(hits)})
        sources = [{"n": n, "sid": hits[n - 1].sid, "title": hits[n - 1].soliton.title,
                    "source": hits[n - 1].soliton.source_id, "domain": hits[n - 1].soliton.domain} for n in cited]
        return text, sources, dropped

    def _verify(self, text: str, hits: list[Hit], ev: Emit) -> tuple[str, list[str]]:
        """Each sentence must cite and be supported (AURORA_VERIFY_MODE; M32: against every passage the
        cited-only check kept 8 of 14 unsupported sentences, the all-passages check none)."""
        kept, dropped = [], []
        all_ctx = "\n\n".join(f"[{n}] {h.soliton.text[:1500]}" for n, h in enumerate(hits, 1))
        for s in [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text) if x.strip()]:
            ids = sorted({int(x) for x in re.findall(r"\[(\d+)\]", s) if 1 <= int(x) <= len(hits)})
            if len(s) < 25:                      # headings, list markers: kept as they are
                kept.append(s)
                continue
            if not ids:
                dropped.append(s)
                ev("verify.drop", {"sentence": s, "reason": "no citation"})
                continue
            plain = re.sub(r"\[\d+\]", "", s)
            mode = self.cfg["AURORA_VERIFY_MODE"]
            if mode == "cited":                  # only the passages the sentence cites (before M32)
                ctx = "\n\n".join(f"[{n}] {hits[n - 1].soliton.text}" for n in ids[:4])
            else:                                # every passage given to synthesis: same prefix, cached by llama-server
                ctx = all_ctx
            ok = self.llm.complete(SYS_VERIFY, f"PASSAGES:\n{ctx}\n\nSENTENCE: {plain}", 4).answer.upper().startswith("YES")
            if not ok and mode == "all_or_english":
                en = self.llm.complete(SYS_TRANSLATE, plain, 200).answer.strip()
                ok = self.llm.complete(SYS_VERIFY, f"PASSAGES:\n{ctx}\n\nSENTENCE: {en}", 4).answer.upper().startswith("YES")
            if ok:
                kept.append(s)
                ev("verify.keep", {"sentence": s})
            else:
                dropped.append(s)
                ev("verify.drop", {"sentence": s, "reason": "not supported by the cited passages"})
        return " ".join(kept).strip(), dropped

    # ---- stage 0: route ------------------------------------------------------------
    def _turns(self, recent: list[Soliton], n: int, cut: int | None = 500) -> str:
        """The last n turns with their local time and day: '[mercoledì 2026-09-30 10:31 (ieri)] Owner: ...'."""
        return "\n".join(f"[{sns_clock.when(s.created_at, self.cfg)}] {'Owner' if s.extra.get('role') == 'user' else 'Aurora'}: "
                         f"{s.text[:cut] if cut else s.text}" for s in recent[-n:])

    def _route(self, question: str, recent: list[Soliton]) -> str:
        """'self' for small talk and questions about Aurora, 'knowledge' for everything else."""
        user = (f"PREVIOUS TURNS:\n{self._turns(recent, 2)}\n\n" if recent else "") + f"LAST MESSAGE: {question}"
        out = self.llm.complete(SYS_ROUTE, user, 4).answer.strip().upper()
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
            kind = s.extra.get("type") or (self.cfg["AURORA_OWNER_NAME"] if s.extra.get("role") == "user" else "tu (Aurora)")
            line = f"- [{sns_clock.when(s.created_at, self.cfg)} · {kind}] {s.text[:700]}"
            if used + len(line) > self.cfg["AURORA_MEMORY_RECALL_CHARS"]:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(reversed(lines))

    def _self_answer(self, question: str, recent: list[Soliton], ev: Emit) -> str:
        state = self.self_state()
        ev("self.state", state)
        mems = self._memories(question, recent, ev)
        today = sns_clock.now(self.cfg)
        days = "; ".join(f"{label} = {sns_clock.DAYS_IT[d.weekday()]} {d:%Y-%m-%d}" for label, d in
                         (("oggi", today), ("ieri", today - timedelta(days=1)), ("l'altro ieri", today - timedelta(days=2))))
        system = (IDENTITY_FILE.read_text(encoding="utf-8")
                  + "\nFACTS ABOUT YOURSELF, MEASURED NOW:\n" + json.dumps(state, ensure_ascii=False, indent=1)
                  + f"\n\nCALENDAR: {days}. Use these dates for 'oggi', 'ieri', 'stamattina'; never compute them yourself."
                  + (f"\n\nYOUR MEMORIES RELEVANT TO THE QUESTION (oldest first; each with its date and how long ago). "
                     f"If what is asked is not here, say you do not remember it, do not invent:\n{self._memory_block(mems)}"
                     if mems else "\n\nYOUR MEMORIES: none found for this question; do not invent any.")
                  + (f"\n\nRECENT CONVERSATION:\n{self._turns(recent, len(recent))}" if recent else ""))
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

    def _for(self, role: str):
        """The model for a role: the chosen reasoner for the reasoning roles, the local one otherwise."""
        return self.reasoner if role in self.cloud_roles else self.llm

    def _compress(self, question: str, text: str, ev: Emit) -> str:
        out, stats = txt_compress.compress(question, text, self.cfg["AURORA_CLOUD_KEEP_PCT"])
        ev("cloud.compress", stats)
        self.log.info("cloud compression: %d -> %d chars, %d -> %d sentences", stats["chars_in"],
                      stats["chars_out"], stats["sentences_in"], stats["sentences_out"])
        return out

    def _abstention(self, question: str, lang: str) -> str:
        if lang == "it":
            return ("Nel mio vault non ho trovato conoscenza verificata che risponda a questa domanda, quindi non "
                    "rispondo di mio. Posso cercare fonti esterne e acquisirle: rispondimi «sì, cerca».")
        return ("I found no verified knowledge in my vault that answers this question, so I will not answer from my "
                "own training. I can search external sources and acquire them: reply \"yes, search\".")

    # ---- stage 8 ------------------------------------------------------------------
    def remember(self, question: str, result: Answer, run_id: str, ev: Emit, trail: "Trail | None" = None,
                 asked_at: str | None = None) -> None:
        """The question and the answer become STM turns; the answer keeps the path that produced it
        (steps and reasoning, in `extra`), so that Aurora and the owner can look back at what she did."""
        lang = txt_lang.detect(question)
        turns = [Soliton.new(question, "conversation", "conversation", lang, f"run:{run_id}",
                             extra={"role": "user", "run_id": run_id}, created_at=asked_at),
                 Soliton.new(result.text, "conversation", "conversation", txt_lang.detect(result.text), f"run:{run_id}",
                             extra={"role": "assistant", "run_id": run_id, "abstained": result.abstained,
                                    "mode": result.mode, "seconds": round(result.seconds, 1), "speed": result.speed,
                                    "sources": [s["sid"] for s in result.sources],
                                    "source_list": result.sources,
                                    **(trail.export() if trail else {})})]
        rep = self.writer.add_many(turns, run_id=run_id)
        added = self.indexer.update("conversation", run_id=run_id)
        ev("memory.write", {"written": len(rep.written), "indexed": added})
