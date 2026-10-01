# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Stages 1 and 2 of the knowledge pipeline: recall and selection (KNOWLEDGE_PIPELINE.md).

    question (+ its English translation, when given)
      -> vector search over every domain of knowledge and memory (global: a
         domain filter loses the answer when the domain is guessed wrong, M10/M13)
      -> union of the candidates (AURORA_SEARCH_CANDIDATES per query)
      -> re-ranking, each passage read with the question in the passage's own
         language: Italian solitons with the Italian question, English ones with
         the translation (M14: translation helps on English text; ECOSYSTEM 4.1)
      -> the best AURORA_SEARCH_TOPK passages, then grouped by domain for synthesis.

Every call logs its timings and emits a `retrieval.hits` trace event with the
sids and scores it kept.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from . import sys_config, sys_log
from .sol_index import IndexSet
from .sol_reader import VaultReader
from .sol_schema import Soliton


@dataclass
class Hit:
    sid: str
    soliton: Soliton
    dense: float
    rerank: float
    query_used: str          # "original" or "translation"


class Searcher:
    def __init__(self, embedder, reranker, cfg: sys_config.Config | None = None,
                 reader: VaultReader | None = None, index: IndexSet | None = None):
        self.cfg = cfg or sys_config.get()
        self.embedder, self.reranker = embedder, reranker
        self.reader = reader or VaultReader(self.cfg)
        self.index = index or IndexSet(self.cfg)
        self.log = sys_log.get_logger("search")

    def search(self, question: str, translation: str | None = None, candidates: int | None = None,
               top_k: int | None = None, run_id: str | None = None, sections: set[str] | None = None) -> list[Hit]:
        candidates = candidates or self.cfg["AURORA_SEARCH_CANDIDATES"]
        top_k = top_k or self.cfg["AURORA_SEARCH_TOPK"]
        t0 = time.time()
        queries = [question] + ([translation] if translation and translation != question else [])
        qv = self.embedder.encode_queries(queries)
        t1 = time.time()
        dense: dict[str, float] = {}
        for per_query in self.index.search(np.asarray(qv), candidates, sections):
            for sid, score, _, _ in per_query:
                dense[sid] = max(score, dense.get(sid, -1.0))
        t2 = time.time()
        sols = self.reader.get_many(dense)
        order = [sid for sid in dense if sid in sols]
        if len(order) < len(dense):
            self.log.warning("%d indexed sids not found in the vault (index ahead of a reset?)", len(dense) - len(order))
        use_translation = [bool(translation) and sols[sid].lang == "en" for sid in order]
        pairs = [((translation if tr else question), sols[sid].text) for sid, tr in zip(order, use_translation)]
        scores = self.reranker.score(pairs)
        t3 = time.time()
        ranked = sorted(zip(order, scores, use_translation), key=lambda x: -x[1])[:top_k]
        hits = [Hit(sid, sols[sid], dense[sid], float(s), "translation" if tr else "original") for sid, s, tr in ranked]
        self.log.info("search: %d queries, %d candidates, %d kept | encode %.2f s, vector %.3f s, rerank %.2f s",
                      len(queries), len(order), len(hits), t1 - t0, t2 - t1, t3 - t2)
        sys_log.trace("search", "retrieval.hits",
                      {"question": question, "translated": bool(translation), "candidates": len(order),
                       "hits": [{"sid": h.sid, "domain": h.soliton.domain, "rerank": round(h.rerank, 4),
                                 "dense": round(h.dense, 4)} for h in hits],
                       "seconds": {"encode": round(t1 - t0, 3), "vector": round(t2 - t1, 3), "rerank": round(t3 - t2, 3)}},
                      run_id=run_id)
        return hits

    @staticmethod
    def group_by_domain(hits: list[Hit]) -> dict[str, list[Hit]]:
        groups: dict[str, list[Hit]] = defaultdict(list)
        for h in hits:
            groups[h.soliton.domain].append(h)
        return dict(groups)
