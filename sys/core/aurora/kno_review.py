# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Thinking again about past answers (owner, 2026-10-06: "the first installation computed dopamine and the like, and they
made her act, a message in the chat included... let her review conversations and run the analysis again to see if she
finds other answers").

No simulated hormone: each drive is a count read from what the code recorded.
 curiosity        questions she declined and has not studied yet (kno_study takes them at night)
 dissatisfaction  her answers whose verification dropped sentences, or that rest on a single source
 novelty          answers old enough for the vault to have grown since (days)
 social           hours since the owner last wrote
When the owner is silent, inside AURORA_REVIEW_HOURS, aurora-rem starts a review: up to AURORA_REVIEW_PER_DAY past
knowledge answers (the weakest first) are answered again from scratch, without touching the memory. The model compares
the two; only an answer that adds facts or corrects the old one, with sources the old one did not have, becomes a
message in the chat (a reflection of type "review", at most AURORA_REVIEW_MESSAGES a day) and replaces the old answer in
the shadow. Every outcome is kept in the user's state folder (review.json), so each answer is reviewed once; after
PAUSE_AFTER reviews with nothing better the review pauses by itself: it was not worth the GPU.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import sys_config

DAYS = 14                     # how far back answers are reviewed
MIN_AGE_H = 6                 # an answer of the last hours: nothing new can be in the vault yet
PAUSE_AFTER = 12              # reviews in a row with nothing better: the review pauses (owner: "si spegne da sola")
GOOD = ("NEW_INFO", "CORRECTION")

SYS_JUDGE = ("You compare two answers Aurora gave to the same QUESTION: the OLD one, given days ago, and the NEW one, "
             "written now from her current knowledge. Reply on the first line with one word: CORRECTION if the new answer "
             "corrects something the old one got wrong; NEW_INFO if it adds relevant facts the old one lacked; SAME if "
             "it says the same things in other words; WORSE if it is vaguer or answers less. On the second line, one "
             "sentence in Italian for the owner saying what changed (nothing if SAME or WORSE). Judge only the content.")


def _state_file(cfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    return d / "review.json"


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


def _today() -> float:
    return datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def paused(cfg: sys_config.Config) -> bool:
    """The last PAUSE_AFTER reviews found nothing better."""
    last = sorted(_done(cfg).values(), key=lambda o: o.get("at", 0))[-PAUSE_AFTER:]
    return len(last) >= PAUSE_AFTER and not any(o.get("verdict") in GOOD for o in last)


def _dropped(turn) -> int:
    for e in turn.extra.get("trace") or []:
        if e and e[0] == "answer.final":
            return len((e[1] or {}).get("dropped") or [])
    return 0


def _asked(turn, question: str) -> str:
    """The question as it was searched: a follow-up rewritten on its own (question.standalone), else the owner's words."""
    for e in turn.extra.get("trace") or []:
        if e and e[0] == "question.standalone":
            return (e[1] or {}).get("question") or question
    return question


def candidates(pipeline, cfg: sys_config.Config, now: datetime | None = None) -> list[dict]:
    """Past knowledge answers not reviewed yet, the weakest first: {run_id, question, asked, sid, drive, score}."""
    from . import kno_study, sys_uploads
    now = now or datetime.now(timezone.utc)
    since, until = (now - timedelta(days=DAYS)).isoformat(), (now - timedelta(hours=MIN_AGE_H)).isoformat()
    turns = pipeline.reader.recent(2000)
    asked = {t.extra.get("run_id"): t for t in turns if t.extra.get("role") == "user"}
    done = _done(cfg)
    with_files = set(sys_uploads.by_run(cfg, {t.extra.get("run_id") for t in turns} - {None}))
    out, seen = [], set()
    for t in turns:
        rid = t.extra.get("run_id")
        if (t.extra.get("role") != "assistant" or t.extra.get("abstained") or t.extra.get("mode") != "knowledge"
                or not since <= t.created_at <= until or rid not in asked or rid in done or rid in with_files):
            continue
        q = _asked(t, asked[rid].text.split(" [")[0].strip())
        if not 8 <= len(q) <= 400 or q.lower() in seen or kno_study.CONTEXT.search(q):
            continue
        seen.add(q.lower())
        dropped, sources = _dropped(t), len(t.extra.get("source_list") or [])
        days = (now - datetime.fromisoformat(t.created_at)).total_seconds() / 86400
        drive = "dissatisfaction" if dropped or sources <= 1 else "novelty"
        out.append({"run_id": rid, "question": q, "asked": t.created_at, "sid": t.sid, "drive": drive,
                    "dropped": dropped, "sources": sources, "score": round(2 * dropped + (sources <= 1) + days / 7, 2)})
    return sorted(out, key=lambda c: -c["score"])


def drives(pipeline, cfg: sys_config.Config, idle_min: float | None = None) -> dict:
    """Each drive as a count, with what it makes her do (the Health page and rem/state show them)."""
    from . import kno_study
    c = candidates(pipeline, cfg)
    return {"curiosity": len(kno_study.pending(pipeline, cfg)),
            "dissatisfaction": sum(1 for x in c if x["drive"] == "dissatisfaction"),
            "novelty": sum(1 for x in c if x["drive"] == "novelty"),
            "social_h": round(idle_min / 60, 1) if idle_min is not None else None,
            "reviewed_today": reviewed_today(cfg), "paused": paused(cfg)}


def reviewed_today(cfg: sys_config.Config) -> int:
    t = _today()
    return sum(1 for o in _done(cfg).values() if o.get("at", 0) >= t)


def told_today(cfg: sys_config.Config) -> int:
    t = _today()
    return sum(1 for o in _done(cfg).values() if o.get("at", 0) >= t and o.get("told"))


def in_hours(cfg: sys_config.Config, hour: int | None = None) -> bool:
    start, end = (int(x) for x in str(cfg["AURORA_REVIEW_HOURS"]).split("-"))
    h = datetime.now().astimezone().hour if hour is None else hour
    return start <= h < end if start <= end else (h >= start or h < end)


def due(pipeline, cfg: sys_config.Config) -> int:
    """How many answers a review would take now (0: not now)."""
    left = int(cfg["AURORA_REVIEW_PER_DAY"]) - reviewed_today(cfg)
    if left <= 0 or not in_hours(cfg) or paused(cfg):
        return 0
    return min(left, len(candidates(pipeline, cfg)))


def judge(llm, question: str, old: str, new: str) -> tuple[str, str]:
    out = llm.complete(SYS_JUDGE, f"QUESTION: {question}\n\nOLD ANSWER:\n{old[:4000]}\n\nNEW ANSWER:\n{new[:4000]}",
                       120).answer.strip()
    first, _, rest = out.partition("\n")
    word = first.strip().strip("*.: ").upper().replace(" ", "_")
    verdict = next((v for v in (*GOOD, "SAME", "WORSE") if word.startswith(v)), "SAME")
    return verdict, rest.strip().split("\n")[0][:300]


def compose(item: dict, why: str, text: str, sources: list[dict], cfg: sys_config.Config) -> str:
    from . import sns_clock
    day = sns_clock.local(item["asked"], cfg)[:10]
    head = f"Ripensando alla tua domanda del {day}, «{item['question'][:160]}»" + (f": {why}" if why else ".")
    names = "; ".join(dict.fromkeys(s.get("title") or s.get("source") or "" for s in sources if s))
    return "\n\n".join(x for x in (head, text.strip(), f"Fonti: {names}" if names else "") if x)


def review(pipeline, cfg: sys_config.Config, emit, limit: int) -> dict:
    """Answer again up to `limit` past answers; tell the owner the better ones (within AURORA_REVIEW_MESSAGES)."""
    from . import kno_shadow
    from .kno_rem import Rem
    items, out = candidates(pipeline, cfg)[:max(0, limit)], []
    past = {s.sid: s for s in pipeline.reader.recent(2000)}
    for item in items:
        t0 = time.time()
        ans = pipeline.run(item["question"], emit, item["run_id"] + "-review", remember=False)
        turn = past.get(item["sid"])
        old = turn.text if turn else ""
        old_sids = {s.get("sid") for s in (turn.extra.get("source_list") if turn else None) or []}
        fresh = [s for s in ans.sources or [] if s.get("sid") not in old_sids]
        if ans.abstained or ans.mode != "knowledge":
            verdict, why = "WORSE", ""
        else:
            verdict, why = judge(pipeline.llm, item["question"], old, ans.text)
        better = verdict in GOOD and bool(fresh)          # a new claim needs a new source, not only new words
        told = better and told_today(cfg) < int(cfg["AURORA_REVIEW_MESSAGES"])
        outcome = {"verdict": verdict, "better": better, "told": told, "drive": item["drive"], "new_sources": len(fresh),
                   "seconds": round(time.time() - t0, 1), "at": time.time(), "question": item["question"]}
        if better:
            kno_shadow.add(cfg, pipeline.search.embedder, item["question"], ans.text, ans.sources, follow=ans.suggestions)
        if told:
            text = compose(item, why, ans.text, ans.sources, cfg)
            sol = Rem(pipeline, cfg)._write(text, "review", f"review:{item['run_id']}",
                                            {"question": item["question"], "verdict": verdict, "drive": item["drive"],
                                             "old_run": item["run_id"], "sources": [{"title": s.get("title"),
                                             "source": s.get("source"), "domain": s.get("domain")} for s in ans.sources[:8]]},
                                            emit)
            outcome["sid"] = sol.sid
        _mark(cfg, item["run_id"], outcome)
        out.append({k: outcome[k] for k in ("question", "verdict", "better", "told", "new_sources", "seconds")})
    return {"reviewed": len(out), "better": sum(o["better"] for o in out), "told": sum(o["told"] for o in out),
            "items": out, "paused": paused(cfg)}
