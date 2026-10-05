# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Studying at night what she did not know (owner, 2026-10-05: "stanotte ho studiato quello che ieri non sapevo").

During the day Aurora declines a question when her knowledge does not answer it (35% of the knowledge questions in a
week, measured on the Status page). At night (aurora-rem, the dream window, after the dream) she takes the questions
she declined in the last days, at most AURORA_STUDY_PER_NIGHT, and for each one runs the search agent: it looks for
sources (arXiv and the harvester's sources), imports them, and answers again — not remembered as a conversation
(nobody asked at 3 a.m.): the outcome is kept as a reflection of type "study", learned or still not, with the answer
and its sources. The morning greeting (kno_morning) tells the owner what she learned. Each question is studied once;
the state per user is in their state folder (study.json).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import re

from . import sys_config

# the night imports only what the re-ranker found clearly relevant: in the first study run (2026-10-05, 12 imports) the
# relevant ones scored 0.75-0.97, the useless ones ("Red", "GIMP" for a question about a picture) 0.11-0.32 —
# provisional, to measure again on more nights (M110)
MIN_SCORE = 0.5
# a question about something shown or attached cannot be studied from sources
CONTEXT = re.compile(r"(?i)\b(this|these|that|questa|questo|queste|questi|quella|quello)\s+(image|picture|photo|file|"
                     r"document|video|page|screenshot|immagine|foto|documento|pagina|pdf|schermata)\b|allegat|attached")


def _state_file(cfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    return d / "study.json"


def _done(cfg: sys_config.Config) -> dict:
    f = _state_file(cfg)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        return {}


def _mark(cfg: sys_config.Config, run_id: str, outcome: dict) -> None:
    d = _done(cfg)
    d[run_id] = outcome
    f = _state_file(cfg)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def pending(pipeline, cfg: sys_config.Config, days: float = 7) -> list[dict]:
    """The knowledge questions she declined in the last days and has not studied yet, oldest first."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    turns = pipeline.reader.recent(2000)
    asked = {t.extra.get("run_id"): t for t in turns if t.extra.get("role") == "user"}
    done = _done(cfg)
    from . import sys_uploads
    with_files = set(sys_uploads.by_run(cfg, {t.extra.get("run_id") for t in turns} - {None}))
    out, seen = [], set()
    for t in turns:
        rid = t.extra.get("run_id")
        if (t.extra.get("role") == "assistant" and t.extra.get("abstained") and t.extra.get("mode", "knowledge") == "knowledge"
                and t.created_at >= since and rid in asked and rid not in done):
            q = asked[rid].text.split(" [")[0].strip()
            if rid in with_files or CONTEXT.search(q):
                continue                                  # about a picture or a file: not a question for sources
            if 8 <= len(q) <= 400 and q.lower() not in seen:
                seen.add(q.lower())
                out.append({"run_id": rid, "question": q, "asked": asked[rid].created_at})
    return out


SELF_CONTAINED = ("You classify the QUESTION below, you do not answer it. Can it be answered from books and articles "
                  "alone, without seeing a picture, a file, a screen, the user's own accounts or an earlier message it "
                  "refers to? Reply with one word: YES or NO.")


def self_contained(llm, question: str) -> bool:
    """The local model's reading: "che colore è questo quadrato?" needs the picture (M110: a word list missed it)."""
    try:
        return llm.complete(SELF_CONTAINED, f"QUESTION: {question}", 3).answer.strip().upper().startswith("Y")
    except Exception:                                 # noqa: BLE001 — in doubt, not studied
        return False


def study(pipeline, cfg: sys_config.Config, emit, limit: int) -> dict:
    """Study up to `limit` declined questions; each outcome a reflection of type study."""
    from .kno_acquire import ArxivAgent
    from .kno_rem import Rem
    todo, skipped = [], 0
    for item in pending(pipeline, cfg):
        if len(todo) >= max(0, limit):
            break
        if self_contained(pipeline.llm, item["question"]):
            todo.append(item)
        else:                                         # about something shown: marked, never studied
            _mark(cfg, item["run_id"], {"learned": False, "skipped": "needs what was shown", "at": time.time(),
                                        "question": item["question"]})
            skipped += 1
    learned = 0
    for item in todo:
        t0 = time.time()
        ans = ArxivAgent(pipeline, cfg).run(item["question"], emit, item["run_id"] + "-study", remember=False,
                                            min_score=MIN_SCORE)
        ok = not ans.abstained
        learned += ok
        sources = [{"title": s.get("title"), "source": s.get("source"), "domain": s.get("domain")} for s in (ans.sources or [])]
        text = (f"Domanda: {item['question']}\n\n" + (ans.text if ok else "Ho cercato, ma non ho ancora trovato fonti che rispondano."))
        Rem(pipeline, cfg)._write(text, "study", f"study:{item['run_id']}",
                                  {"question": item["question"], "learned": ok, "asked": item["asked"], "sources": sources[:8],
                                   "seconds": round(time.time() - t0, 1)}, emit)
        _mark(cfg, item["run_id"], {"learned": ok, "at": time.time(), "question": item["question"]})
    return {"studied": len(todo), "learned": learned, "skipped": skipped, "left": max(0, len(pending(pipeline, cfg)))}


def tonight(pipeline) -> list:
    """The study reflections of the last 18 hours (for the morning greeting)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat()
    return [s for s in pipeline.reader.recent(300, domain="reflection")
            if s.extra.get("type") == "study" and s.created_at >= since] \
        if pipeline.reader.layout.shards("memory", "reflection") else []
