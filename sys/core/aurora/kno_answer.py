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

The stages live in their modules: 4-7 in kno_stages, the self route in kno_self, the trail and the answer in
kno_trail, the split of a case told as a story in kno_split (C183); this module runs them in order.

Every stage emits an event through `emit(event, payload)`; the API streams them
and sys_log keeps them in the trace. The draft of stage 6 is streamed as
reasoning; the answer shown is the verified one, because a sentence already
shown cannot be taken back.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

from . import kno_followup, kno_split, kno_think, sys_config, sys_log, txt_lang
from .kno_self import SelfTalk
from .kno_stages import SYS_TRANSLATE, Emit, Stages
from .kno_trail import Answer, Trail, hebb  # noqa: F401 — imported from here by the API, the agents, the tests
from .mdl_llm import LLM
from .sol_index import Indexer
from .sol_reader import VaultReader
from .sol_schema import Soliton, now_iso
from .sol_search import Hit, Searcher
from .sol_writer import VaultWriter


class Pipeline(Stages, SelfTalk):
    def __init__(self, embedder, reranker, cfg: sys_config.Config | None = None, llm: LLM | None = None,
                 state_fn: Callable[[], dict] | None = None, user: str | None = None, index=None):
        self.cfg = cfg or sys_config.get()
        self.state_fn = state_fn                   # facts about Aurora measured by the caller (services, uptime)
        self.llm = llm or LLM(self.cfg)
        self.cloud_roles = {r.strip() for r in self.cfg["AURORA_CLOUD_ROLES"].split(",") if r.strip()}
        # whose conversations and memories (multi-user, U3; None: today's single owner); the knowledge index is
        # shared between the users' pipelines (`index`): loaded once
        self.user = user
        self.search = Searcher(embedder, reranker, self.cfg, index=index, user=user)
        self.reader = VaultReader(self.cfg, user=user)
        self.writer = VaultWriter(self.cfg, component="api", user=user)
        self.indexer = Indexer(embedder, self.cfg, component="api", user=user)
        self.log = sys_log.get_logger("api")

    def run(self, question: str, emit: Emit | None = None, run_id: str | None = None,
            remember: bool = True, attached: list | None = None, focus: list[dict] | None = None,
            suggest: bool = False, think: str | None = None) -> Answer:
        """`remember=False` leaves the memory untouched (a caller that retries remembers only the outcome).
        `attached`: kno_attach.Attached items; their passages come first for this question.
        `focus`: sources ({"source", "domain"}) whose passages compete with the search's (a suggested follow-up).
        `suggest`: follow-up questions after a knowledge answer (the WebUI asks for them)."""
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
        asked = question                            # the owner's words, kept for the answer and the memory
        question, auto_focus = kno_followup.standalone(self, question, recent, ev)
        focus = (focus or []) + [f for f in auto_focus if f not in (focus or [])]
        lang = txt_lang.detect(question)
        translation = None
        if lang != "en":
            translation = self._for("translate").complete(SYS_TRANSLATE, question, 200).answer
            ev("translate", {"from": lang, "translation": translation})

        def retrieve(recall: list[str] | None = None):
            # a case told as a story is searched by its problems and the provisions they need (C183); the story whole
            # only when those find nothing
            hits, subs = kno_split.search(self, question, lambda: self.search.search(question, translation, run_id=run_id,
                                                                                     recall=recall), ev, run_id)
            same = [h for h in hits if kno_split.same_message(h, asked) or kno_split.same_message(h, question)]
            if same:                                     # the owner's own message asked before: not a source
                hits = [h for h in hits if h not in same]
                ev("retrieval.filter", {"dropped_same_message": len(same)})
            # Aurora's own past answers are never a source: their sources are already in the vault, and
            # letting them cite each other is how the previous installation turned its diary into "philosophy".
            # The owner's messages stay citable: they are facts about the owner.
            # Aurora's reflections and dreams are hers, not facts about the world: never sources either.
            own = [h for h in hits if (h.soliton.kind == "conversation" and h.soliton.extra.get("role") == "assistant")
                   or h.soliton.kind == "reflection"]
            if own:
                hits = [h for h in hits if h not in own]
                ev("retrieval.filter", {"dropped_own_answers": len(own)})
            if focus:
                hits = kno_followup.with_focus(self, question, translation, hits, focus, ev)
            if attached:
                hits = self._with_attached(question, translation, hits, attached)
            ev("retrieval.hits", {"hits": [{"n": i, "sid": h.sid, "domain": h.soliton.domain, "title": h.soliton.title,
                                            "source": h.soliton.source_id, "rerank": round(h.rerank, 3)}
                                           for i, h in enumerate(hits, 1)]})
            return hits, subs

        recent_block = self._turns(recent, len(recent), cut=None)
        if recent:
            ev("memory.recent", {"turns": len(recent)})
        # how much to think (kno_think): the vault pipeline as before, or the way of the question's kind — the web
        # for a fact, the vault for an explanation, the deep pipeline for a case — read with where it was read
        # (kno_read); an attached file keeps the vault pipeline; a follow-up reads its sources in focus first
        mode = "vault" if attached else kno_think.mode_of(self.cfg, think)
        classic = lambda h, sb: self._answer(kno_split.with_searches(question, sb), h, recent_block, ev) if h else None  # noqa: E731
        verified, answer, hits, subs = kno_think.answer(self, question, translation, mode, retrieve, classic, ev,
                                                        focused=bool(focus))
        if verified:
            hebb(self.cfg, [x for x in verified["sources"] if x.get("sid")])
            result = Answer(run_id, asked, verified["text"], False, verified["sources"], verified["dropped"],
                            came_from=verified.get("came_from", ""), learn=verified.get("learn", False))
        elif answer is None:
            result = Answer(run_id, asked, self._abstention(question, lang, mode), True)
        else:
            result = Answer(run_id, asked, answer[0], False, answer[1], answer[2])
        result.seconds = time.time() - t0
        result.speed = None if result.abstained else self.speed
        ev("answer.final", {"text": result.text, "abstained": result.abstained, "sources": result.sources,
                            "dropped": result.dropped, "seconds": round(result.seconds, 1), "mode": "knowledge",
                            "speed": result.speed})
        if suggest and not result.abstained and self.cfg["AURORA_PIPELINE_SUGGEST"]:
            try:                                    # after the answer is shown: never a reason to fail it
                result.suggestions = kno_followup.suggest(self, question, result.text, result.sources, hits, ev)
            except Exception as e:
                self.log.warning("suggestions failed: %s", e)
        if remember:                                # with the suggestions: another window shows them too (C110)
            names = f" [{', '.join(a.name for a in attached)}]" if attached else ""
            self.remember(asked + names, result, run_id, ev, trail, asked_at)
        ev("run.end", {"seconds": round(result.seconds, 1)})
        return result

    def _with_attached(self, question: str, translation: str | None, hits: list[Hit], attached: list) -> list[Hit]:
        """Attached passages first: images and videos whole, documents their best chunks for this question."""
        top_k = self.cfg["AURORA_SEARCH_TOPK"]
        first: list[Hit] = []
        for a in attached:
            sols = a.solitons
            if not sols:
                continue
            queries = [translation if (translation and s.lang == "en") else question for s in sols]
            scores = self.search.reranker.score(list(zip(queries, [s.text for s in sols])))
            ranked = sorted(zip(sols, scores), key=lambda x: -float(x[1]))
            keep = ranked if a.kind in ("image", "video") else ranked[:top_k]
            first += [Hit(s.sid, s, 1.0, float(sc), "attachment") for s, sc in keep]
        seen = {h.sid for h in first}
        return (first + [h for h in hits if h.sid not in seen])[:max(top_k, len(first))]

    # ---- stage 0: route (the self route: kno_self) ---------------------------------
    def _standalone(self, question: str, recent: list[Soliton], ev: Emit) -> str:
        """The follow-up rewritten (kno_followup.standalone), without its focus: for the benchmarks."""
        return kno_followup.standalone(self, question, recent, ev)[0]

    def _for(self, role: str):
        """The model for a step, as the owner assigned it in the Models page (mdl_router: masked towards the cloud,
        the local model as fallback)."""
        from . import mdl_router
        return mdl_router.model_for(role, self.llm, self.cfg)

    def _abstention(self, question: str, lang: str, mode: str = "vault") -> str:
        if mode != "vault":                          # the web was searched already: the night studies it (kno_study)
            if lang == "it":
                return ("Non ho trovato una risposta né nel vault né sul web, e non voglio inventarla. La studio stanotte: "
                        "domani ne saprò di più.")
            return "I found no answer in my vault nor on the web, and I will not make one up. I will study it tonight."
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
                                    **({"came_from": result.came_from} if result.came_from else {}),
                                    **({"learn": True} if result.learn else {}),
                                    "mode": result.mode, "seconds": round(result.seconds, 1), "speed": result.speed,
                                    "sources": [s["sid"] for s in result.sources],
                                    "source_list": result.sources,
                                    **({"suggestions": result.suggestions} if result.suggestions else {}),
                                    **(trail.export() if trail else {})})]
        rep = self.writer.add_many(turns, run_id=run_id)
        added = self.indexer.update("conversation", run_id=run_id)
        ev("memory.write", {"written": len(rep.written), "indexed": added})
