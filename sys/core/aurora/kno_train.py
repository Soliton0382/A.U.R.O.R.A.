# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Training the shadow at night (owner, 2026-10-06: "a battery of questions, as if we were training a model, so it
performs better from the first day while the vault and the synapses grow").

Not a fixed list: each night (aurora-rem, the dream window, after the study) Aurora takes AURORA_SHADOW_TRAIN_PER_NIGHT
documents of her own knowledge at random — spread over the domains, so that a domain of 300,000 passages does not take
them all — writes for each the question a curious person would ask that the document answers (the local model), and
answers it with the whole pipeline. A verified answer with sources casts a shadow ("train"): the next time someone asks
it in other words, the answer comes in seconds. A question already in a shadow is skipped. Nothing is remembered as a
conversation (nobody asked at 3 a.m.). The state per night is in <STATUS>/train.json.
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime

from . import sys_config

SYS_Q = ("You write ONE question in Italian about the general concept, phenomenon or method the PASSAGE explains — the "
         "question someone who never saw this document would ask (e.g. 'Cos'è l'inferenza variazionale?', 'Perché i "
         "neutrini oscillano?'). Never about this study's own results, numbers, protocol or authors; never 'questo testo'. "
         "At most 15 words. If the passage explains no general concept, reply NONE. Reply with the question only.")
SKIP = {"conversation", "reflection", "patents", "general"}


def _state(cfg: sys_config.Config):
    return cfg.path("AURORA_STATUS_DIR") / "train.json"


def trained_tonight(cfg: sys_config.Config, now: datetime | None = None) -> bool:
    from . import kno_study
    try:
        at = json.loads(_state(cfg).read_text()).get("at", 0)
    except (OSError, ValueError):
        return False
    return at >= kno_study.window_start(cfg, now).timestamp()


def documents(reader, n: int, rng: random.Random) -> list:
    """n first passages of titled documents, one domain after the other at random."""
    domains = [d for d in reader.layout.domains("knowledge") if d not in SKIP]
    rng.shuffle(domains)
    out, tries = [], 0
    while len(out) < n and domains and tries < n * 20:
        tries += 1
        dom = domains[len(out) % len(domains)]
        shards = list(reader.layout.shards(reader.layout.section_of(dom), dom))
        if not shards:
            continue
        shard = rng.choice(shards)
        top = reader._con(shard).execute("SELECT max(rowid) FROM solitons").fetchone()[0] or 0
        start = rng.randint(0, max(0, top - 1))
        for _k, _r, s in reader.iter_domain(dom, after=(reader.layout.shard_key(shard), start)):
            if s.chunk_index == 0 and (s.title or "").strip() and len(s.text) > 400:
                out.append(s)
                break
            if _r - start > 400:                         # this stretch has no document start: another draw
                break
    return out


def train(pipeline, cfg: sys_config.Config, emit, n: int, seed: int | None = None) -> dict:
    from . import kno_shadow
    rng = random.Random(seed)
    asked = served = skipped = 0
    t0 = time.time()
    for s in documents(pipeline.reader, n, rng):
        try:
            q = pipeline.llm.complete(SYS_Q, f"TITLE: {s.title}\nPASSAGE: {s.text[:1500]}", 60).answer.strip().strip('"«»')
        except Exception:                               # noqa: BLE001 — one document less tonight
            continue
        if not q.endswith("?") or len(q) > 220 or q.upper().startswith("NONE"):
            continue
        if kno_shadow.find(cfg, pipeline.search.embedder, pipeline.search.reranker, q) is not None:
            skipped += 1                                 # already in a shadow
            continue
        asked += 1
        ans = pipeline.run(q, emit=lambda e, d: None, run_id=f"train-{int(time.time())}", remember=False, suggest=True)
        if not ans.abstained and ans.mode == "knowledge" and ans.sources:
            kno_shadow.add(cfg, pipeline.search.embedder, q, ans.text, ans.sources, origin="train", follow=ans.suggestions)
            served += 1
        emit("rem.train", {"question": q, "answered": not ans.abstained, "domain": s.domain})
    out = {"asked": asked, "shadows": served, "skipped": skipped, "minutes": round((time.time() - t0) / 60, 1), "at": time.time()}
    _state(cfg).write_text(json.dumps(out))
    return out
